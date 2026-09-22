"""Local PostgreSQL adapter for the existing bounded read-only tools."""
import json
from pathlib import Path

import pg8000.dbapi

from src.tools import StockTools, ToolError


class PostgresTools(StockTools):
    def __init__(self, config_path: Path):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        # SQL comes exclusively from the fixed tool implementation, never the model.
        sql = sql.replace("json_each(news.tickers)", "jsonb_array_elements_text(news.tickers::jsonb) AS tags(value)")
        sql = sql.replace("? IS NULL", "CAST(? AS TEXT) IS NULL")
        sql = sql.replace("%", "%%").replace("?", "%s")
        try:
            conn = pg8000.dbapi.connect(**self.config, timeout=5)
            try:
                cur = conn.cursor()
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute(sql, args)
                return [dict(zip([c[0] for c in cur.description], row)) for row in cur.fetchall()]
            finally:
                conn.close()
        except pg8000.dbapi.Error:
            raise ToolError("本機 PostgreSQL 查詢失敗，請確認資料庫已啟動。") from None

    def metadata(self) -> dict:
        result = super().metadata()
        result["database_backend"] = "PostgreSQL + pgvector"
        result["vector_search_enabled"] = False
        return result
