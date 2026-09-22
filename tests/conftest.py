import json
import sqlite3

import pytest

from scripts.export_snapshot import SCHEMA
from src.tools import StockTools


@pytest.fixture
def stock_tools(tmp_path):
    path = tmp_path / "stocks.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO stocks VALUES (?,?,?)", [("2330", "台積電", "半導體"), ("2303", "聯電", "半導體")])
        for ticker, day, close in [("2330","2026-09-01",100), ("2330","2026-09-02",110),
                                    ("2330","2026-09-03",120), ("2303","2026-09-02",50), ("2303","2026-09-03",55)]:
            db.execute("INSERT INTO daily_prices VALUES (?,?,?,?,?,?,?)", (ticker, day, close, close, close, close, 1000))
        db.execute("INSERT INTO news VALUES (?,?,?,?,?,?,?)", (1, "記憶體測試新聞", "純測試資料，不是真實行情。",
                   "https://example.com/news", "2026-09-03T10:00:00+08:00", "fixture", '["2330"]'))
        db.execute("INSERT INTO metadata VALUES (?,?)", ("price_last_date", json.dumps("2026-09-03")))
    return StockTools(path)
