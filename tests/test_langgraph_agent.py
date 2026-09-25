import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from src.langgraph_agent import run_graph_agent


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.seen = []

    async def ainvoke(self, messages):
        self.seen.append(messages)
        return next(self.responses)


def collect(question, tools, responses, max_rounds=5):
    model = FakeModel(responses)
    events = asyncio.run(_collect(question, tools, model, max_rounds))
    return events, model


async def _collect(question, tools, model, max_rounds):
    return [event async for event in run_graph_agent(question, tools, max_rounds, model)]


def test_graph_tool_result_and_answer(stock_tools):
    call = AIMessage(content="", tool_calls=[{"name": "get_prices", "args": {"ticker": "2330", "limit": 1}, "id": "call-1"}])
    events, model = collect("查台積電股價", stock_tools, [call, AIMessage(content="來源：本機快照；收盤價 120")])
    assert [event["type"] for event in events if event["type"] in ("tool_result", "answer", "done")] == ["tool_result", "answer", "done"]
    assert isinstance(model.seen[1][-1], ToolMessage)
    assert events[-1]["tool_calls"] == 1


def test_graph_rejects_ungrounded_answer(stock_tools):
    events, _ = collect("查台積電股價", stock_tools, [AIMessage(content="120元"), AIMessage(content="120元")], 2)
    assert events[-1]["type"] == "error"
    assert not any(event["type"] == "answer" for event in events)


def test_graph_missing_ticker_skips_model(stock_tools):
    events, model = collect("看一下這5天內0050的趨勢", stock_tools, [])
    assert events[-1]["type"] == "done"
    assert events[-1]["tool_calls"] == 1
    assert not model.seen


def test_graph_iteration_limit(stock_tools):
    calls = [AIMessage(content="", tool_calls=[{"name": "get_prices", "args": {"ticker": "2330"}, "id": str(i)}]) for i in range(2)]
    events, _ = collect("查台積電股價", stock_tools, calls, 2)
    assert sum(event["type"] == "tool_result" for event in events) == 2
    assert events[-1]["type"] == "error"
