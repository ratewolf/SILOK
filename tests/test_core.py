import sqlite3
from pathlib import Path
import pytest

from sillok_poc.xml_loader import iter_articles
from sillok_poc.database import insert_articles, execute_readonly

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic.xml"


def test_xml_import_and_query(tmp_path):
    records = list(iter_articles(FIXTURE))
    assert len(records) == 2
    assert records[0].reign == "태조"
    assert records[0].year == 1393
    assert records[0].date_raw == "1393-01-06L0"
    assert records[1].date_raw == "1393-01-06L0"
    assert records[0].categories == "군사-관방"
    db = tmp_path / "test.db"
    assert insert_articles(db, records) == 2
    rows, _ = execute_readonly(db, "SELECT COUNT(*) AS n FROM records")
    assert rows == [{"n": 2}]
    rows, _ = execute_readonly(db, "SELECT title_ko FROM records WHERE reign = '태조' ORDER BY title_ko")
    assert len(rows) == 2


@pytest.mark.parametrize("sql", [
    "DELETE FROM records", "DROP TABLE records",
    "SELECT * FROM sqlite_master", "SELECT load_extension('evil')",
    "SELECT * FROM records; DROP TABLE records",
    "WITH a AS (DELETE FROM records RETURNING *) SELECT * FROM a"
])
def test_unsafe_query_rejected(tmp_path, sql):
    db = tmp_path / "test.db"
    insert_articles(db, iter_articles(FIXTURE))
    with pytest.raises((ValueError, sqlite3.Error)):
        execute_readonly(db, sql)


def test_ten_gold_queries_run(tmp_path):
    from sillok_poc.evaluate import questions
    db = tmp_path / "test.db"
    insert_articles(db, iter_articles(FIXTURE))
    all_questions = questions(db)
    assert len(all_questions) == 10
    for question, sql in all_questions:
        rows, _ = execute_readonly(db, sql)
        assert rows is not None, question


def test_streaming_preserves_metadata_across_days_and_months(tmp_path):
    from copy import deepcopy
    from lxml import etree
    root = etree.parse(str(FIXTURE)).getroot()
    month = root.find("level3")
    day = month.find("level4")
    next_day = deepcopy(day)
    next_day.set("id", "fake_next_day")
    next_day.find("front/biblioData/date/dateOccured").set("date", "1393-01-07L0")
    for index, article in enumerate(next_day.findall("level5")):
        article.set("id", f"fake_next_day_{index}")
    month.append(next_day)
    next_month = deepcopy(month)
    for index, article in enumerate(next_month.iter("level5")):
        article.set("id", f"fake_next_month_{index}")
    root.append(next_month)
    path = tmp_path / "months.xml"
    path.write_bytes(etree.tostring(root))
    records = list(iter_articles(path))
    assert len(records) == 8
    assert {r.reign for r in records} == {"태조"}
    assert [r.date_raw for r in records] == [
        "1393-01-06L0", "1393-01-06L0", "1393-01-07L0", "1393-01-07L0",
    ] * 2
