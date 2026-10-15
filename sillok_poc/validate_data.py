"""Audit representative real XML files and build a separate validation database.

python -m sillok_poc.validate_data --help
No network access, source mutation, or inference is performed.
"""
import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3

from lxml import etree
from .database import insert_articles
from .xml_loader import bib, iter_articles, list_xml_files, lname, parse_article, _release_record


def audit_file(path):
    levels, types = Counter(), Counter()
    reasons = Counter()
    ids = set()
    duplicates = 0
    years, reigns = set(), set()
    accepted = 0
    for _, elem in etree.iterparse(str(path), events=("end",), resolve_entities=False,
                                  load_dtd=False, no_network=True):
        if not isinstance(elem.tag, str):
            continue
        name = lname(elem)
        if name.startswith("level"):
            levels[name] += 1
            metadata = bib(elem)
            types[f"{name}:{metadata.get('type') if metadata is not None else 'missing'}"] += 1
        if name == "level5":
            article = parse_article(elem)
            if article:
                accepted += 1
                duplicates += article.article_id in ids
                ids.add(article.article_id)
                years.add(article.year)
                reigns.add(article.reign)
            elif bib(elem) is None or bib(elem).get("type") != "T":
                reasons["not_type_T"] += 1
            else:
                reasons["missing_required_metadata"] += 1
        if name in {"level5", "level4", "level3", "level2"}:
            _release_record(elem)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return dict(file=str(path), sha256=digest.hexdigest(), levels=dict(levels),
                metadata_types=dict(types), accepted=accepted, skipped=dict(reasons),
                duplicate_ids=duplicates, reigns=sorted(reigns), years=sorted(years))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--db", default="data/validation.db")
    parser.add_argument("--output", default="reports/data-validation.json")
    args = parser.parse_args()
    root = Path(args.raw)
    # Annual records from three reigns plus introductory/appendix structures.
    names = ["2nd_waa_000.xml", "2nd_waa_101.xml", "2nd_waa_200.xml",
             "2nd_wba_101.xml", "2nd_wda_100.xml", "2nd_wda_101.xml"]
    paths = [root / name for name in names if (root / name).is_file()]
    if len(paths) != len(names):
        parser.error("대표 검증 파일이 없습니다. 공식 XML 데이터 경로를 확인하세요.")
    if Path(args.db).exists():
        parser.error("기존 DB를 덮어쓰지 않습니다. 새 --db 경로를 사용하세요.")
    reports = []
    for path in paths:
        print("검사:", path, flush=True)
        reports.append(audit_file(path))
    annual = [root / name for name in ["2nd_waa_101.xml", "2nd_wba_101.xml", "2nd_wda_101.xml"]]
    processed = insert_articles(args.db, itertools.chain.from_iterable(
        itertools.islice(iter_articles(path), 100) for path in annual))
    con = sqlite3.connect(Path(args.db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        count = con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        groups = con.execute("SELECT reign,year,COUNT(*) FROM records GROUP BY reign,year ORDER BY reign,year").fetchall()
        sample = con.execute("SELECT article_id,reign,year,date_raw,title_ko FROM records WHERE reign='태조' ORDER BY article_id LIMIT 5").fetchall()
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    result = dict(xml_file_count=len(list_xml_files(root)), scope="six representative files, not full corpus",
                  files=reports, validation_db=args.db, processed=processed,
                  stored=count, groups=groups, sample=sample, integrity=integrity)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
