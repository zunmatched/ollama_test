"""Add the local news graph to an existing stock_demo database without touching source data."""
import json
from pathlib import Path

import pg8000.dbapi

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / ".runtime/postgres-admin.json"


def main():
    password = json.loads(ADMIN.read_text(encoding="utf-8"))["password"]
    conn = pg8000.dbapi.connect(host="127.0.0.1", port=55432, database="stock_demo",
                                user="stock_admin", password=password, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS graph_entities (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('company','product','industry','event')),
            name TEXT NOT NULL, normalized_name TEXT NOT NULL,
            UNIQUE(kind, normalized_name))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS graph_relations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            subject_id BIGINT NOT NULL REFERENCES graph_entities(id),
            predicate TEXT NOT NULL CHECK (predicate IN ('involved_in','affects','belongs_to')),
            object_id BIGINT NOT NULL REFERENCES graph_entities(id),
            UNIQUE(subject_id, predicate, object_id))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS graph_evidence (
            relation_id BIGINT NOT NULL REFERENCES graph_relations(id),
            news_id BIGINT NOT NULL REFERENCES news(id),
            excerpt TEXT NOT NULL, extraction_model TEXT NOT NULL, content_hash TEXT NOT NULL,
            PRIMARY KEY(relation_id, news_id, excerpt))""")
        cur.execute("""CREATE TABLE IF NOT EXISTS graph_processed_news (
            news_id BIGINT PRIMARY KEY REFERENCES news(id),
            content_hash TEXT NOT NULL, extraction_model TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('complete','failed')),
            error TEXT, processed_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        cur.execute("CREATE INDEX IF NOT EXISTS graph_entity_name ON graph_entities(normalized_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS graph_evidence_news ON graph_evidence(news_id)")
        cur.execute("GRANT SELECT ON graph_entities, graph_relations, graph_evidence, graph_processed_news TO stock_reader")
        conn.commit()
        print("News graph schema ready; original news and prices unchanged.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
