import json
import sqlite3

from sillok_poc.database import insert_articles
from sillok_poc.evaluate import evaluate, signature
from sillok_poc.xml_loader import iter_articles
from test_core import FIXTURE


def test_evaluation_checks_order_and_never_accepts_truncated_results(tmp_path, monkeypatch):
    db = tmp_path / 'evaluation.db'
    insert_articles(db, iter_articles(FIXTURE))
    con = sqlite3.connect(db)
    with con:
        con.executemany('INSERT INTO records(article_id,reign,year,title_ko) VALUES (?,?,?,?)',
                        [(f'large_{i:05}', '태조', 1393, f'{i:05}') for i in range(10001)])
    con.close()
    monkeypatch.setattr('sillok_poc.evaluate.questions', lambda path: [
        ('ordered', 'SELECT title_ko FROM records ORDER BY title_ko LIMIT 2'),
        ('large', 'SELECT article_id FROM records'),
    ])
    class Model:
        def generate(self, question):
            return ('SELECT title_ko FROM records ORDER BY title_ko DESC LIMIT 2'
                    if question == 'ordered' else 'SELECT article_id FROM records')
    output = tmp_path/'results.json'
    results = evaluate(db, output, model=Model())
    assert results[0]['ordered'] and not results[0]['correct']
    assert results[1]['truncated'] and not results[1]['correct']
    assert results[1]['error'] == 'comparison_truncated'
    assert json.loads(output.read_text()) == results


def test_signature_distinguishes_null_from_text_and_preserves_duplicates():
    assert signature([[None]]) != signature([['None']])
    assert signature([[1], [1]]) != signature([[1]])
