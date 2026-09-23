# 本機新聞 GraphRAG

本功能只處理本機 `stock_demo.news` 快照，不會寫入遠端來源資料庫。它將新聞轉成具原文證據的實體關係，並使用同一款本機 embedding 模型為新聞和問題產生向量。

## 建立索引

先啟動 PostgreSQL 與 Ollama，確認已下載 `qwen3.5:4b` 和 `qwen3-embedding:0.6b`。在專案根目錄執行：

```powershell
uv run python scripts/setup-graphrag.py
uv run python scripts/build-news-graph.py --limit 30
uv run python scripts/embed-news.py --limit 300
```

圖譜先處理最新 30 則，向量處理全部 300 則；若要擴大圖譜，可將 `build-news-graph.py` 的上限改成 `--limit 300`。重跑會依內容 hash 和模型版本跳過已處理的文章。每篇文章單獨提交；中途失敗不會清空先前結果。模型下載需要網路，索引建立及查詢可離線執行。

## 資料與查詢

- `graph_entities`：公司、產品、產業、事件；目前只做空白與大小寫正規化，不做跨名稱同義詞合併。
- `graph_relations`：受限的三種關係；`graph_evidence` 保存新聞 ID、逐字原文片段、模型和內容 hash。
- `graph_processed_news`：紀錄已完成文章；`news_embeddings` 保存 1024 維文章向量及模型識別。
- `search_news_graph`：依實體名稱搜尋關係與證據。`search_news_semantic`：查語意相近新聞。原 `search_news` 保留關鍵字搜尋。

模型抽取的片段會驗證為新聞原文的連續文字（容許空白差異並還原原文），但這只能證明引用存在，不能證明關係解讀正確。目前向量索引涵蓋快照全部 300 則新聞，均由 `qwen3-embedding:0.6b` 產生 1,024 維向量；圖譜處理最新 30 則，其中 8 則產出 31 條證據。其餘文章可能沒有符合條件的關係。實體只按名稱合併，可能將「外資」等泛稱錯標為公司；目前也只查直接關係，尚無多跳推理。示範時檢查右側工具結果與新聞來源；不要把新聞內容當成股價變動的已證實原因。查詢帳號仍為唯讀；批次建立索引使用僅存於 `.runtime` 的本機管理帳號。
