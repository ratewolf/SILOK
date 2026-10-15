"""Parse standard regnal-year level5 article records from Sillok XML.

Do not treat appendix/introductory level3 records as ordinary articles.
XML schema must be checked against the files actually downloaded.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

YEAR_RE = re.compile(r"^(\d{4})(?:\D|$)")
REIGN_RE = re.compile(r"^\s*([^\s\d]+)\s*(?:즉위년|\d+\s*년?)")


def lname(elem):
    return etree.QName(elem).localname


def child(elem, tag):
    if elem is None:
        return None
    return next((node for node in elem if isinstance(node.tag, str) and lname(node) == tag), None)


def children(elem, tag):
    if elem is None:
        return []
    return [node for node in elem if isinstance(node.tag, str) and lname(node) == tag]


def find_path(elem, *path):
    for name in path:
        elem = child(elem, name)
    return elem


def node_text(elem):
    return " ".join("".join(elem.itertext()).split()) if elem is not None else ""


def bib(elem):
    return find_path(elem, "front", "biblioData")


def dates_in(elem):
    b = bib(elem)
    return children(child(b, "date"), "dateOccured")


def extract_year(*elems):
    for elem in elems:
        for d in dates_in(elem):
            if d.get("type") == "서기":
                m = YEAR_RE.match((d.get("date") or "").strip())
                if m:
                    return int(m.group(1)), d.get("date")
    return None, None


def extract_reign(*elems):
    for elem in elems:
        for d in dates_in(elem):
            if d.get("type") == "재위연도":
                m = REIGN_RE.match(node_text(d))
                if m:
                    return m.group(1)
    return None


@dataclass
class Article:
    article_id: str
    reign: str
    year: int
    date_raw: str
    title_ko: str
    original_text: str
    categories: str


def parse_article(article, assumed_reign=None):
    b = bib(article)
    if b is None or b.get("type") != "T":
        return None
    title = node_text(find_path(b, "title", "mainTitle"))
    article_id = article.get("id")
    parents = list(article.iterancestors())
    year, date_raw = extract_year(article, *parents)
    reign = extract_reign(article, *parents) or assumed_reign
    categories = "; ".join(node_text(x) for x in children(b, "subjectClass"))
    original_text = node_text(child(article, "text"))
    # Do not silently import incomplete records or invent a reign/year.
    if not (article_id and title and year and reign):
        return None
    return Article(article_id, reign, year, date_raw or "", title, original_text, categories)


def iter_articles(xml_path, assumed_reign=None):
    """Stream level5 nodes to avoid loading entire multi-year files into memory."""
    context = etree.iterparse(
        str(xml_path), events=("end",), resolve_entities=False,
        load_dtd=False, no_network=True, huge_tree=False,
    )
    for _, elem in context:
        if not isinstance(elem.tag, str):
            continue
        if lname(elem) == "level5":
            article = parse_article(elem, assumed_reign)
            if article is not None:
                yield article
            _release_record(elem)
        elif lname(elem) in {"level4", "level3", "level2"}:
            _release_record(elem)


def _release_record(elem):
    # Remove only the completed record. Earlier siblings include the parent's
    # front/biblioData, which later articles still need for inherited metadata.
    parent = elem.getparent()
    elem.clear()
    if parent is not None:
        parent.remove(elem)


def list_xml_files(path):
    path = Path(path)
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.xml")) + sorted(path.rglob("*.XML"))
