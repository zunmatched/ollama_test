"""Real-model smoke checks; writes private local evidence and an offline backup."""
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("prices", "查詢台積電（2330）最近五個交易日的收盤價。", "get_prices"),
    ("compare", "比較 2330 和 2303 在 2026-09-01 至 2026-09-21 的價格變動百分比。", "compare_stocks"),
    ("news", "搜尋「記憶體」最近三則新聞，整理重點並附來源日期。", "search_news"),
    ("missing", "查詢 2330 在 2030-01-01 的收盤價，只查這一天。", "get_prices"),
]


def main():
    results = []
    with httpx.Client(timeout=240, trust_env=False) as client:
        status = client.get("http://127.0.0.1:8765/api/status").json()
        for name, question, expected in CASES:
            events = []
            with client.stream("POST", "http://127.0.0.1:8765/api/chat", json={"question": question}) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        events.append(json.loads(line))
            calls = [e for e in events if e["type"] == "tool_result"]
            passed = (any(e["type"] == "done" and not e.get("truncated") for e in events)
                      and any(e["name"] == expected and "error" not in e["result"] for e in calls)
                      and not any(e["type"] == "error" for e in events))
            if name == "missing":
                price_calls = [e for e in calls if e["name"] == "get_prices"]
                passed = passed and bool(price_calls) and all(
                    e["arguments"].get("start_date") == "2030-01-01"
                    and e["arguments"].get("end_date") == "2030-01-01"
                    and e["result"].get("found") is False for e in price_calls)
            answer = next((e["text"] for e in events if e["type"] == "answer"), "")
            passed = passed and bool(answer) and "</think>" not in answer and "<think>" not in answer
            if name == "news":
                news_rows = [row for e in calls if e["name"] == "search_news" for row in e["result"].get("rows", [])]
                passed = passed and len(news_rows) >= 3 and all(str(row["id"]) in answer for row in news_rows) and "\ufffd" not in answer
            result = {"case": name, "question": question, "tool_flow_passed": bool(passed), "answer": answer, "events": events}
            results.append(result)
            timing = next((e["elapsed_s"] for e in events if e["type"] == "done"), None)
            print(json.dumps({"case": name, "tool_flow_passed": bool(passed), "elapsed_s": timing}, ensure_ascii=False), flush=True)
    output = ROOT / "docs/local-results"
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"recorded_at": datetime.now(timezone.utc).isoformat(), "status": status, "results": results,
                "scope": "Automated tool-flow checks; answer factuality requires human review. Network adapters were not disabled."}
    (output / "smoke-results.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    cards = []
    for result in results:
        cards.append(f"<section><h2>{html.escape(result['question'])}</h2><p>工具流程檢查：{result['tool_flow_passed']}</p>"
                     f"<pre>{html.escape(result['answer'])}</pre><details><summary>原始執行紀錄</summary>"
                     f"<pre>{html.escape(json.dumps(result['events'], ensure_ascii=False, indent=2))}</pre></details></section>")
    page = "<!doctype html><html lang='zh-Hant'><meta charset='utf-8'><title>Local Stock Lab · 實測備援</title>" \
           "<style>body{max-width:1000px;margin:40px auto;padding:20px;background:#0c1319;color:#edf3f2;font:16px/1.8 sans-serif}" \
           "section{border:1px solid #395049;padding:24px;margin:24px 0;border-radius:12px}h1,h2,summary{color:#98e0c0}" \
           "pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}summary{cursor:pointer}</style>" \
           "<h1>Local Stock Lab · 實測紀錄</h1><p>這是事先保存的模型回答與工具結果，不是即時推論。新聞內容仍需人工核對。</p>" \
           f"<p>記錄時間：{html.escape(evidence['recorded_at'])}</p>" + "".join(cards) + "</html>"
    (output / "demo-backup.html").write_text(page, encoding="utf-8")
    if not all(r["tool_flow_passed"] for r in results):
        raise SystemExit("Some tool-flow checks failed; inspect docs/local-results/smoke-results.json")


if __name__ == "__main__":
    main()
