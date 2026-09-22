"""Integration check against the local imported snapshot; never prints records or secrets."""
import sys
from pathlib import Path

import pg8000.dbapi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.postgres_tools import PostgresTools
from src.tools import StockTools


def main():
    pg = PostgresTools(ROOT / ".runtime/postgres-reader.json")
    sqlite = StockTools()
    cases = [
        ("find_stocks", {"keyword": "台積電"}),
        ("find_stocks", {"keyword": "' OR 1=1 --"}),
        ("find_stocks", {"keyword": "%"}),
        ("get_prices", {"ticker": "2330"}),
        ("get_prices", {"ticker": "2330", "start_date": "2030-01-01", "end_date": "2030-01-01"}),
        ("compare_stocks", {"tickers": ["2330", "2303"], "start_date": "2026-09-01", "end_date": "2026-09-21"}),
        ("search_news", {"ticker": "2330"}),
        ("search_news", {"keyword": "記憶體"}),
        ("search_news", {"keyword": "記憶體", "ticker": "2330"}),
    ]
    for name, args in cases:
        expected = sqlite.execute(name, args)
        actual = pg.execute(name, args)
        assert "error" not in actual, (name, actual)
        assert actual == expected, name
    assert pg.query("SELECT extversion FROM pg_extension WHERE extname='vector'")[0]["extversion"]
    assert pg.query("SELECT '[1,0,0]'::vector <=> '[1,0,0]'::vector AS distance")[0]["distance"] == 0
    conn = pg8000.dbapi.connect(**pg.config)
    try:
        cur = conn.cursor()
        cur.execute("SET TRANSACTION READ WRITE")
        try:
            cur.execute("DELETE FROM stocks WHERE false")
        except pg8000.dbapi.DatabaseError as exc:
            assert exc.args[0].get("C") == "42501", "Expected insufficient privilege"
        else:
            raise AssertionError("Reader unexpectedly has write permission")
    finally:
        conn.rollback()
        conn.close()
    print("PASS: 9 SQLite/PostgreSQL parity cases, pgvector cosine distance, reader write denial")
    print({key: pg.metadata()[key] for key in ("price_rows", "news_rows", "database_backend")})


if __name__ == "__main__":
    main()
