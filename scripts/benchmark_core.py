"""Synthetic, offline FAISS/BM25 workload measurement, not an LLM quality benchmark."""

import argparse
import json
import platform
import re
import statistics
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from webly import ModelCapabilities, ProviderBundle, ResourceScope, build_runtime
from webly.vector_index.snapshots import SnapshotStore


class Embeddings:
    def count_tokens(self, text):
        return len(text.split())

    def embed(self, text):
        return [1.0, 0.5, 0.0, 0.0]


class Model:
    def count_tokens(self, text):
        return len(text.split())

    def generate(self, prompt):
        if "Sufficient?" in prompt:
            return "YES"
        if "Cite only Evidence IDs" in prompt:
            match = re.search(r"\[Evidence: ([^\]]+)\] \(Source: [^\n]+\)\n(?:\[[^\n]+\]\n)?([^\n]+)", prompt)
            return json.dumps(
                {
                    "answer": match[2],
                    "status": "answered",
                    "missing_information": [],
                    "citations": [{"segment_id": match[1], "supporting_span": match[2]}],
                }
            )
        return "SAME"


def main():
    import psutil

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=2000)
    parser.add_argument("--segments-per-page", type=int, default=10)
    parser.add_argument("--queries", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()
    if min(args.pages, args.segments_per_page, args.queries) < 1:
        parser.error("Workload sizes must be positive")
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()

    def sample():
        while not stop.wait(0.01):
            peak[0] = max(peak[0], process.memory_info().rss)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        with tempfile.TemporaryDirectory(prefix="webly-benchmark-") as temporary:
            root = Path(temporary)
            providers = ProviderBundle(
                Embeddings(),
                ModelCapabilities("benchmark", 8192, dimensions=4),
                Model(),
                ModelCapabilities("benchmark-chat", 128000),
            )
            with (
                providers,
                build_runtime(
                    {"start_url": "https://fixture.test/", "retrieval_mode": "classic"},
                    resources=ResourceScope("benchmark", root / "core"),
                    providers=providers,
                ) as runtime,
            ):
                records = []
                source = root / "results.jsonl"
                with source.open("w", encoding="utf-8") as stream:
                    for page in range(args.pages):
                        paragraphs = []
                        for segment in range(args.segments_per_page):
                            text = (
                                f"Page {page} segment {segment} describes the public visitor "
                                "schedule and opening hours."
                            )
                            paragraphs.append(text)
                            sid = f"page-{page}-segment-{segment}"
                            records.append(
                                {
                                    "segment_id": sid,
                                    "id": sid,
                                    "url": f"https://fixture.test/{page}",
                                    "text": text,
                                    "original_text": text,
                                    "embedding_text": text,
                                    "hierarchy": ["Schedule"],
                                    "embedding": [1, segment / 10, 0, 0],
                                }
                            )
                        stream.write(
                            json.dumps({"url": f"https://fixture.test/{page}", "html": "\n".join(paragraphs)}) + "\n"
                        )
                start = time.perf_counter()
                runtime.db.create(4)
                runtime.db.add(records)
                del records
                SnapshotStore(runtime.config.index_dir).publish(runtime.db, source_path=str(source))
                publication_s = time.perf_counter() - start
                start = time.perf_counter()
                runtime.query_result("What is the visitor schedule?")
                cold_s = time.perf_counter() - start
                workloads = []

                def query(index):
                    started = time.perf_counter()
                    result = runtime.query_result(f"What is the schedule for page {index}?")
                    assert result.supported and result.citations
                    return time.perf_counter() - started

                for concurrency in (1, 4, 10):
                    before = process.memory_info().rss
                    with ThreadPoolExecutor(max_workers=concurrency) as pool:
                        samples = list(pool.map(query, range(args.queries)))
                    ordered = sorted(samples)
                    workloads.append(
                        {
                            "concurrency": concurrency,
                            "queries": len(samples),
                            "p50_s": statistics.median(samples),
                            "p95_s": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))],
                            "rss_before": before,
                            "rss_after": process.memory_info().rss,
                        }
                    )
                report = {
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "synthetic": True,
                    "real_model_calls": False,
                    "capacity_claim": False,
                    "pages": args.pages,
                    "segments": args.pages * args.segments_per_page,
                    "embedding_dimensions": 4,
                    "runtime_concurrency_policy": "serialized_per_runtime",
                    "snapshot_build_publish_s": publication_s,
                    "cold_query_s": cold_s,
                    "workloads": workloads,
                    "sampled_peak_rss_bytes": peak[0],
                }
    finally:
        stop.set()
        sampler.join(timeout=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
