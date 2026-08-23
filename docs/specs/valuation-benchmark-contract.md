# 決策比較訊號 — 個股 vs 大盤估值基準

## 背景

做決策時「比較」比「絕對數字」更重要——個股本益比 27.94 本身看不出貴不貴，
要跟大盤本益比比才知道相對便宜或昂貴；預估目標價本身看不出吸引力，要跟現價
比出漲幅 % 才能快速下判斷。這份文件涵蓋兩塊：

1. **目標價 vs 現價**（`app/calc/workbook_model.py`）：純計算，沿用既有的
   `current_price`／`pe_target_prices` 欄位相減得出，不需要新資料源。
2. **個股本益比／殖利率 vs 大盤中位數**（`app/calc/market_valuation.py` +
   `app/scrapers/twse_valuation_stats.py`）：需要一份全市場橫斷面估值資料，
   本節重點記錄這塊的資料源選擇與限制。

## 資料源

`app.scrapers.twse_valuation_stats`（TWSE OpenAPI `BWIBBU_ALL`，官方）：單一請求
一次回傳全部**上市**股票當日 `{Code, Name, PEratio, DividendYield, PBratio}`。
2026-08-22 實測 1081 檔、868 檔本益比有值（其餘為虧損股，空字串正確轉 `None`
不當 0），2330 台積電 PE 27.94／殖利率 0.91% 跟既有 `stock_info.pe_ratio`
（Fubon 來源）數字一致，交叉驗證通過。

**MVP 範圍限定上市（TWSE）**：TWSE OpenAPI 沒有涵蓋上櫃股票；上櫃要另外接
TPEx OpenAPI 對應端點，用同樣的 pattern（`app.scrapers.twse_valuation_stats`
的 parse/scrape 架構）補一支姊妹 scraper，屬於後續工作，不在這輪範圍內。
目前上櫃個股查詢 `pe_vs_market_pct`／`yield_vs_market_pct` 會是 `None`
（顯示為「-」，不是 0）。

## 大盤基準值：中位數，不是加權指數本益比

TWSE 本身不直接發布「大盤本益比」這種聚合值。`app.calc.market_valuation.
market_median()` 對這份橫斷面資料取**中位數**（濾掉 `None` 與非正值後），
不是依市值加權平均，理由：

- 用中位數不會被虧損股（PE 缺值，已濾除）或個別極端值（例如本益比破百的
  轉機股）拉偏。
- 這是我方對「一般散戶認知的大盤估值水位」的近似，不宣稱是官方發布的
  發行量加權指數本益比——跟 `pe_matrix.py`／`sector-momentum-formula-
  contract.md` 既有的「明講近似、不宣稱精確復刻官方指標」寫作慣例一致。

## 資料層

新表 `stock_valuation_daily(date, code, pe_ratio, dividend_yield_pct, pb_ratio,
source, fetched_at)`，PK 為 `(date, code)`。單一官方來源（`twse-bwibbu-all`），
`merge_rule="single_source"`，不需要跟其他來源做優先序裁決。

## 服務層

`app.dashboard_v2_service.build_valuation_benchmark(conn, code)` 回傳：

```python
{
    "date": "2026-08-21",
    "stock_pe": 27.94, "stock_yield": 0.91,
    "market_pe_median": 17.645, "market_yield_median": 3.43,
    "pe_vs_market_pct": 0.583..., "yield_vs_market_pct": -0.735...,
}
```

查無當日資料時全部欄位回 `None`（不是清空整頁、也不是拿舊資料硬湊），因為
這是獨立面板，缺資料時本來就該老實顯示「-」。

## 回補頻率

TWSE 官方、單一請求、低頻率（一天一次全市場快照）——掛進
`app.ingest._MARKET_STEPS`，跟其他官方每日資料集一樣自動排程，不需要像細產業
那樣要求使用者手動觸發（風險邊界只擋「大量高頻爬取」，這裡是單一請求）。

## 前端

`#stat-pe`／`#stat-yield`（`web/static/app.js::renderStockHeader`）旁各加一個
`deltaChip()` 徽章顯示「vs 大盤中位數」的 %；共用元件見
`web/static/app.js` 的 `signedPct()`／`deltaChip()`（重用 `signedHeatClass` 的
三級色階，只是換一個 pill 形狀的基底 class，不重新發明）。
