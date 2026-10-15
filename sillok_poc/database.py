"""SQLite schema and read-only query executor for an educational PoC."""
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    article_id TEXT PRIMARY KEY,
    reign TEXT NOT NULL,
    year INTEGER NOT NULL,
    date_raw TEXT,
    title_ko TEXT NOT NULL,
    original_text TEXT,
    categories TEXT
);
CREATE INDEX IF NOT EXISTS idx_records_reign_year ON records(reign, year);
"""
SCHEMA_PROMPT = """SQLite database. Only one table exists:
records(article_id TEXT primary key, reign TEXT, year INTEGER,
        date_raw TEXT, title_ko TEXT, original_text TEXT, categories TEXT)
- reign is the Korean king name (e.g., '태조', '세종').
- year is numeric Western calendar year in the original records, not reign year.
- date_raw is the original date string and may include an intercalary-month marker.
- title_ko is a Korean article heading; original_text is Classical Chinese.
- categories is a semicolon-separated subject list (e.g. '군사-관방(關防)').
- Queries about topic words use title_ko or categories LIKE. Do not assume
  a Korean question can be matched directly against Classical Chinese.
- Return exactly one SQLite SELECT query, with no explanatory prose.
"""


def create_db(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    con.commit()
    return con


def insert_articles(db_path, articles):
    con = create_db(db_path)
    count = 0
    try:
        with con:
            for a in articles:
                con.execute("""INSERT OR REPLACE INTO records
                (article_id,reign,year,date_raw,title_ko,original_text,categories)
                VALUES (?,?,?,?,?,?,?)""", (a.article_id, a.reign, a.year,
                a.date_raw, a.title_ko, a.original_text, a.categories))
                count += 1
    finally:
        con.close()
    return count


# SQLite authorizer is an extra gate in addition to read-only URI + SELECT check.
_ALLOWED_FUNCTIONS = {
    "count", "min", "max", "avg", "sum", "like", "length", "lower",
    "upper", "substr", "coalesce", "ifnull", "trim", "abs", "round"
}


def _authorizer(action, arg1, arg2, database, trigger):
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        return sqlite3.SQLITE_OK if arg1 == "records" else sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_OK if (arg2 or "").lower() in _ALLOWED_FUNCTIONS else sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_DENY


class SQLValidationError(ValueError):
    """Query is outside the supported read-only SQL subset."""


class QueryTimeoutError(TimeoutError):
    """SQLite exceeded its execution budget."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool
    sql_time_sec: float


def execute_query(db_path, sql, max_rows=20, timeout_sec=2.0):
    """Return positional rows, column metadata, and explicit truncation status."""
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows < 1:
        raise ValueError("max_rows는 1 이상의 정수여야 합니다.")
    if not isinstance(timeout_sec, (int, float)) or not 0 < timeout_sec < float("inf"):
        raise ValueError("timeout_sec는 유한한 양수여야 합니다.")
    import re
    sql = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^SELECT\s", sql):
        raise SQLValidationError("현재는 SELECT로 시작하는 SQL만 허용합니다.")
    if ";" in sql:
        raise SQLValidationError("SQL 여러 문장은 허용되지 않습니다.")
    db_path = Path(db_path).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"DB가 없습니다: {db_path}")
    con = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        con.set_authorizer(_authorizer)
        start = time.monotonic()
        con.set_progress_handler(lambda: int(time.monotonic() - start > timeout_sec), 1000)
        try:
            cursor = con.execute(sql)
            columns = [item[0] for item in cursor.description]
            rows = [list(row) for row in cursor.fetchmany(max_rows + 1)]
        except sqlite3.Error as exc:
            if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                raise QueryTimeoutError("SQL 실행 시간이 제한을 초과했습니다.") from exc
            if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_AUTH or "not authorized" in str(exc):
                raise SQLValidationError("허용되지 않은 테이블 또는 함수입니다.") from exc
            raise
        return QueryResult(columns, rows[:max_rows], len(rows) > max_rows,
                           round(time.monotonic() - start, 4))
    finally:
        con.close()


def execute_readonly(db_path, sql, max_rows=20, timeout_sec=2.0):
    """Compatibility wrapper for the original CLI and data tests."""
    result = execute_query(db_path, sql, max_rows, timeout_sec)
    rows = []
    for row in result.rows:
        mapped = {}
        for column, value in zip(result.columns, row):
            mapped.setdefault(column, value)
        rows.append(mapped)
    return rows, result.sql_time_sec
