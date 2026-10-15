"""GPU-only optional inference using the model card's Unsloth loader.
Install unsloth separately in a compatible GPU environment; not needed to test data.
"""
import re
from .database import SCHEMA_PROMPT

MODEL_ID = "huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko"


class TextToSQL:
    def __init__(self):
        try:
            from unsloth import FastLanguageModel
        except ImportError as exc:
            raise RuntimeError("AI 실행환경에서 `pip install unsloth`가 필요합니다.") from exc
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=MODEL_ID, max_seq_length=2048, dtype=None, load_in_4bit=True
        )
        FastLanguageModel.for_inference(self.model)

    def generate(self, question):
        prompt = f"""다음 스키마를 참고하여 SQLite SELECT문만 생성해 주세요.
{SCHEMA_PROMPT}

질문: {question}
SQL:"""
        messages = [{"role": "user", "content": prompt}]
        tokens = self.tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
        ).to(self.model.device)
        generated = self.model.generate(
            input_ids=tokens, max_new_tokens=180, do_sample=False,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        # Decode ONLY new tokens, not the original prompt.
        result = self.tokenizer.decode(generated[0][tokens.shape[-1]:], skip_special_tokens=True).strip()
        fenced = re.search(r"```(?:sql)?\s*(.*?)```", result, re.I | re.S)
        if fenced:
            result = fenced.group(1).strip()
        return result
