"""10 example questions with dynamically chosen king/year from actual DB.
Gold SQL is a starting point: manually review each pair before a formal evaluation.
"""
import json
import sqlite3
import time
from pathlib import Path
from .database import execute_readonly


def questions(db_path):
    con = sqlite3.connect(db_path)
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
        ("왕대별 기사 수를 알려줘.", "SELECT reign, COUNT(*) FROM records GROUP BY reign ORDER BY reign"),
        ("가장 많은 기사를 가진 왕대는?", "SELECT reign, COUNT(*) AS n FROM records GROUP BY reign ORDER BY n DESC, reign LIMIT 1"),
        ("기사 제목 다섯 개를 가나다순으로 보여줘.", "SELECT title_ko FROM records ORDER BY title_ko LIMIT 5"),
        ("제목에 '왕'이 들어가는 기사는 몇 건인가요?", "SELECT COUNT(*) FROM records WHERE title_ko LIKE '%왕%'"),
        ("군사로 분류된 기사는 몇 건인가요?", "SELECT COUNT(*) FROM records WHERE categories LIKE '%군사%'"),
        (f"{king} 시대 기사는 몇 건인가요?", f"SELECT COUNT(*) FROM records WHERE reign = '{king}'"),
        (f"서기 {year}년에 해당하는 기사는 몇 건인가요?", f"SELECT COUNT(*) FROM records WHERE year = {year}"),
    ]


def signature(rows):
    # Compare values rather than aliases; rows are unordered except for explicit ORDER BY.
    return sorted((tuple(map(str, r.values())) for r in rows))


def evaluate(db_path, output_path):
    from .model import TextToSQL
    model = TextToSQL()
    results = []
    for question, gold in questions(db_path):
        outcome = {"question": question, "gold_sql": gold}
        try:
            expected, _ = execute_readonly(db_path, gold)
            t0 = time.monotonic()
            generated = model.generate(question)
            model_latency = round(time.monotonic() - t0, 4)
            outcome["generated_sql"] = generated
            actual, sql_latency = execute_readonly(db_path, generated)
            outcome.update(correct=signature(expected) == signature(actual),
                           model_time_sec=model_latency, sql_time_sec=sql_latency, error=None)
        except Exception as exc:
            outcome.update(generated_sql=outcome.get("generated_sql"), correct=False, error=str(exc))
        results.append(outcome)
        print(f"{'OK' if outcome['correct'] else 'FAIL'}  {question}")
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True, parents=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"정확도(이 PoC 데이터에서만): {sum(x['correct'] for x in results)}/{len(results)}")
    print("보고서:", output_path)
