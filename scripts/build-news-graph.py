"""Extract an evidence-backed news graph with local Ollama; resumable by content hash."""
import argparse
import hashlib
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pg8000.dbapi

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.5:4b"
EXTRACTOR = MODEL + "/news-graph-v2"
KINDS = {"company", "product", "industry", "event"}
PREDICATES = {
    "involved_in": ("company", "event"),
    "affects": ("event", "product"),
    "belongs_to": ("company", "industry"),
}


class _TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"p", "br", "li", "div"}:
            self.parts.append("\n")


def clean_news(content):
    parser = _TextOnly()
    parser.feed(html.unescape(content or ""))
    return re.sub(r"[ \t]+", " ", "".join(parser.parts)).strip()


def verbatim_excerpt(source, candidate):
    """Recover exact source characters when the model changes whitespace only."""
    indexed = [(index, char) for index, char in enumerate(source) if not char.isspace()]
    compact_source = "".join(char for _, char in indexed)
    compact_candidate = "".join(char for char in candidate if not char.isspace())
    offset = compact_source.find(compact_candidate)
    if offset < 0 or not compact_candidate:
        return None
    return source[indexed[offset][0]:indexed[offset + len(compact_candidate) - 1][0] + 1]


def validate_relations(value, source):
    """Accept only short, verbatim-supported edges with a fixed relation vocabulary."""
    if not isinstance(value, dict) or not isinstance(value.get("relations"), list):
        raise ValueError("Model did not return a relations array")
    result = []
    for item in value["relations"][:6]:
        if not isinstance(item, dict):
            continue
        try:
            subject, obj = item["subject"], item["object"]
            predicate, excerpt = item["predicate"], item["evidence"]
            if not all(isinstance(part, dict) for part in (subject, obj)):
                continue
            subject_kind, object_kind = subject["kind"], obj["kind"]
            subject_name, object_name = subject["name"].strip(), obj["name"].strip()
            if (subject_kind not in KINDS or object_kind not in KINDS or
                PREDICATES.get(predicate) != (subject_kind, object_kind) or
                not 2 <= len(subject_name) <= 80 or not 2 <= len(object_name) <= 80 or
                not isinstance(excerpt, str) or not 8 <= len(excerpt) <= 180 or
                (subject_kind != "event" and normalize(subject_name) not in normalize(source)) or
                (object_kind != "event" and normalize(object_name) not in normalize(source))):
                continue
            excerpt = verbatim_excerpt(source, excerpt)
            if excerpt is None:
                continue
        except (KeyError, AttributeError, TypeError):
            continue
        result.append((subject_kind, subject_name, predicate, object_kind, object_name, excerpt))
    return result


def normalize(name):
    return re.sub(r"\s+", "", name).casefold()


def entity_id(cur, kind, name):
    cur.execute("""INSERT INTO graph_entities(kind,name,normalized_name) VALUES (%s,%s,%s)
        ON CONFLICT(kind,normalized_name) DO UPDATE SET name=graph_entities.name RETURNING id""",
        (kind, name, normalize(name)))
    return cur.fetchone()[0]


def save_relations(cur, news_id, digest, relations):
    cur.execute("DELETE FROM graph_evidence WHERE news_id=%s", (news_id,))
    for subject_kind, subject_name, predicate, object_kind, object_name, excerpt in relations:
        subject = entity_id(cur, subject_kind, subject_name)
        obj = entity_id(cur, object_kind, object_name)
        cur.execute("""INSERT INTO graph_relations(subject_id,predicate,object_id)
            VALUES (%s,%s,%s) ON CONFLICT(subject_id,predicate,object_id)
            DO UPDATE SET predicate=graph_relations.predicate RETURNING id""", (subject, predicate, obj))
        relation_id = cur.fetchone()[0]
        cur.execute("""INSERT INTO graph_evidence(relation_id,news_id,excerpt,extraction_model,content_hash)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (relation_id, news_id, excerpt, EXTRACTOR, digest))
    cur.execute("""INSERT INTO graph_processed_news(news_id,content_hash,extraction_model,status,error)
        VALUES (%s,%s,%s,'complete',NULL) ON CONFLICT(news_id) DO UPDATE SET
        content_hash=EXCLUDED.content_hash, extraction_model=EXCLUDED.extraction_model,
        status='complete', error=NULL, processed_at=now()""", (news_id, digest, EXTRACTOR))


def extract(client, title, content):
    source = title + "\n" + clean_news(content)
    prompt = ("從以下新聞抽取最多六條有原文證據的關係。只用明確提及的資訊；"
              "不推測股價、因果或投資結論。實體 kind 僅用 company/product/industry/event。"
              "關係僅用 company involved_in event、event affects product、"
              "company belongs_to industry。evidence 必須是新聞中連續且完全相同的原文，8 到 180 字。"
              "沒有可靠關係就回傳空陣列。輸出 JSON："
              '{"relations":[{"subject":{"kind":"company","name":"..."},'
              '"predicate":"involved_in","object":{"kind":"event","name":"..."},'
              '"evidence":"原文片段"}]}\n\n新聞：\n' + source)
    response = client.post("http://127.0.0.1:11434/api/chat", json={
        "model": MODEL, "messages": [{"role": "user", "content": prompt}],
        "stream": False, "think": False, "format": "json", "keep_alive": "10m",
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 1200}})
    response.raise_for_status()
    return validate_relations(json.loads(response.json()["message"]["content"]), source)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="Maximum articles this run (default: 30)")
    args = parser.parse_args()
    if not 1 <= args.limit <= 300:
        parser.error("--limit must be between 1 and 300")
    password = json.loads((ROOT / ".runtime/postgres-admin.json").read_text(encoding="utf-8"))["password"]
    conn = pg8000.dbapi.connect(host="127.0.0.1", port=55432, database="stock_demo",
                                user="stock_admin", password=password, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("""SELECT n.id,n.title,n.content,p.content_hash,p.extraction_model,p.status
            FROM news n LEFT JOIN graph_processed_news p ON p.news_id=n.id
            ORDER BY n.published_at DESC LIMIT %s""", (args.limit,))
        articles = cur.fetchall()
        conn.rollback()
        with httpx.Client(timeout=180, trust_env=False) as client:
            for index, (news_id, title, content, previous_hash, previous_model, status) in enumerate(articles, 1):
                title, content = title or "", content or ""
                digest = hashlib.sha256((title + "\n" + content).encode()).hexdigest()
                if (previous_hash, previous_model, status) == (digest, EXTRACTOR, "complete"):
                    print(f"{index}/{len(articles)} news {news_id}: unchanged")
                    continue
                try:
                    relations = extract(client, title, content)
                    save_relations(cur, news_id, digest, relations)
                    conn.commit()
                    print(f"{index}/{len(articles)} news {news_id}: {len(relations)} verified relations")
                except (httpx.HTTPError, ValueError, KeyError, pg8000.dbapi.Error) as exc:
                    conn.rollback()
                    print(f"{index}/{len(articles)} news {news_id}: failed ({type(exc).__name__})")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
