import asyncio
import json

import httpx

from src.agent import run_agent, final_content


def test_final_content_excludes_reasoning():
    assert final_content("private reasoning</think>\nFinal answer") == "Final answer"
    assert final_content("<think>unfinished reasoning") == ""


def test_missing_ticker_has_verified_explanation(stock_tools):
    def no_model(request):
        raise AssertionError("Missing snapshot ticker should not require inference")
    events = collect(stock_tools, no_model, question="看一下這5天內0050的趨勢")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["arguments"] == {"keyword": "0050"}
    assert not result["result"]["found"]
    answer = next(e["text"] for e in events if e["type"] == "answer")
    assert "未包含 0050" in answer
    assert "2330" in answer
    assert events[-1]["type"] == "done"


def test_iso_date_is_not_a_missing_ticker(stock_tools):
    events = collect(stock_tools, lambda request: httpx.Response(200, json={
        "message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "get_prices", "arguments": {"ticker": "2330", "start_date": "2030-01-01", "end_date": "2030-01-01"}}}]}}),
        max_rounds=1, question="查詢2330在2030-01-01的收盤價")
    assert next(e for e in events if e["type"] == "tool_result")["name"] == "get_prices"


def collect(stock_tools, handler, max_rounds=5, question="查台積電"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return [event async for event in run_agent(question, stock_tools, client, max_rounds)]
    return asyncio.run(run())


def test_tool_result_returns_to_model(stock_tools):
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if len(calls) == 1:
            message = {"role": "assistant", "content": "", "tool_calls": [{"function": {
                "name": "get_prices", "arguments": {"ticker": "2330", "limit": 1}}}]}
        else:
            tool_message = body["messages"][-1]
            assert tool_message["role"] == "tool"
            assert json.loads(tool_message["content"])["rows"][0]["close"] == 120
            message = {"role": "assistant", "content": "測試回答"}
        return httpx.Response(200, json={"message": message})
    events = collect(stock_tools, handler)
    assert events[-1]["type"] == "done"
    assert events[-1]["tool_calls"] == 1


def test_iteration_limit(stock_tools):
    def handler(request):
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "get_prices", "arguments": {"ticker": "2330"}}}]}})
    events = collect(stock_tools, handler)
    assert sum(e["type"] == "tool_result" for e in events) == 5
    assert events[-1]["type"] == "error"


def test_ungrounded_answer_is_not_delivered(stock_tools):
    events = collect(stock_tools, lambda request: httpx.Response(200, json={
        "message": {"role": "assistant", "content": "unverified price"}}))
    assert not any(e["type"] == "answer" for e in events)
    assert events[-1]["type"] == "error"


def test_tool_error_is_visible(stock_tools):
    events = collect(stock_tools, lambda request: httpx.Response(200, json={"message": {
        "role": "assistant", "content": "", "tool_calls": [{"function": {"name": "delete_all", "arguments": {}}}]}}), 1)
    assert next(e for e in events if e["type"] == "tool_result")["result"]["error"]


def test_comparison_requires_computed_tool(stock_tools):
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "get_prices", "arguments": {"ticker": "2330"}}}]},
        {"role": "assistant", "content": "Wrong five-day calculation"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "compare_stocks", "arguments": {
            "tickers": ["2330","2303"], "start_date": "2026-09-01", "end_date": "2026-09-03"}}}]},
        {"role": "assistant", "content": "Correct comparison"},
    ]
    events = collect(stock_tools, lambda request: httpx.Response(200, json={"message": messages.pop(0)}),
                     question="比較兩檔股票價格")
    assert [e["text"] for e in events if e["type"] == "answer"] == ["Correct comparison"]


def test_news_requires_source_ids(stock_tools):
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "search_news", "arguments": {"keyword": "記憶體"}}}]},
        {"role": "assistant", "content": "Partial summary without source"},
        {"role": "assistant", "content": "ID 1: complete fixture summary"},
    ]
    events = collect(stock_tools, lambda request: httpx.Response(200, json={"message": messages.pop(0)}))
    assert [e["text"] for e in events if e["type"] == "answer"] == ["ID 1: complete fixture summary"]
