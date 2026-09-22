# 本機 PostgreSQL + pgvector

本機展示現在可使用 PostgreSQL 17 + pgvector 0.8.6，資料仍是有限快照。遠端原始資料库沒有被修改。

## 這台筆電

- 雙擊 `start-demo.cmd`：存在本機 PostgreSQL 設定時，自動使用 PostgreSQL。
- 雙擊 `start-sqlite.cmd`：切換回 SQLite 備援；執行中的問題需先結束。
- 網頁：`http://127.0.0.1:8765/`，架構區會顯示實際資料庫。
- 本機資料庫：`127.0.0.1:55432`，database `stock_demo`，查詢帳號 `stock_reader`。
- 密碼只存在忽略的 `.runtime/postgres-reader.json`，不要提交或貼到投影片。

Docker Desktop 本次因殘留通訊檔案啟動失敗，因此改用 **WSL Ubuntu-22.04 內既有的 Docker Engine**。啟動腳本保留一個隱藏的 WSL 程序，避免 WSL 閒置退出。容器使用 `ollama-stock` Compose project 與 `ollama-stock_stock_pgdata` volume；停止容器不會刪除資料。不要使用 `docker compose down -v`。

## 重建與驗證

需要已有 SQLite 快照、Python 依賴與可用的 WSL Docker Engine：

```powershell
uv run python scripts/setup-postgres.py --wsl
uv run python scripts/verify_postgres.py
powershell -File scripts/start.ps1 -NoBrowser -Backend postgres
uv run python scripts/smoke_demo.py
```

首次下載映像需要網路。部署腳本生成隨機密碼，首次匯入在一個交易內完成；偵測到既有資料表就保留資料，不自動覆蓋。原生 Docker Engine 環境可以省略 `--wsl`，但這台筆電的啟動腳本使用 WSL。

## 權限與向量狀態

查詢帳號只有 SELECT 權限，預設唯讀交易；程式也強制唯讀、5 秒查詢限制與固定參數化 SQL。容器只發布在本機 loopback。

pgvector 已啟用並通過餘弦距離運算測試。`news_embeddings` 預留新聞 ID、模型識別、內容 hash 與向量欄位，目前是空表，**新聞仍使用關鍵字查詢，尚未啟用語意搜尋**。需先選定並驗證本地 embedding 模型，再以同一模型建立文章與問題向量；不能直接混用來源不明的 1,024 維向量。

本次匯入 8 檔股票、989 筆行情與 300 則新聞。9 組 SQLite/PostgreSQL 查詢結果一致，並驗證查詢帳號即使要求讀寫交易也無法 DELETE。未完成整機重新開機與關閉網卡演練。原 HTML 簡報中的 SQLite 架構與量測代表遷移前版本，介紹新版時請說明此次資料層變更。
