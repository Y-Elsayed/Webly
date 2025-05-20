import string
import tiktoken
class TextSummarizer:
    def __init__(self, llm, prompt_template="Summarize the following text:\n{text}", model="gpt-3.5-turbo", max_tokens=2000):
        self.llm = llm
        self.prompt_template = prompt_template
        self.max_tokens = max_tokens
        self.tokenizer = tiktoken.encoding_for_model(model)

    def _truncate_text(self, text: str) -> str:
        tokens = self.tokenizer.encode(text)
        return self.tokenizer.decode(tokens[:self.max_tokens])

    def _has_text_placeholder(self) -> bool:
        formatter = string.Formatter()
        return any(field_name == 'text' for _, field_name, _, _ in formatter.parse(self.prompt_template))

    def summarize(self, url: str, text: str) -> dict:
        safe_text = self._truncate_text(text)

        # Check if the prompt needs the text or not
        if self._has_text_placeholder():
            prompt = self.prompt_template.format(text=safe_text)
        else:
            prompt = self.prompt_template

        # Flexible handling of LLM interface (messages or prompt)
        if hasattr(self.llm, 'generate'):
            summary = self.llm.generate(prompt)
        elif hasattr(self.llm, 'chat'):
            summary = self.llm.chat([{"role": "user", "content": prompt}])
        else:
            raise RuntimeError("LLM must implement either `generate(prompt)` or `chat(messages)`")

        return {
            "url": url,
            "summary": summary,
            "length": len(summary)
        }

    def __call__(self, url: str, text: str) -> dict:
        return self.summarize(url, text)
