from collections import defaultdict
import os
import json
from typing import Optional, List, Dict, Any
import re
from crawl.crawler import Crawler
from embedder.base_embedder import Embedder
from vector_index.vector_db import VectorDatabase
try:
    from processors.text_summarizer import TextSummarizer
except Exception:
    TextSummarizer = object
from processors.page_processor import SemanticPageProcessor
from processors.text_chunkers import DefaultChunker
from processors.text_extractors import DefaultTextExtractor
from webcreeper.creeper_core.utils import configure_logging


class IngestPipeline:
    """
    End-to-end pipeline:
      - extract(): runs crawler with a page-writer callback so results.jsonl is always written
      - transform(): reads results.jsonl/.json -> chunk -> (optional) summarize -> embed
      - load(): writes vectors + metadata to FAISS
      - run(): orchestrates (crawl_only | index_only | both)
    """

    # Soft limits to avoid model/context errors during summarization
    _MAX_SUMMARY_CHARS: int = 12000          # cap text passed to summarizer
    _HEAD_TAIL_SPLIT: int = 10000            # keep head N + tail (_MAX - N)

    def __init__(
        self,
        crawler: Crawler,
        index_path: str,
        embedder: Embedder,
        db: VectorDatabase,
        summarizer: Optional[TextSummarizer],
        results_path: Optional[str] = None,
        use_summary: bool = True,
        debug: bool = False,
        debug_summary_path: Optional[str] = None,
        progress_callback=None
    ):
        self.crawler = crawler
        self.index_path = index_path
        self.embedder = embedder
        self.db = db
        self.summarizer = summarizer
        self.use_summary = bool(use_summary)
        # default to crawler's configured output file
        self.results_path = results_path or os.path.join(
            getattr(crawler, "output_dir", "."), getattr(crawler, "results_filename", "results.jsonl")
        )
        self.debug = bool(debug)
        self.logger = configure_logging(self.__class__.__name__)
        self.progress_callback = progress_callback

        # Debug file paths
        if debug_summary_path:
            self.debug_summary_path = debug_summary_path
            # keep a sibling for raw chunks
            base_dir = os.path.dirname(self.debug_summary_path)
            os.makedirs(base_dir, exist_ok=True)
            self.debug_chunks_path = os.path.join(base_dir, "raw_chunks.jsonl")
        else:
            debug_dir = os.path.join(getattr(crawler, "output_dir", "."), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            self.debug_summary_path = os.path.join(debug_dir, "summaries_full.jsonl")
            self.debug_chunks_path = os.path.join(debug_dir, "raw_chunks.jsonl")

        # Page processor: HTML -> text chunks
        self.page_processor = SemanticPageProcessor(
            extractor=DefaultTextExtractor(),
            chunker=DefaultChunker()
        )

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _resolve_results_path(self, require_non_empty: bool = False) -> str:
        """
        Resolve the actual path to crawl results:
          - if self.results_path exists use it
          - else try swapping .jsonl <-> .json
          - else try defaults in crawler.output_dir
        """
        candidates: List[str] = []
        rp = self.results_path

        # 1) as-is
        candidates.append(rp)

        # 2) swap extension
        root, ext = os.path.splitext(rp)
        if ext.lower() == ".jsonl":
            candidates.append(root + ".json")
        elif ext.lower() == ".json":
            candidates.append(root + ".jsonl")

        # 3) defaults next to crawler output_dir
        out_dir = getattr(self.crawler, "output_dir", None)
        if out_dir:
            candidates.append(os.path.join(out_dir, "results.jsonl"))
            candidates.append(os.path.join(out_dir, "results.json"))

        for path in candidates:
            if os.path.exists(path) and (os.path.getsize(path) > 0 or not require_non_empty):
                return path

        # Fallback to original
        return rp

    def _default_page_writer(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Accept both callback styles used by Atlas/Crawler:
          - (url: str, html: str)
          - ({ "url": ..., "html": ... })
        Return a dict the crawler can write directly, or None to skip.
        """
        # dict style first
        if args and isinstance(args[0], dict):
            d = args[0]
            url = d.get("url"); html = d.get("html")
            return {"url": url, "html": html} if url and html else None

        # tuple style
        if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
            url, html = args[0], args[1]
            return {"url": url, "html": html} if url and html else None

        # kwargs fallback
        url = kwargs.get("url"); html = kwargs.get("html")
        return {"url": url, "html": html} if url and html else None

    def _safe_summarize(self, url: str, text: str) -> Optional[str]:
        """
        Guard the summarizer against very-long inputs that can trigger model context errors.
        """
        if not self.summarizer:
            return None

        src = text or ""
        if len(src) > self._MAX_SUMMARY_CHARS:
            # keep a large head and a small tail (often contains boilerplate footers we can omit)
            head = src[:self._HEAD_TAIL_SPLIT]
            tail = src[-(self._MAX_SUMMARY_CHARS - self._HEAD_TAIL_SPLIT):]
            src = head + "\n\n[...] (truncated)\n\n" + tail

        try:
            data = self.summarizer(url, src)
            if isinstance(data, dict) and "summary" in data and data["summary"]:
                return data["summary"]
        except Exception as e:
            self.logger.error(f"Summarizer error for {url}: {e}")
        return None

    # -------------------------------------------------------------------------
    # Public stages
    # -------------------------------------------------------------------------
    def extract(self, override_callback=None, settings_override: dict = None):
        """
        Run the crawler. We always provide a page-writer callback so results get saved.
        """
        self.logger.info("Crawling site...")
        writer_cb = override_callback or self._default_page_writer
        # Newer crawler signatures
        try:
            self.crawler.crawl(
                on_page_crawled=writer_cb,
                settings_override=settings_override,
                save_sitemap=True
            )
        except TypeError:
            # Older signatures (graceful fallback)
            try:
                self.crawler.crawl(writer_cb)
            except TypeError:
                # Oldest: no args
                self.crawler.crawl()

    def transform(self) -> List[dict]:
        """
        Read results file -> chunk -> (optional) summarize -> embed.
        """
        self.logger.info(
            f"Transforming pages (summarize = {self.use_summary and bool(self.summarizer)})"
        )
        # Initialize FAISS index
        self.db.create(dim=self.embedder.dim)
        transformed_records: List[dict] = []

        # Resolve results path (require presence & non-empty)
        resolved_results = self._resolve_results_path(require_non_empty=True)
        if not os.path.exists(resolved_results):
            raise FileNotFoundError(f"[IngestPipeline] results not found at {resolved_results}")
        if os.path.getsize(resolved_results) == 0:
            raise FileNotFoundError(f"[IngestPipeline] results file is empty at {resolved_results}")

        # Load site graph once
        graph_path = os.path.join(getattr(self.crawler, "output_dir", "."), "graph.json")
        if os.path.exists(graph_path):
            try:
                with open(graph_path, "r", encoding="utf-8") as gf:
                    site_graph = json.load(gf)
            except Exception as e:
                self.logger.warning(f"Failed to read graph.json: {e}")
                site_graph = {}
        else:
            site_graph = {}

        # Build a reverse map for incoming links once (cheap even for small/med graphs)
        incoming_map = defaultdict(list)
        for from_page, links in (site_graph or {}).items():
            for link in (links or []):
                target = link.get("target")
                if not target:
                    continue
                incoming_map[target].append({
                    "from_page": from_page,
                    "anchor_text": link.get("anchor_text", ""),
                    "source_chunk": link.get("source_chunk"),
                })


        summary_debug_file = open(self.debug_summary_path, "w", encoding="utf-8") if self.debug else None
        chunk_debug_file = open(self.debug_chunks_path, "w", encoding="utf-8") if self.debug else None

        # Stream results (compute total for progress if possible)
        total_lines = None
        try:
            with open(resolved_results, "r", encoding="utf-8") as count_f:
                total_lines = sum(1 for _ in count_f)
        except Exception:
            total_lines = None

        with open(resolved_results, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, start=1):
                try:
                    record = json.loads(line)
                    url = record.get("url")
                    html = record.get("html")
                    
                    outgoing_links = site_graph.get(url, [])
                    incoming_links = incoming_map.get(url, [])

                    if not url or not html:
                        self.logger.warning(
                            f"Skipping malformed record (missing url/html): {record}"
                        )
                        continue

                    chunks = self.page_processor.process(url, html)

                    if self.progress_callback:
                        try:
                            self.progress_callback(idx, total_lines, url)
                        except Exception:
                            pass

                    for chunk in chunks:
                        content_to_embed = chunk.get("text", "")
                        if not isinstance(content_to_embed, str) or not content_to_embed.strip():
                            continue

                        # Debug: raw chunks
                        if self.debug and chunk_debug_file:
                            json.dump({
                                "url": chunk.get("url", url),
                                "chunk_index": chunk.get("chunk_index", -1),
                                "text": content_to_embed,
                                "length": len(content_to_embed)
                            }, chunk_debug_file)
                            chunk_debug_file.write("\n")

                        # Optional summarization
                        if self.use_summary and self.summarizer:
                            summary_text = self._safe_summarize(url, content_to_embed)
                            if summary_text:
                                chunk["summary"] = summary_text
                                content_to_embed = summary_text

                                if self.debug and summary_debug_file:
                                    json.dump({
                                        "url": chunk.get("url", url),
                                        "chunk_index": chunk.get("chunk_index", -1),
                                        "original_preview": chunk.get("text", "")[:500],
                                        "summary_preview": summary_text[:500]
                                    }, summary_debug_file)
                                    summary_debug_file.write("\n")
                            else:
                                # If summarizer failed, proceed with original text
                                pass

                        parts = self._chunk_for_embedding(content_to_embed)
                        parent_chunk_id = f"{url}#chunk_{chunk.get('chunk_index', -1)}"

                        for seg_idx, part in enumerate(parts):
                            try:
                                embedding = self.embedder.embed(part)
                            except Exception as e:
                                self.logger.error(
                                    f"Embedding error for {url} (seg {seg_idx}): {e}"
                                )
                                continue
                            if embedding is None:
                                self.logger.warning(
                                    f"Skipping chunk from {url} seg {seg_idx} - embedding returned None."
                                )
                                continue

                            rec = {
                                **chunk,  # keep original fields (url, hierarchy, etc.)
                                "text": part,                # the actual embedded segment text
                                "embedding": embedding,
                                "id": f"{parent_chunk_id}__seg_{seg_idx}",
                                "metadata": {
                                    **(chunk.get("metadata", {}) or {}),
                                    "chunk_id": parent_chunk_id,  # keep original id as parent
                                    "seg_index": seg_idx,
                                    "seg_count": len(parts),
                                    "page_url": url,
                                    "outgoing_links": outgoing_links,
                                    "incoming_links": incoming_links,
                                },
                            }
                            transformed_records.append(rec)


                except json.JSONDecodeError:
                    self.logger.warning("Skipping line (not valid JSON).")
                except Exception as e:
                    self.logger.warning(f"Skipping record due to error: {e}")

        if summary_debug_file:
            summary_debug_file.close()
            self.logger.info(f"Wrote debug summaries to {self.debug_summary_path}")

        if chunk_debug_file:
            chunk_debug_file.close()
            self.logger.info(f"Wrote raw chunks to {self.debug_chunks_path}")

        return transformed_records

    def load(self, records: List[dict]):
        """
        Write records to FAISS and persist to disk.
        """
        if not isinstance(records, list):
            records = []

        for rec in records:
            try:
                self.db.add([rec])
            except Exception as e:
                self.logger.error(f"Failed to add record: {e}")

        # Persist index + metadata
        try:
            self.db.save(self.index_path)
            self.logger.info(f"Saved index to {self.index_path}")
        except Exception as e:
            raise RuntimeError(f"[IngestPipeline] Failed to save index to {self.index_path}: {e}")

    # -------------------------------------------------------------------------
    # Orchestrator
    # -------------------------------------------------------------------------
    def run(
        self,
        override_callback=None,
        settings_override: dict = None,
        force_crawl: bool = False,
        mode: str = "both",  # "crawl_only" | "index_only" | "both"
    ):
        """
        mode:
          - "crawl_only": only run the crawler and produce results.jsonl/graph.json
          - "index_only": only read results.jsonl/.json -> build FAISS index
          - "both": (default) crawl if needed, then index
        """
        mode = (mode or "both").lower()
        if mode not in ("crawl_only", "index_only", "both"):
            raise ValueError(f"Invalid mode: {mode}")

        # ---------------- Crawl phase ----------------
        if mode in ("crawl_only", "both"):
            # Decide whether to crawl
            resolved_before = self._resolve_results_path(require_non_empty=False)
            need_crawl = force_crawl or not (os.path.exists(resolved_before) and os.path.getsize(resolved_before) > 0)

            if need_crawl:
                self.logger.info(f"Crawling (force={force_crawl})...")
                writer_cb = override_callback or self._default_page_writer

                try:
                    self.crawler.crawl(
                        on_page_crawled=writer_cb,
                        settings_override=settings_override,
                        save_sitemap=True
                    )
                except TypeError:
                    try:
                        self.crawler.crawl(writer_cb)
                    except TypeError:
                        self.crawler.crawl()

            # Re-resolve after crawl
            resolved_after = self._resolve_results_path(require_non_empty=False)
            if not os.path.exists(resolved_after) or os.path.getsize(resolved_after) == 0:
                # Optional: dump disallowed reasons for debugging if crawler exposes it
                report_path = None
                try:
                    report = getattr(self.crawler, "get_disallowed_report", lambda: {})()
                    if report:
                        dbg_dir = os.path.join(getattr(self.crawler, "output_dir", "."), "debug")
                        os.makedirs(dbg_dir, exist_ok=True)
                        report_path = os.path.join(dbg_dir, "disallowed_report.json")
                        with open(report_path, "w", encoding="utf-8") as fp:
                            json.dump(report, fp, indent=2)
                except Exception:
                    pass

                # >>> handled return instead of raising <<<
                msg = (
                    f"[IngestPipeline] No pages were saved at {resolved_after}. "
                    "The results file is missing or empty. This can happen if the start URL "
                    "is outside Allowed Domains, robots/allowlist rules blocked pages, or the crawler "
                    "couldn't fetch any HTML (JS-only pages, auth walls, etc.)."
                )
                result = {
                    "crawled": True,
                    "indexed": False,
                    "results_path": resolved_after,
                    "empty_results": True,
                    "message": msg,
                }
                if report_path:
                    result["disallowed_report_path"] = report_path

                # For crawl_only we stop here cleanly; for both we also stop without indexing.
                return result

            else:
                self.logger.info(f"Using cached results at {resolved_before}")

            if mode == "crawl_only":
                self.logger.info("Crawl-only mode complete.")
                return {
                    "crawled": True,
                    "indexed": False,
                    "results_path": self._resolve_results_path(require_non_empty=False),
                }

        # ---------------- Index phase ----------------
        if mode in ("index_only", "both"):
            resolved_for_index = self._resolve_results_path(require_non_empty=False)
            if not os.path.exists(resolved_for_index) or os.path.getsize(resolved_for_index) == 0:
                return {
                    "crawled": (mode == "both"),
                    "indexed": False,
                    "results_path": resolved_for_index,
                    "empty_results": True,
                    "message": (
                        f"[IngestPipeline] Cannot index because the results file is missing or empty at "
                        f"{resolved_for_index}. Run a crawl first or adjust Allowed Domains / seeds."
                    ),
                }
            records = self.transform()
            self.load(records)
            self.logger.info("Indexing phase complete.")
            return {
                "crawled": (mode == "both"),
                "indexed": True,
                "index_path": self.index_path,
            }

    def _max_input_tokens(self) -> int:
        for attr in ("max_input_tokens", "max_tokens", "context_size", "max_seq_len"):
            v = getattr(self.embedder, attr, None)
            if isinstance(v, int) and v > 0:
                return v
        return 8192

    def _count_tokens(self, text: str) -> int:
        if hasattr(self.embedder, "count_tokens"):
            try:
                return int(self.embedder.count_tokens(text))
            except Exception:
                pass
        return max(1, len(text) // 4)

    def _hard_char_splits(self, text: str, max_tokens: int) -> list[str]:
        char_budget = max(800, max_tokens * 4)
        out, i, n = [], 0, len(text)
        while i < n:
            out.append(text[i : min(n, i + char_budget)])
            i += char_budget
        return out

    def _chunk_for_embedding(self, text: str, safety_ratio: float = 0.9) -> list[str]:
        ratio = getattr(self.embedder, "safety_ratio", safety_ratio)
        max_tok = int(self._max_input_tokens() * ratio)
        if self._count_tokens(text) <= max_tok:
            return [text]
        paras = re.split(r"\n{2,}", text)
        chunks, cur, cur_toks = [], [], 0
        def flush():
            nonlocal chunks, cur, cur_toks
            if cur:
                joined = "\n\n".join(cur).strip()
                if joined:
                    chunks.append(joined)
            cur, cur_toks = [], 0
        for p in paras:
            ptok = self._count_tokens(p)
            if ptok > max_tok:
                sents = re.split(r"(?<=[.!?])\s+", p)
                for s in sents:
                    stok = self._count_tokens(s)
                    if stok > max_tok:
                        for piece in self._hard_char_splits(s, max_tok):
                            if self._count_tokens(piece) > max_tok:
                                chunks.append(piece)
                            else:
                                if cur_toks + self._count_tokens(piece) > max_tok:
                                    flush()
                                cur.append(piece)
                                cur_toks += self._count_tokens(piece)
                        continue
                    if cur_toks + stok > max_tok:
                        flush()
                    cur.append(s); cur_toks += stok
                flush()
            else:
                if cur_toks + ptok > max_tok:
                    flush()
                cur.append(p); cur_toks += ptok
        flush()
        return [c for c in chunks if c]
