"""Optional LangGraph orchestration for the existing read-only stock tools."""

import json
import re
import time
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from src.agent import final_content, system_prompt
from src.config import MODEL, OLLAMA_URL
from src.tools import TOOL_SCHEMAS, StockTools


class AgentState(TypedDict, total=False):
    messages: list
    events: list[dict]
    rounds: int
    tool_calls: int
    comparison_done: bool
    comparison_required: bool
    news_ids: list[str]
    tokens: int
    generation_ns: int
    truncated: bool
    answer: str
    error: str
    started: float
    question: str


def build_graph(tools: StockTools, llm: Any, max_rounds: int = 5):
    """Compile explicit model, tool, and evidence-check nodes for one request."""

    async def precheck(state: AgentState) -> dict:
        question = state["question"]
        metadata = tools.metadata()
        names = ", ".join(f"{s['ticker']} {s['name']}" for s in metadata["stocks"])
        requested = list(dict.fromkeys(re.findall(r"(?<![\w.\-])\d{4,6}(?![\w.\-])", question, flags=re.ASCII)))
        available = {s["ticker"] for s in metadata["stocks"]}
        missing = [ticker for ticker in requested if ticker not in available]
        events = []
        if missing and any(word in question for word in ("趨勢", "收盤", "價格", "行情", "漲跌", "股票", "比較")):
            events.append({"type": "status", "text": "程式先確認指定股票是否存在於本機快照"})
            for ticker in missing:
                args = {"keyword": ticker}
                events.append({"type": "tool_start", "name": "find_stocks", "arguments": args})
                tick = time.perf_counter()
                result = tools.execute("find_stocks", args)
                events.append({"type": "tool_result", "name": "find_stocks", "arguments": args,
                               "result": result, "elapsed_ms": round((time.perf_counter() - tick) * 1000, 1)})
                if "error" in result:
                    return {"error": "股票資料查核失敗，請確認本機資料庫已啟動。", "events": events}
            answer = (f"本機快照未包含 {'、'.join(missing)}，因此無法回答這些標的的指定期間行情或趨勢。"
                      "這不代表該股票沒有交易資料，只是本次展示尚未匯入。\n\n"
                      f"目前可查：{names}。\n若要查詢上述缺少的標的，需要先匯入其歷史行情。\n"
                      f"來源：本機 stocks 清單；行情快照截止 {metadata.get('price_last_date', '未提供')}。")
            return {"answer": answer, "events": events, "tool_calls": len(missing)}
        return {"messages": [SystemMessage(content=system_prompt(metadata)), HumanMessage(content=question)],
                "events": events}

    async def model(state: AgentState) -> dict:
        round_number = state.get("rounds", 0) + 1
        response: AIMessage = await llm.ainvoke(state["messages"])
        meta = response.response_metadata or {}
        return {"messages": state["messages"] + [response], "rounds": round_number,
                "tokens": state.get("tokens", 0) + int(meta.get("eval_count") or 0),
                "generation_ns": state.get("generation_ns", 0) + int(meta.get("eval_duration") or 0),
                "truncated": meta.get("done_reason") == "length",
                "events": [{"type": "status", "text": f"LangGraph 模型節點 · 第 {round_number} 輪"}]}

    async def execute_tools(state: AgentState) -> dict:
        calls = state["messages"][-1].tool_calls
        if len(calls) > 4:
            return {"error": "模型一次要求過多工具，已停止。請縮小問題範圍。", "events": []}
        messages = list(state["messages"])
        events = []
        comparison_done = state.get("comparison_done", False)
        news_ids = state.get("news_ids", [])
        for call in calls:
            name, args = call["name"], call["args"]
            events.append({"type": "tool_start", "name": name, "arguments": args})
            tick = time.perf_counter()
            result = tools.execute(name, args)
            events.append({"type": "tool_result", "name": name, "arguments": args,
                           "result": result, "elapsed_ms": round((time.perf_counter() - tick) * 1000, 1)})
            messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False),
                                        tool_call_id=call["id"], name=name))
            if name == "compare_stocks" and "error" not in result:
                comparison_done = True
            if name in ("search_news", "search_news_graph", "search_news_semantic") and result.get("found"):
                news_ids = [str(row["id"]) for row in result["rows"]]
        return {"messages": messages, "events": events,
                "tool_calls": state.get("tool_calls", 0) + len(calls),
                "comparison_done": comparison_done, "news_ids": news_ids}

    async def verify(state: AgentState) -> dict:
        content = state["messages"][-1].content
        answer = final_content(content if isinstance(content, str) else "")
        feedback = None
        if state.get("tool_calls", 0) == 0:
            feedback = "請先使用工具查詢，不能以模型記憶作答。"
            failure = "模型未能呼叫查詢工具，因此沒有可驗證的資料回答。請換一個具體問題。"
        elif state.get("comparison_required") and not state.get("comparison_done"):
            feedback = "期間比較必須呼叫compare_stocks取得共同交易日計算結果。"
            failure = "未取得可靠的期間比較結果，已停止回答。"
        elif state.get("news_ids") and (any(source not in answer for source in state["news_ids"]) or "\ufffd" in answer):
            feedback = "請重新回答並完整引用全部新聞ID：" + ", ".join(state["news_ids"])
            failure = "模型摘要未完整引用來源，請直接查看右側新聞結果。"
        if feedback:
            if state["rounds"] < max_rounds:
                return {"messages": state["messages"] + [HumanMessage(content=feedback)],
                        "events": [{"type": "status", "text": "LangGraph 驗證節點要求補齊證據"}]}
            return {"error": failure, "events": []}
        if state.get("truncated"):
            answer += "\n\n（模型輸出達到長度上限，請以工具紀錄核對。）"
        return {"answer": answer or "模型沒有產生回答，請查看工具結果或重新提問。", "events": []}

    graph = StateGraph(AgentState)
    graph.add_node("precheck", precheck)
    graph.add_node("model", model)
    graph.add_node("tools", execute_tools)
    graph.add_node("verify", verify)
    graph.add_edge(START, "precheck")
    graph.add_conditional_edges("precheck", lambda s: END if s.get("answer") or s.get("error") else "model")
    graph.add_conditional_edges("model", lambda s: "tools" if s["messages"][-1].tool_calls else "verify")
    graph.add_conditional_edges("tools", lambda s: END if s.get("error") else "model" if s["rounds"] < max_rounds else END)
    graph.add_conditional_edges("verify", lambda s: END if s.get("answer") or s.get("error") else "model")
    return graph.compile()


