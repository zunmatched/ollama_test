"""Fill the local pgvector table with repeatable Ollama article embeddings."""
import argparse
import hashlib
import json
from pathlib import Path

import httpx
import pg8000.dbapi

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3-embedding:0.6b"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.limit <= 300:
        parser.error("--limit must be between 1 and 300")
    password = json.loads((ROOT / ".runtime/postgres-admin.json").read_text(encoding="utf-8"))["password"]
    conn = pg8000.dbapi.connect(host="127.0.0.1", port=55432, database="stock_demo",
                                user="stock_admin", password=password, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("""SELECT n.id,n.title,n.content,e.model,e.content_hash
            FROM news n LEFT JOIN news_embeddings e ON e.news_id=n.id
            ORDER BY n.published_at DESC LIMIT %s""", (args.limit,))
        articles = cur.fetchall()
        conn.rollback()
        with httpx.Client(timeout=120, trust_env=False) as client:
            for index, (news_id, title, content, previous_model, previous_hash) in enumerate(articles, 1):
                content = (title or "") + "\n" + (content or "")
                digest = hashlib.sha256(content.encode()).hexdigest()
                if (previous_model, previous_hash) == (MODEL, digest):
                    print(f"{index}/{len(articles)} news {news_id}: unchanged")
                    continue
                response = client.post("http://127.0.0.1:11434/api/embed", json={
                    "model": MODEL, "input": content, "keep_alive": "10m"})
                response.raise_for_status()
                vector = response.json()["embeddings"][0]
                if len(vector) != 1024:
                    raise ValueError(f"Expected 1024 dimensions, got {len(vector)}")
                cur.execute("""INSERT INTO news_embeddings(news_id,model,content_hash,embedding)
                    VALUES (%s,%s,%s,%s::vector) ON CONFLICT(news_id) DO UPDATE SET
                    model=EXCLUDED.model,content_hash=EXCLUDED.content_hash,
                    embedding=EXCLUDED.embedding""", (news_id, MODEL, digest, json.dumps(vector)))
                conn.commit()
                print(f"{index}/{len(articles)} news {news_id}: embedded")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
