"""Create a project-local PostgreSQL deployment and import the SQLite snapshot.

Secrets stay in ignored .runtime files. Existing populated databases are never overwritten.
"""
import json
import secrets
import sqlite3
import subprocess
import argparse
from pathlib import Path

import pg8000.dbapi

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wsl", action="store_true", help="Use Docker Engine in Ubuntu-22.04")
    options = parser.parse_args()
    RUNTIME.mkdir(exist_ok=True)
    secret_file = RUNTIME / "postgres-admin.json"
    if not secret_file.exists():
        secret_file.write_text(json.dumps({"password": secrets.token_urlsafe(32)}), encoding="utf-8")
    password = json.loads(secret_file.read_text(encoding="utf-8"))["password"]
    env_file = RUNTIME / "postgres.env"
    env_file.write_text("STOCK_ADMIN_PASSWORD=" + password + "\n", encoding="utf-8")
    if options.wsl:
        wsl_root = "/mnt/" + ROOT.drive[0].lower() + ROOT.as_posix()[2:]
        command = ["wsl", "-d", "Ubuntu-22.04", "--cd", wsl_root, "--", "docker", "compose", "--project-name", "ollama-stock", "--env-file", ".runtime/postgres.env", "up", "-d", "--wait"]
    else:
        command = ["docker", "compose", "--project-name", "ollama-stock", "--env-file", str(env_file), "up", "-d", "--wait"]
    subprocess.run(command, cwd=ROOT, check=True)
    conn = pg8000.dbapi.connect(host="127.0.0.1", port=55432, database="stock_demo", user="stock_admin", password=password, timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute("SELECT to_regclass('public.stocks')")
        if cur.fetchone()[0]:
            conn.commit()
            print("Existing database preserved; no snapshot overwritten.")
            return
        reader_password = secrets.token_urlsafe(32)
        # token_urlsafe uses no SQL quotes; this role is restricted to SELECT below.
        cur.execute("CREATE ROLE stock_reader LOGIN PASSWORD '" + reader_password + "'")
        cur.execute("ALTER ROLE stock_reader SET default_transaction_read_only = on")
        cur.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        cur.execute("CREATE TABLE stocks (ticker TEXT PRIMARY KEY, name TEXT, sector TEXT)")
        cur.execute("CREATE TABLE daily_prices (ticker TEXT, date TEXT, open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION, volume BIGINT, PRIMARY KEY(ticker,date))")
        cur.execute("CREATE TABLE news (id BIGINT PRIMARY KEY, title TEXT, content TEXT, url TEXT, published_at TEXT, source TEXT, tickers TEXT)")
        cur.execute("CREATE INDEX news_date ON news(published_at)")
        cur.execute("CREATE TABLE news_embeddings (news_id BIGINT PRIMARY KEY REFERENCES news(id), model TEXT NOT NULL, content_hash TEXT NOT NULL, embedding vector NOT NULL)")
        snapshot = ROOT / "data/demo/stocks.sqlite"
        with sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True) as source:
            for table in ("metadata", "stocks", "daily_prices", "news"):
                rows = source.execute("SELECT * FROM " + table).fetchall()
                if rows:
                    cur.executemany("INSERT INTO " + table + " VALUES (" + ",".join(["%s"] * len(rows[0])) + ")", rows)
                print(f"Imported {table}: {len(rows)} rows")
        cur.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        cur.execute("GRANT CONNECT ON DATABASE stock_demo TO stock_reader")
        cur.execute("GRANT USAGE ON SCHEMA public TO stock_reader")
        cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO stock_reader")
        reader = {"host": "127.0.0.1", "port": 55432, "database": "stock_demo", "user": "stock_reader", "password": reader_password}
        (RUNTIME / "postgres-reader.json").write_text(json.dumps(reader), encoding="utf-8")
        conn.commit()
        print("PostgreSQL + pgvector ready; vector search awaits a verified embedding model.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