async def run_graph_agent(question: str, tools: StockTools, max_rounds: int = 5, llm: Any = None):
    started = time.perf_counter()
    if llm is None:
        llm = ChatOllama(model=MODEL, base_url=OLLAMA_URL, temperature=0,
                         num_ctx=8192, num_predict=1000, reasoning=False).bind_tools(TOOL_SCHEMAS)
    graph = build_graph(tools, llm, max_rounds)
    initial: AgentState = {"question": question, "rounds": 0, "tool_calls": 0,
                           "comparison_required": "比較" in question and any(
                               word in question for word in ("價格", "漲跌", "報酬", "收盤"))}
    yield {"type": "start", "model": MODEL, "engine": "langgraph"}
    state = dict(initial)
    async for update in graph.astream(initial, stream_mode="updates", config={"recursion_limit": max_rounds * 4 + 4}):
        _, changed = next(iter(update.items()))
        state.update(changed)
        for event in changed.get("events", []):
            yield event
        if changed.get("error"):
            yield {"type": "error", "text": changed["error"]}
            return
        if changed.get("answer"):
            yield {"type": "answer", "text": changed["answer"]}
            ns = state.get("generation_ns", 0)
            tokens = state.get("tokens", 0)
            yield {"type": "done", "truncated": state.get("truncated", False),
                   "elapsed_s": round(time.perf_counter() - started, 2),
                   "tool_calls": state.get("tool_calls", 0), "generated_tokens": tokens,
                   "generation_tokens_per_s": round(tokens / (ns / 1e9), 1) if ns else None}
            return
    yield {"type": "error", "text": f"已達{max_rounds}輪上限，停止執行。請縮小問題範圍；已取得的工具結果保留在右側。"}
