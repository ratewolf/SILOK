from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import time

import pytest

from sillok_poc.database import execute_query, insert_articles, QueryTimeoutError
from sillok_poc.service import QuestionService
from sillok_poc.xml_loader import iter_articles
from test_core import FIXTURE


@pytest.fixture
def db(tmp_path):
    path = tmp_path / 'service.db'
    insert_articles(path, iter_articles(FIXTURE))
    return path


class Generator:
    def __init__(self, sql):
        self.sql = sql

    def generate(self, question):
        return self.sql


def test_truncation_empty_and_duplicate_columns(db):
    result = execute_query(db, 'SELECT title_ko, title_ko FROM records ORDER BY article_id', max_rows=1)
    assert result.columns == ['title_ko', 'title_ko']
    assert len(result.rows) == 1 and len(result.rows[0]) == 2
    assert result.truncated
    assert not execute_query(db, 'SELECT * FROM records', max_rows=2).truncated
    empty = execute_query(db, 'SELECT title_ko FROM records WHERE year=0')
    assert empty.rows == [] and empty.columns == ['title_ko'] and not empty.truncated


@pytest.mark.parametrize(('sql', 'code'), [
    ('DELETE FROM records', 'sql_rejected'),
    ('SELECT * FROM sqlite_master', 'sql_rejected'),
    ("SELECT load_extension('x')", 'sql_rejected'),
    ('SELECT nonexistent FROM records', 'query_error'),
])
def test_service_errors_leave_database_unchanged(db, sql, code):
    answer = QuestionService(db, lambda: Generator(sql)).ask('질문')
    assert answer.status == 'error' and answer.error_code == code
    assert answer.sql == sql
    assert execute_query(db, 'SELECT COUNT(*) FROM records').rows == [[2]]


def test_empty_is_success_and_missing_db_does_not_load_model(db, tmp_path):
    def forbidden():
        raise AssertionError('Model must not load')
    empty = QuestionService(db, lambda: Generator('SELECT year FROM records WHERE year=0')).ask('빈 결과')
    assert empty.status == 'ok' and empty.rows == [] and empty.error_code is None
    service = QuestionService(tmp_path/'missing.db', forbidden)
    assert service.ask('질문').error_code == 'database_missing'
    assert service.ask('  ').error_code == 'invalid_question'
    assert not (tmp_path/'missing.db').exists()


def test_model_failure_can_be_retried(db):
    calls = []
    def factory():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('private server details')
        return Generator('SELECT COUNT(*) FROM records')
    service = QuestionService(db, factory)
    failed = service.ask('질문')
    assert failed.error_code == 'model_error'
    assert 'private' not in failed.error_message
    assert service.ask('질문').rows == [[2]]


def test_requests_are_serialized_and_model_is_reused(db):
    state = {'loads': 0, 'active': 0, 'peak': 0}
    lock = Lock()
    class SlowGenerator:
        def generate(self, question):
            with lock:
                state['active'] += 1
                state['peak'] = max(state['peak'], state['active'])
            time.sleep(0.01)
            with lock:
                state['active'] -= 1
            return 'SELECT COUNT(*) FROM records'
    def factory():
        state['loads'] += 1
        return SlowGenerator()
    service = QuestionService(db, factory)
    with ThreadPoolExecutor(max_workers=3) as pool:
        answers = list(pool.map(service.ask, ['a', 'b', 'c']))
    assert all(answer.rows == [[2]] for answer in answers)
    assert state['loads'] == 1 and state['peak'] == 1


def test_sql_timeout_is_reported(db):
    sql = 'SELECT COUNT(*) FROM ' + ', '.join(f'records t{i}' for i in range(20))
    with pytest.raises(QueryTimeoutError):
        execute_query(db, sql, timeout_sec=0.000001)
    answer = QuestionService(db, lambda: Generator(sql), timeout_sec=0.000001).ask('질문')
    assert answer.error_code == 'query_timeout'
