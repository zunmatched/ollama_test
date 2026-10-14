"""Replace the local demo data with the verified SQLite export in one transaction.

Run after export_snapshot.py. This touches only local stock_demo, never the source DB.
Rebuild news embeddings and graph after running it.
"""
import json
import sqlite3
from pathlib import Path

import pg8000.dbapi

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("metadata", "stocks", "daily_prices", "news")


def main():
    snapshot = ROOT / "data/demo/stocks.sqlite"
    with sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True) as source:
        rows = {table: source.execute(f"SELECT * FROM {table}").fetchall() for table in TABLES}
    if len(rows["stocks"]) != 8 or not rows["daily_prices"] or not rows["news"]:
        raise RuntimeError("Snapshot is incomplete; local PostgreSQL was not modified.")
    metadata = {key: json.loads(value) for key, value in rows["metadata"]}
    if (metadata.get("price_rows") != len(rows["daily_prices"]) or
            metadata.get("news_rows") != len(rows["news"])):
        raise RuntimeError("Snapshot counts do not match metadata; local PostgreSQL was not modified.")

    password = json.loads((ROOT / ".runtime/postgres-admin.json").read_text(encoding="utf-8"))["password"]
    conn = pg8000.dbapi.connect(host="127.0.0.1", port=55432, database="stock_demo",
                                user="stock_admin", password=password, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = '120s'")
        # Dependency order matters; a failure rolls back the complete replacement.
        for table in ("graph_evidence", "graph_processed_news", "graph_relations",
                      "graph_entities", "news_embeddings", "news", "daily_prices", "stocks", "metadata"):
            cur.execute(f"DELETE FROM {table}")
        for table in TABLES:
            values = rows[table]
            placeholders = ",".join(["%s"] * len(values[0]))
            cur.executemany(f"INSERT INTO {table} VALUES ({placeholders})", values)
        for table in TABLES:
            cur.execute(f"SELECT count(*) FROM {table}")
            if cur.fetchone()[0] != len(rows[table]):
                raise RuntimeError(f"Row count mismatch in {table}; rolling back.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f"Local PostgreSQL refreshed: {len(rows['stocks'])} stocks, "
          f"{len(rows['daily_prices'])} prices through {metadata['price_last_date']}, "
          f"{len(rows['news'])} news through {metadata['news_last_date']}.")
    print("News embeddings and graph are now empty; rebuild them before demo.")


if __name__ == "__main__":
    main()
