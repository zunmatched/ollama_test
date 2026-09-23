"""Local PostgreSQL adapter for the existing bounded read-only tools."""
import json
import re
from pathlib import Path

import httpx
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
        result["embedding_news_rows"] = self.query("SELECT COUNT(*) AS total FROM news_embeddings WHERE model=?", ("qwen3-embedding:0.6b",))[0]["total"]
        result["vector_search_enabled"] = result["embedding_news_rows"] > 0
        try:
            result["graph_news_rows"] = self.query("SELECT COUNT(DISTINCT news_id) AS total FROM graph_evidence")[0]["total"]
            result["graph_processed_rows"] = self.query("SELECT COUNT(*) AS total FROM graph_processed_news WHERE status='complete'")[0]["total"]
        except ToolError:
            result["graph_news_rows"] = 0
            result["graph_processed_rows"] = 0
        return result

    def search_news_graph(self, keyword: str, limit: int = 5) -> dict:
        self.limit(limit, 5)
        if not isinstance(keyword, str) or not 2 <= len(keyword.strip()) <= 60:
            raise ToolError("keyword 必須是 2–60 字的公司、產品、產業或事件名稱。")
        pattern = self.like(re.sub(r"\s+", "", keyword.strip()).casefold())
        try:
            rows = self.query("""SELECT n.id,n.title,n.url,n.published_at,n.source,
                s.kind AS subject_kind,s.name AS subject,r.predicate,
                o.kind AS object_kind,o.name AS object,e.excerpt AS evidence
                FROM graph_evidence e JOIN graph_relations r ON r.id=e.relation_id
                JOIN graph_entities s ON s.id=r.subject_id
                JOIN graph_entities o ON o.id=r.object_id
                JOIN news n ON n.id=e.news_id
                WHERE s.normalized_name LIKE ? ESCAPE '\\' OR o.normalized_name LIKE ? ESCAPE '\\'
                ORDER BY n.published_at DESC,n.id DESC LIMIT ?""",
                (pattern, pattern, limit))
        except ToolError:
            return {"source": "本機 PostgreSQL / 新聞圖譜", "found": False, "rows": [],
                    "note": "新聞圖譜尚未建立；請先執行 setup-graphrag.py。"}
        return {"source": "本機 PostgreSQL / 新聞圖譜", "retrieval": "實體名稱與原文證據查詢",
                "found": bool(rows), "rows": rows,
                "note": "關係由本機模型抽取，已核對證據為原文片段；仍可能有語意錯誤，請檢視來源。"}

    def search_news_semantic(self, question: str, limit: int = 3) -> dict:
        self.limit(limit, 5)
        if not isinstance(question, str) or not 2 <= len(question.strip()) <= 200:
            raise ToolError("question 必須是 2–200 字的新聞查詢。")
        model = "qwen3-embedding:0.6b"
        if not self.query("SELECT EXISTS(SELECT 1 FROM news_embeddings WHERE model=?) AS enabled", (model,))[0]["enabled"]:
            return {"source": "本機 PostgreSQL / news_embeddings", "found": False, "rows": [],
                    "note": "新聞向量尚未建立；請先執行 embed-news.py。"}
        try:
            with httpx.Client(timeout=60, trust_env=False) as client:
                response = client.post("http://127.0.0.1:11434/api/embed", json={
                    "model": model, "input": question.strip(), "keep_alive": "10m"})
                response.raise_for_status()
                vector = response.json()["embeddings"][0]
            if len(vector) != 1024:
                raise ToolError("查詢向量維度與新聞索引不一致。")
            rows = self.query("""SELECT n.id,n.title,substr(n.content,1,900) AS excerpt,
                n.url,n.published_at,n.source,
                round((e.embedding <=> ?::vector)::numeric,4) AS distance
                FROM news_embeddings e JOIN news n ON n.id=e.news_id
                WHERE e.model=? ORDER BY e.embedding <=> ?::vector LIMIT ?""",
                (json.dumps(vector), model, json.dumps(vector), limit))
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            raise ToolError("本機向量模型尚未就緒；請確認 embedding 模型已下載並建立新聞索引。") from None
        return {"source": "本機 PostgreSQL / news_embeddings", "retrieval": "Qwen3 embedding 餘弦距離",
                "found": bool(rows), "rows": rows,
                "note": "距離越低越相近；相似度不代表新聞內容真實或因果成立。"}
