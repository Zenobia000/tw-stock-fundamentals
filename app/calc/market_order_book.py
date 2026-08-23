"""大盤尾盤委買委賣 — 用全市場「最後揭示買/賣量」加總，替代做不到的即時委買委賣。

籌碼K線 App「大盤即時委買委賣」是即時委託簿累計（例如截圖裡的 605萬/609萬張），
本專案是收盤後批次系統，抓不到即時委託簿。但 TWSE `MI_INDEX` 官方來源本身就有
「最後揭示買量」「最後揭示賣量」欄位（收盤前最後一筆委託的量），落地在
`market_stock_snapshot_daily.last_bid_volume`/`last_ask_volume`（見
`app/scrapers/twse_market_snapshot.py`）。全市場加總這兩欄，是一個誠實的
「尾盤最後揭示」替代指標——語意是「收盤瞬間全市場委買/委賣量加總」，不是
「當日累積委託總量」，兩者數字量級會差很多，UI 呈現要清楚標示是「尾盤」不是
「即時」或「全日累積」，避免使用者誤讀成參考截圖那種即時委託簿數字。

已知限制：
1. 只有 TWSE 有這兩個欄位。TPEX 官方 `tpex_mainboard_daily_close_quotes` 只有
   `LatestBidPrice`/`LatesAskPrice`（最後揭示「價」），沒有對應的量欄位，所以
   這裡固定只算 TWSE，回傳結構明講 `market: "TWSE"`，不假裝涵蓋全市場。
2. 「最後揭示」是收盤前那一瞬間的委託量快照，不是連續委託簿的滾動累計，跟
   即時看盤軟體顯示的「總委買/總委賣」在定義上是兩件不同的事，只是名稱相似。
"""

import sqlite3


def compute_market_order_book(conn: sqlite3.Connection, date: str) -> dict:
    """全市場（僅 TWSE）當日最後揭示買/賣量加總。

    回傳 `{"date": ..., "market": "TWSE", "total_bid_volume": ..., "total_ask_volume": ...}`。
    當日沒有資料（例如尚未 ingest）時，兩個加總欄位回傳 `None`，不當作 0。
    """
    row = conn.execute(
        """
        SELECT SUM(last_bid_volume) AS total_bid, SUM(last_ask_volume) AS total_ask
        FROM market_stock_snapshot_daily
        WHERE date = ? AND market = 'TWSE'
        """,
        (date,),
    ).fetchone()

    return {
        "date": date,
        "market": "TWSE",
        "total_bid_volume": row["total_bid"] if row else None,
        "total_ask_volume": row["total_ask"] if row else None,
    }
