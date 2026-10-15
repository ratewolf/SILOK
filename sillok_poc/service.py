"""Shared question-to-query contract; importing this module never loads a GPU model."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
import sqlite3
import logging
from threading import Lock
import time
from typing import Callable, Protocol

from .database import execute_query, QueryTimeoutError, SQLValidationError


class SQLGenerator(Protocol):
    def generate(self, question: str) -> str: ...


@dataclass
class Answer:
    question: str
    status: str = "error"
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    model_time_sec: float = 0.0
    sql_time_sec: float = 0.0
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self):
        return asdict(self)


def _default_model():
    from .model import TextToSQL
    return TextToSQL()


class QuestionService:
    """Create once per process. Serialize requests and reuse one lazily loaded model."""

    def __init__(self, db_path, model_factory: Callable[[], SQLGenerator] = _default_model,
                 max_rows=20, timeout_sec=2.0):
        self.db_path = Path(db_path)
        self.model_factory = model_factory
        self.max_rows = max_rows
        self.timeout_sec = timeout_sec
        self._model = None
        self._lock = Lock()

    def ask(self, question: str) -> Answer:
        answer = Answer(question=question)
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            answer.error_code = "invalid_question"
            answer.error_message = "질문을 1~1000자로 입력해 주세요."
            return answer
        with self._lock:
            if not self.db_path.is_file():
                answer.error_code = "database_missing"
                answer.error_message = "데이터베이스를 먼저 준비해 주세요."
                return answer
            start = time.monotonic()
            try:
                if self._model is None:
                    self._model = self.model_factory()
                answer.sql = self._model.generate(question.strip())
                if not isinstance(answer.sql, str) or not answer.sql.strip():
                    raise ValueError("모델이 SQL을 반환하지 않았습니다.")
            except Exception:
                logging.getLogger(__name__).exception("Text-to-SQL model execution failed")
                answer.error_code = "model_error"
                answer.error_message = "모델 실행에 실패했습니다. 서버의 모델 환경을 확인해 주세요."
                return answer
            finally:
                answer.model_time_sec = round(time.monotonic() - start, 4)
            try:
                result = execute_query(self.db_path, answer.sql, self.max_rows, self.timeout_sec)
            except QueryTimeoutError:
                answer.error_code = "query_timeout"
                answer.error_message = "조회 시간이 초과되었습니다. 조건을 좁혀 주세요."
            except SQLValidationError:
                answer.error_code = "sql_rejected"
                answer.error_message = "허용된 읽기 전용 SQL로 변환하지 못했습니다. 질문을 바꿔 주세요."
            except FileNotFoundError:
                answer.error_code = "database_missing"
                answer.error_message = "데이터베이스를 먼저 준비해 주세요."
            except sqlite3.Error:
                answer.error_code = "query_error"
                answer.error_message = "생성된 SQL을 실행하지 못했습니다. 질문을 바꿔 주세요."
            else:
                answer.status = "ok"
                answer.columns = result.columns
                answer.rows = result.rows
                answer.truncated = result.truncated
                answer.sql_time_sec = result.sql_time_sec
            return answer
