# 面試前資料更新

2026-10-14 已從使用者授權的 `stock_agent` 資料庫，以唯讀交易匯出 8 檔股票最近 180 天行情與最多 300 則新聞。來源最新行情日期是 2026-10-14；本機快照含 981 筆行情、300 則新聞，最新新聞時間是 2026-10-14 16:35（台北時間）。來源資料庫未修改。本機 SQLite 與 PostgreSQL 已刷新，300 則新聞向量重新建立；圖譜針對最新 100 則重新抽取，其中 20 則產出 74 條原文證據。

下次更新順序：

1. 先確認來源資料可用，並備份 `data/demo/stocks.sqlite` 與本機 `stock_demo` 資料庫到忽略的 `.runtime/backups/`。
2. 用環境變數設定來源的 `PGHOST`、`PGPORT`、`PGDATABASE`、`PGUSER`、`PGPASSWORD`；執行 `uv run python scripts/export_snapshot.py`。不要把密碼寫進程式碼、Git 或命令紀錄。
3. 確認匯出日期和筆數後，啟動本機 PostgreSQL，執行 `uv run python scripts/refresh-postgres.py`。此步驟在一個交易中更換展示表，並清除過期的新聞向量及圖譜。
4. 啟動本機 Ollama，執行 `uv run python scripts/embed-news.py --limit 300` 及 `uv run python scripts/build-news-graph.py --limit 100`。這兩步只寫本機資料庫；模型抽取的關係仍需人工核對。
5. 執行 `uv run python scripts/verify_postgres.py`、`uv run pytest -q` 及 `uv run python scripts/smoke_demo.py`。在 `/api/status` 檢查日期、資料量、向量量、圖譜量與引擎；現場以工具紀錄確認實際來源。

本次驗證：9 組 SQLite/PostgreSQL 查詢一致、37 項自動測試通過；真模型五題（行情、比較、一般新聞、新聞圖譜、資料不足）的工具流程皆通過。三則台積電圖譜題實測呼叫 `search_news_graph`，回答附新聞 ID、日期及原文證據。`docs/local-results/` 保存本機測試結果和離線備援頁面，不會提交到 Git。

行情和新聞不是即時串流。隔天展示時應說「截至 2026-10-14 的本機快照」，不要稱為當下行情。`docs/local-results/demo-backup.html` 是事先實測備援，不是即時查詢。
