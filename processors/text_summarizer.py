import tiktoken

class TextSummarizer:
    #For future me: the prompt_template needs more testing and tuning, which will tested in the main
    def __init__(self, llm, prompt_template="Summarize the following text:\n{text}", model="gpt-3.5-turbo", max_tokens=2000):
        self.llm = llm
        self.prompt_template = prompt_template
        self.max_tokens = max_tokens
        self.tokenizer = tiktoken.encoding_for_model(model)

    def _truncate_text(self, text: str) -> str:
        tokens = self.tokenizer.encode(text)
        truncated_tokens = tokens[:self.max_tokens]
        return self.tokenizer.decode(truncated_tokens)

    def summarize(self, url: str, text: str) -> dict:
        safe_text = self._truncate_text(text)
        prompt = self.prompt_template.format(text=safe_text)
        summary = self.llm.generate(prompt)

        return {
            "url": url,
            "summary": summary,
            "length": len(summary)
        }

    def __call__(self, url: str, text: str) -> dict:
        return self.summarize(url, text)
