from bs4 import BeautifulSoup, Tag
from typing import List, Dict
import uuid

class SemanticChunker:
    def __init__(self, max_tokens: int = 512, tokenizer=None):
        self.max_tokens = max_tokens
        self.tokenizer = tokenizer  # Optional to count tokens

    def chunk_html(self, html: str, source_url: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html5lib")
        body = soup.body or soup

        chunks = []
        heading_stack = []
        current_text = []
        current_meta = {
            "hierarchy": [],
            "tag_path": [],
            "chunk_type": "text",
            "source": source_url,
            "order": 0
        }
        order = 0
        last_element_type = None

        def flush_current_chunk():
            nonlocal order
            if current_text:
                text = "\n".join(current_text).strip()
                if text:
                    chunk = {
                        "id": str(uuid.uuid4()),
                        "text": text,
                        "source": source_url,
                        "hierarchy": current_meta["hierarchy"].copy(),
                        "tag_path": current_meta["tag_path"].copy(),
                        "chunk_type": current_meta["chunk_type"],
                        "order": order
                    }
                    if self.tokenizer:
                        chunk["tokens"] = len(self.tokenizer(chunk["text"]))
                    chunks.append(chunk)
                    order += 1
                current_text.clear()
                current_meta["tag_path"] = []
                current_meta["chunk_type"] = "text"

        for element in body.descendants:
            if isinstance(element, Tag):
                if element.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                    flush_current_chunk()
                    level = int(element.name[1])
                    heading_text = element.get_text(strip=True)
                    heading_stack = heading_stack[:level - 1] + [heading_text]
                    current_meta["hierarchy"] = heading_stack.copy()
                    current_meta["tag_path"] = [element.name]
                elif element.name in ["p", "li"]:
                    text = self._preserve_links(element).strip()
                    if text:
                        prefix = "- " if element.name == "li" else ""
                        current_text.append(prefix + text)
                        current_meta["tag_path"].append(element.name)
                        last_element_type = element.name
                elif element.name in ["ul", "ol"]:
                    current_meta["tag_path"].append(element.name)
                elif element.name == "table":
                    flush_current_chunk()
                    table_text = self._extract_table_as_markdown(element)
                    if table_text:
                        chunk = {
                            "id": str(uuid.uuid4()),
                            "text": table_text,
                            "source": source_url,
                            "hierarchy": heading_stack.copy(),
                            "tag_path": ["table"],
                            "chunk_type": "table",
                            "order": order
                        }
                        if self.tokenizer:
                            chunk["tokens"] = len(self.tokenizer(chunk["text"]))
                        chunks.append(chunk)
                        order += 1
                elif element.name == "pre" and element.find("code"):
                    code_text = element.get_text(strip=False).strip()
                    if code_text:
                        # If previous content exists, attach code to it
                        if last_element_type in ["p", "li"]:
                            current_text.append(f"```\n{code_text}\n```")
                            current_meta["tag_path"].append("code")
                            current_meta["chunk_type"] = "text"
                        else:
                            flush_current_chunk()
                            chunk = {
                                "id": str(uuid.uuid4()),
                                "text": f"```\n{code_text}\n```",
                                "source": source_url,
                                "hierarchy": heading_stack.copy(),
                                "tag_path": ["code"],
                                "chunk_type": "code",
                                "order": order
                            }
                            if self.tokenizer:
                                chunk["tokens"] = len(self.tokenizer(chunk["text"]))
                            chunks.append(chunk)
                            order += 1
                        last_element_type = "code"

        flush_current_chunk()
        return chunks

    def _extract_table_as_markdown(self, table_tag: Tag) -> str:
        rows = table_tag.find_all("tr")
        if not rows:
            return ""

        output = []
        for i, row in enumerate(rows):
            cols = row.find_all(["td", "th"])
            line = " | ".join(col.get_text(strip=True) for col in cols)
            output.append(line)
            if i == 0:
                output.append(" | ".join(["---"] * len(cols)))

        return "\n".join(output)
    
    def _preserve_links(self, element: Tag) -> str:
        """
        Converts <a href="...">text</a> to [text](url) # markdown
        """
        for a in element.find_all('a'):
            href = a.get('href')
            if href:
                label = a.get_text(strip=True)
                a.replace_with(f"[{label}]({href})")
            else:
                a.unwrap()
        return element.get_text(separator=" ")
