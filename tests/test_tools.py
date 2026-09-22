import sqlite3

import pytest


def test_read_only(stock_tools):
    with stock_tools.connection() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM stocks")


def test_find_by_name(stock_tools):
    assert stock_tools.find_stocks("台積電")["rows"][0]["ticker"] == "2330"


def test_sql_injection_is_literal(stock_tools):
    assert not stock_tools.find_stocks("' OR 1=1 --")["found"]
    assert not stock_tools.find_stocks("%")["found"]


def test_recent_prices_are_ordered_and_limited(stock_tools):
    result = stock_tools.get_prices("2330", limit=2)
    assert [r["close"] for r in result["rows"]] == [110,120]


def test_missing_date_does_not_fallback(stock_tools):
    assert not stock_tools.get_prices("2330", "2030-01-01", "2030-01-01")["found"]


def test_comparison_uses_common_dates(stock_tools):
    result = stock_tools.compare_stocks(["2330","2303"], "2026-09-01", "2026-09-03")
    assert result["start_date"] == "2026-09-02"
    assert result["rows"][0]["price_change_pct"] == pytest.approx(9.0909)
    assert result["rows"][1]["price_change_pct"] == 10


def test_missing_stock_cannot_compare(stock_tools):
    assert not stock_tools.compare_stocks(["2330","9999"], "2026-09-01", "2026-09-03")["found"]


@pytest.mark.parametrize("name,args", [
    ("get_prices", {"ticker": "2330", "limit": 500}),
    ("get_prices", {"ticker": "2330", "limit": True}),
    ("get_prices", {"ticker": "2330", "start_date": "2026-02-30"}),
    ("get_prices", {"ticker": "2330", "start_date": "2026-09-03", "end_date": "2026-09-01"}),
    ("get_prices", {"ticker": "2330; DROP TABLE stocks"}),
    ("get_prices", {"ticker": "2330", "sql": "DELETE FROM stocks"}),
    ("compare_stocks", {"tickers": ["2330","2330"], "start_date": "2026-09-01", "end_date": "2026-09-03"}),
    ("search_news", {}),
    ("run_shell", {"command": "anything"}),
    ("get_prices", "invalid"),
])
def test_invalid_tools_return_errors(stock_tools, name, args):
    assert "error" in stock_tools.execute(name,args)


def test_news_filters_and_returns_source(stock_tools):
    result = stock_tools.search_news("記憶體", ticker="2330")
    assert result["rows"][0]["url"] == "https://example.com/news"
    assert not stock_tools.search_news("記憶體", ticker="2303")["found"]
