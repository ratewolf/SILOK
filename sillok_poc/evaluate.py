"""10 example questions with dynamically chosen king/year from actual DB.
Gold SQL is a starting point: manually review each pair before a formal evaluation.
"""
import json
import sqlite3
import time
from pathlib import Path
from .database import execute_query


def questions(db_path):
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"DB가 없습니다: {db_path}")
    con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        pair = con.execute("SELECT reign, year FROM records ORDER BY article_id LIMIT 1").fetchone()
        if not pair:
            raise ValueError("데이터가 없습니다. XML 적재부터 진행하세요.")
    finally:
        con.close()
    king, year = pair
    return [
        ("전체 기사는 몇 건인가요?", "SELECT COUNT(*) FROM records"),
        ("가장 이른 서기 연도는 언제인가요?", "SELECT MIN(year) FROM records"),
        ("가장 늦은 서기 연도는 언제인가요?", "SELECT MAX(year) FROM records"),
        ("왕대별 기사 수를 왕대 이름순으로 알려줘.", "SELECT reign, COUNT(*) FROM records GROUP BY reign ORDER BY reign"),
        ("가장 많은 기사를 가진 왕대와 기사 수를 알려줘. 동률이면 왕대 이름순으로 하나만 보여줘.", "SELECT reign, COUNT(*) AS n FROM records GROUP BY reign ORDER BY n DESC, reign LIMIT 1"),
        ("기사 제목 다섯 개를 가나다순으로 보여줘.", "SELECT title_ko FROM records ORDER BY title_ko LIMIT 5"),
        ("제목에 '왕'이 들어가는 기사는 몇 건인가요?", "SELECT COUNT(*) FROM records WHERE title_ko LIKE '%왕%'"),
        ("군사로 분류된 기사는 몇 건인가요?", "SELECT COUNT(*) FROM records WHERE categories LIKE '%군사%'"),
        (f"{king} 시대 기사는 몇 건인가요?", f"SELECT COUNT(*) FROM records WHERE reign = '{king}'"),
        (f"서기 {year}년에 해당하는 기사는 몇 건인가요?", f"SELECT COUNT(*) FROM records WHERE year = {year}"),
    ]


def signature(rows):
    # Keep scalar types (NULL is distinct from the text "None") and duplicate rows.
    return sorted((tuple(row) for row in rows), key=repr)


def evaluate(db_path, output_path, model=None):
    if model is None:
        from .model import TextToSQL
        model = TextToSQL()
    results = []
    for question, gold in questions(db_path):
        outcome = {"question": question, "gold_sql": gold}
        try:
            expected = execute_query(db_path, gold, max_rows=10000)
            t0 = time.monotonic()
            generated = model.generate(question)
            model_latency = round(time.monotonic() - t0, 4)
            outcome["generated_sql"] = generated
            actual = execute_query(db_path, generated, max_rows=10000)
            ordered = "ORDER BY" in gold.upper()
            truncated = expected.truncated or actual.truncated
            same = (expected.rows == actual.rows if ordered else
                    signature(expected.rows) == signature(actual.rows))
            outcome.update(correct=same and not truncated,
                           failure_type=("comparison_truncated" if truncated else
                                         None if same else "result_mismatch"),
                           expected_columns=expected.columns, actual_columns=actual.columns,
                           expected_row_count=len(expected.rows), actual_row_count=len(actual.rows),
                           ordered=ordered, truncated=truncated,
                           model_time_sec=model_latency, sql_time_sec=actual.sql_time_sec,
                           error="comparison_truncated" if truncated else None)
        except Exception as exc:
            outcome.update(generated_sql=outcome.get("generated_sql"), correct=False,
                           failure_type=type(exc).__name__, error=str(exc))
        results.append(outcome)
        print(f"{'OK' if outcome['correct'] else 'FAIL'}  {question}")
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True, parents=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"정확도(이 PoC 데이터에서만): {sum(x['correct'] for x in results)}/{len(results)}")
    print("보고서:", output_path)

    return results
