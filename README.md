# Local Stock Lab

在 Windows 筆電上執行的股票資料 agent：**Ollama / Qwen3.5 4B + Python / FastAPI + 本機 PostgreSQL / pgvector**，保留唯讀 SQLite 快照備援。模型自主選擇工具；程式查資料、計算期間價格變化；網頁顯示回答與完整工具紀錄。

本機 PostgreSQL 部署與切換方式見 [部署指南](docs/POSTGRES.md)。新聞可使用關鍵字、實體關係及本機向量查詢；建立與更新索引見 [GraphRAG 指南](docs/GRAPHRAG.md)。

## 這台筆電直接開啟

雙擊根目錄的 **`start-demo.cmd`**，然後開啟 <http://127.0.0.1:8765>。

預設使用 Qwen3.5 4B（Q4_K_M）；首次模型載入較慢。上台前先跑一次「查行情」，保留服務執行並接上電源。每題都是獨立對話，不沿用上一題內容。需要切回已驗證的 Qwen3 4B Instruct 時，執行 `powershell -File scripts/start.ps1 -Model stock-agent:4b`。

模型、Python 套件、資料快照下載完成後，查詢路徑只使用 loopback 與本機檔案。新聞原文連結需要網路。完整斷網與重新開機演練請依 [展示指南](docs/DEMO.md) 操作。

## 系統介紹投影片

開啟 [9 頁 HTML 簡報](assets/system-slides.html)，可直接用瀏覽器離線播放。服務啟動後也可使用 [本機簡報網址](http://127.0.0.1:8765/static/system-slides.html)。

內容包含資料庫分工、agent 架構、工具流程、實測結果與現場展示。使用 `←` / `→` 換頁、`N` 切換講者備註、`G` 開啟目錄、`F` 切換全螢幕。簡報本身不需服務；第 8 頁的 Demo 連結需要先啟動 `start-demo.cmd`。

## 功能與界線

| 工具 | 功能 |
|---|---|
| `find_stocks` | 名稱／代號查詢 |
| `get_prices` | 日期範圍內最近 1–30 筆行情 |
| `compare_stocks` | 2–4 檔股票共同交易日期間的價格變化 |
| `search_news` | 關鍵字、股票標籤篩選及來源引用 |
| `search_news_graph` | 查詢新聞抽取的實體關係與逐字原文證據；需本機 PostgreSQL |
| `search_news_semantic` | 以本機 1024 維向量搜尋語意相近新聞；需本機 PostgreSQL |

GraphRAG 索引目前只覆蓋最新 30 則新聞；其中 8 則有通過原文證據檢查的關係，另有 30 則的本機向量。原資料庫來源不明的 1,024 維向量沒有混用。圖譜關係由模型抽取，仍需人工檢查語意；價格還原方式與成交量單位尚未驗證。此專案展示歷史資料查詢，不提供買賣建議。

## 從新環境安裝

需要 Python 3.12+、[uv](https://docs.astral.sh/uv/getting-started/installation/)、[Ollama](https://docs.ollama.com/windows)。

```powershell
uv sync --frozen
ollama pull qwen3.5:4b
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama pull qwen3-embedding:0.6b
ollama create stock-agent:4b -f models/Modelfile
```

Ollama Windows 安裝版通常會自動啟動；沒有啟動時執行 `ollama serve`。
預設 Demo 使用 `qwen3.5:4b`。原先已驗證的 `stock-agent:4b` 保留為 Qwen3 備援。
`models/Modelfile` 固定 Qwen3 備援的工具模板；沒有微調或更改模型權重。
這台準備用筆電採可攜版，位置為 `.runtime/ollama/ollama.exe`，模型存於 `.runtime/models`。
若手動啟動可攜版，預設載入 Qwen3.5 4B：

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_MODELS = Join-Path $PWD '.runtime/models'
& .runtime/ollama/ollama.exe serve
# 另一個 PowerShell 視窗：
& .runtime/ollama/ollama.exe pull qwen3:4b-instruct-2507-q4_K_M
& .runtime/ollama/ollama.exe create stock-agent:4b -f models/Modelfile
```

## 建立自己的資料快照

Git repository **不含市場資料、新聞內容、模型或密碼**。Clone 後需自行匯出資料。匯出器針對此專案的 PostgreSQL schema；其他資料庫需調整 `scripts/export_snapshot.py`。

```powershell
$env:PGHOST = 'your-db-host'
$env:PGDATABASE = 'your-database'
$env:PGUSER = 'your-readonly-user'
uv run python scripts/export_snapshot.py
# 密碼以隱藏提示輸入，不要放進命令歷史或程式碼。
```

匯出在 repeatable-read、read-only 交易中執行，限定 8 檔股票、最近 180 天行情與最多 300 則有發佈日期的新聞，不匯出持倉、交易或個人設定。以暫存檔完成後原子替換 `data/demo/stocks.sqlite`。快照預設不納入 Git。

## 開發與驗證

```powershell
uv run uvicorn src.app:app --host 127.0.0.1 --port 8765
uv run pytest -q
uv run python scripts/smoke_demo.py
```

最後一項需啟動網頁與 Ollama，會以真模型驗證固定 demo 題目，將結果存入忽略的 `docs/local-results/`，並產生可離線開啟的 HTML 備援。它不評分新聞摘要正確性，仍需人工核對來源。

## 結構

```text
src/             agent loop、唯讀工具、FastAPI 服務
assets/          無 CDN 依賴的 HTML / CSS / JavaScript
scripts/         啟動、快照匯出、真模型驗證
models/          可重建的 Ollama 提示模板，不含權重
tests/           合成資料工具測試、模擬模型測試
docs/            架構、展示流程及本機實测結果
data/demo/       僅本機保留的 SQLite 快照
```

## 安全與限制

- 四個工具白名單、固定參數化 SQL、SQLite `mode=ro` 與 `query_only`。
- 每次最多 5 輪、每輪最多 4 次工具呼叫，同時僅處理一個問題。
- 新聞視為不可信資料；提示詞要求模型忽略內嵌指令，這不是完整的提示注入防護。
- 有限的價格比較意圖規則要求使用比較工具；新聞摘要檢查來源 ID。這些檢查不代表完整的語意正確性驗證。
- 網頁只綁定 `127.0.0.1`；本 demo 沒有多人登入或企業權限管理。
- 小模型仍可能誤解問題或摘要錯誤，工具紀錄用於人工核對。

協作規則見 [AGENTS.md](AGENTS.md)。
