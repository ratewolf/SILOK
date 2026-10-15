"""Usage: python -m sillok_poc --help"""
import argparse
import json
from pathlib import Path
from .xml_loader import iter_articles, list_xml_files
from .database import insert_articles, execute_readonly

DEFAULT_DB = "data/sillok_poc.db"


def inspect(path, assumed_reign):
    files = list_xml_files(path)
    print("XML 파일 수:", len(files))
    for f in files[:3]:
        print("파일:", f)
        try:
            for a in iter_articles(f, assumed_reign=assumed_reign):
                print("샘플:", a.article_id, a.reign, a.year, a.date_raw, a.title_ko,
                      "분류:", a.categories[:50], "본문:", a.original_text[:50])
                break
        except Exception as exc:
            print("읽기 실패:", type(exc).__name__, str(exc))


def import_files(path, db_path, limit, assumed_reign):
    files = list_xml_files(path)
    if not files:
        raise FileNotFoundError(f"XML 파일을 찾지 못했습니다: {path}")
    def articles():
        n = 0
        for f in files:
            for a in iter_articles(f, assumed_reign=assumed_reign):
                yield a
                n += 1
                if n >= limit:
                    return
    n = insert_articles(db_path, articles())
    print(f"처리한 기사: {n}건 (중복 ID는 교체), DB: {db_path}")


def main():
    p = argparse.ArgumentParser(description="Sillok XML→SQLite→Text-to-SQL PoC")
    sp = p.add_subparsers(dest="cmd", required=True)
    ins = sp.add_parser("inspect", help="XML 첫 기사 미리 보기")
    ins.add_argument("path")
    ins.add_argument("--reign", help="추출 불가시 왕대 보정 (실제 자료 검증 후만 사용)")
    imp = sp.add_parser("import", help="XML에서 기사 100건 적재")
    imp.add_argument("path")
    imp.add_argument("--limit", type=int, default=100)
    imp.add_argument("--db", default=DEFAULT_DB)
    imp.add_argument("--reign")
    qry = sp.add_parser("query", help="직접 작성한 SQL로 데이터 조회")
    qry.add_argument("sql")
    qry.add_argument("--db", default=DEFAULT_DB)
    ask = sp.add_parser("ask", help="GPU 모델로 SQL 생성 + 조회")
    ask.add_argument("question")
    ask.add_argument("--db", default=DEFAULT_DB)
    ev = sp.add_parser("evaluate", help="GPU 모델을 10개 질문으로 평가")
    ev.add_argument("--db", default=DEFAULT_DB)
    ev.add_argument("--output", default="reports/evaluation.json")
    args = p.parse_args()
    if args.cmd == "inspect":
        inspect(args.path, args.reign)
    elif args.cmd == "import":
        import_files(args.path, args.db, args.limit, args.reign)
    elif args.cmd == "query":
        rows, sec = execute_readonly(args.db, args.sql)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        print("SQL 실행시간(초):", sec)
    elif args.cmd == "ask":
        from .model import TextToSQL
        model = TextToSQL()
        sql = model.generate(args.question)
        print("생성 SQL:", sql)
        rows, sec = execute_readonly(args.db, sql)
        print("결과:", json.dumps(rows, ensure_ascii=False, indent=2), "시간:", sec)
    elif args.cmd == "evaluate":
        from .evaluate import evaluate
        evaluate(args.db, args.output)

if __name__ == "__main__":
    main()
