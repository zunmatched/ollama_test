"""Export bounded market data; credentials come only from env or a hidden prompt."""
import getpass
import json
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pg8000.dbapi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DB_PATH

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE stocks (ticker TEXT PRIMARY KEY, name TEXT, sector TEXT);
CREATE TABLE daily_prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL,
    close REAL, volume INTEGER, PRIMARY KEY (ticker,date));
CREATE TABLE news (id INTEGER PRIMARY KEY, title TEXT, content TEXT, url TEXT,
    published_at TEXT, source TEXT, tickers TEXT);
CREATE INDEX news_date ON news(published_at);
"""


def main():
    required = ["PGHOST", "PGDATABASE", "PGUSER"]
    if any(not os.environ.get(key) for key in required):
        raise SystemExit("請設定 PGHOST、PGDATABASE、PGUSER。密碼由 PGPASSWORD 或隱藏提示輸入。")
    password = os.environ.get("PGPASSWORD") or getpass.getpass("PostgreSQL password: ")
    selected = ["2330", "2303", "2454", "2344", "2408", "2337", "8046", "2002"]
    remote = pg8000.dbapi.connect(host=os.environ["PGHOST"], port=int(os.environ.get("PGPORT", "5432")),
        database=os.environ["PGDATABASE"], user=os.environ["PGUSER"], password=password, timeout=20)
    try:
        cur = remote.cursor()
        cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '20s'")
        cur.execute("SELECT max(date) FROM public.daily_prices")
        latest = cur.fetchone()[0]
        if latest is None:
            raise RuntimeError("daily_prices 沒有資料。")
        earliest = latest - timedelta(days=180)
        placeholders = ",".join(["%s"] * len(selected))
        cur.execute(f"SELECT ticker,name,sector FROM public.stocks WHERE ticker IN ({placeholders}) ORDER BY ticker", selected)
        stocks = cur.fetchall()
        cur.execute(f"SELECT ticker,date,open,high,low,close,volume FROM public.daily_prices "
                    f"WHERE ticker IN ({placeholders}) AND date BETWEEN %s AND %s ORDER BY ticker,date",
                    selected + [earliest, latest])
        prices = cur.fetchall()
        cur.execute("SELECT id,title,left(content,4000),url,published_at,source,tickers FROM public.news "
                    "WHERE published_at IS NOT NULL AND (tickers::text[] && %s::text[] OR title ILIKE %s) "
                    "ORDER BY published_at DESC LIMIT 300", [selected, "%記憶體%"])
        news = cur.fetchall()
        remote.rollback()
    finally:
        remote.close()
    if not stocks or not prices:
        raise RuntimeError("選定股票沒有資料；未覆蓋既有快照。")
    metadata = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source": "使用者授權的 PostgreSQL stock_agent 市場資料快照",
        "mode": "offline_snapshot", "price_rows": len(prices), "news_rows": len(news),
        "price_first_date": str(min(row[1] for row in prices)),
        "price_last_date": str(max(row[1] for row in prices)),
        "news_last_date": str(max((row[4] for row in news), default="")),
        "retrieval": "keyword", "price_adjustment": "未驗證", "volume_unit": "未驗證",
    }
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = DB_PATH.with_suffix(".tmp.sqlite")
    if temporary.exists():
        raise RuntimeError("上次暫存快照仍存在，請確認後移除 stocks.tmp.sqlite。")
    try:
        with closing(sqlite3.connect(temporary)) as local:
            local.executescript(SCHEMA)
            local.executemany("INSERT INTO stocks VALUES (?,?,?)", stocks)
            local.executemany("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", [
                (r[0], str(r[1]), *(float(v) if v is not None else None for v in r[2:6]), r[6]) for r in prices])
            local.executemany("INSERT INTO news VALUES (?,?,?,?,?,?,?)", [
                (r[0], r[1], r[2] or "", r[3], r[4].isoformat(), r[5], json.dumps(r[6] or [], ensure_ascii=False)) for r in news])
            local.executemany("INSERT INTO metadata VALUES (?,?)", [
                (key, json.dumps(value, ensure_ascii=False)) for key,value in metadata.items()])
            local.commit()
        temporary.replace(DB_PATH)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
