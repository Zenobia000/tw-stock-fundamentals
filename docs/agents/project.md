# 專案契約 — tw-stock-fundamentals

## 背景

來源：`reference/波段股價預估試算_sunny_v2.xlsx`（18 個 sheet 的 Google Sheets 匯出檔）。原本用 `IMPORTHTML` 從多個網站即時抓資料，存成 Excel 後 `IMPORTHTML` 已失效，各頁資料是 2026/08/14 的快照。本專案要用 Python 爬蟲＋SQLite 重建這個即時抓取能力，並做成網站。

估值方法論代號「蘭氏」（見 `工作表1`），核心邏輯：

- **估值鏈**（`總覽`!B5）：近月營收×3 → 預估季營收 → ×毛利率 −營業費用 +業外 → ×(1−稅率) → 預估稅後淨利 ÷股本 → 預估EPS × 高/中/低本益比 → 目標價
- **弦值**（蘭氏 ROE 選股指標，全市場排名用）：`(ROE × 本業比率) / PB`，越高代表用越低股價買到越高品質的本業 ROE
- **本業 EPS**：`EPS × 本業比率`，本業比率 = `1 − 業外損益佔比`，先剔除業外雜訊再評價
- **自由現金流**：`營運現金 − 資本支出`
- **營運天數**：`收款天數 + 存貨天數`（蘭氏核心效率指標，越低越好）
- 紅綠判讀：與前一季比較，多數指標「增=紅」，天數與負債比「降=紅」（方向自動反轉）

## 功能 sheet → 資料源對照

| Sheet | 用途 | 主要來源 | 優先序 |
|---|---|---|---|
| 證券編碼查詢 | 代號→名稱/市場別/產業別 | `isin.twse.com.tw`（官方 ISIN） | 官方，優先 |
| 股票資訊 | 股價/股本/市值/Beta/發布日/ETF持股 | Fubon eBroker DJ | 券商 |
| 營收 | 月營收、YoY、長短期擴張收斂 | histock 財務報表、Fubon 月營收 | 券商/入口 |
| 毛利率&業外 | 毛利率/營益率/業外占比 | Fubon 獲利能力分析、histock 利潤比率 | 券商/入口 |
| 營業費用 | 損益表季度拆解、稅率、週轉天數 | histock、money-link | 入口 |
| 每股盈餘(EPS) | EPS成長率、PE分位目標價矩陣 | Fubon 經營績效、histock | 券商/入口 |
| 財報健檢 | 資產負債表/現金流摘要、安全性指標 | 公開資訊觀測站 MOPS（官方） | 官方，優先 |
| 股息&現金流 | 股利政策、殖利率、填息天數 | CMoney、histock | 入口 |
| 籌碼 | 法人買賣超、大戶比、融資券、分點 | histock、Fubon | 入口/券商 |
| 期貨籌碼 | 三大法人期貨未平倉 | `taifex.com.tw`（官方） | 官方，優先 |
| 排行榜 | 成交值/券資比排行 | Fubon | 券商 |
| 市值排行 | 全市場市值佔比排行 | TWSE/TAIFEX | 官方 |
| 減資一覽表 | 減資股 EPS 校正值 | 手動維護（原資料源已停用） | 手動 |

完整原始公式與每個 sheet 的欄位結構見 `docs/specs/workbook-analysis.md`（從 xlsx 逐格提取，含公式與快照值，可當 golden-value 測試的參考基準）。

## 資料庫（SQLite，`data/app.db`）

每張表都有 `fetched_at` 欄位，作為快取新鮮度判斷依據（同股票同資料源每日最多重抓一次）。核心表：

- `stocks(code PK, name, market, industry, updated_at)`
- `stock_info(code, price, shares_outstanding, market_cap, beta, next_earnings_date, next_revenue_date, fetched_at)`
- `revenue_monthly(code, month, revenue, fetched_at)`
- `margin_quarterly(code, quarter, revenue, gross_margin, operating_income, non_op_ratio, eps, fetched_at)`
- `opex_quarterly(code, quarter, sga, rd, tax_rate, fetched_at)`
- `eps_quarterly(code, quarter, eps, fetched_at)`
- `financial_health_quarterly(code, quarter, cash, ar, inventory, total_assets, total_liabilities, equity, operating_cf, capex, fetched_at)`
- `dividends(code, year, cash_dividend, stock_dividend, yield, fill_days, fetched_at)`
- `cashflow(code, quarter, operating, investing, financing, fetched_at)`
- `chips_daily(code, date, foreign_holding_pct, margin_balance, fetched_at)`
- `futures_oi_daily(date, institution, long_oi, short_oi, fetched_at)`
- `rankings_daily(date, category, rank, code, value, fetched_at)`
- `market_cap_daily(date, code, market_cap, pct_of_market, fetched_at)`
- `capital_reductions(name, code, resume_date, adjust_factor)`

## 驗收標準

每個功能落地時：

1. scraper 對真實來源跑過一次，資料寫進 SQLite，欄位型別正確（非全 NULL）
2. 對照 `docs/specs/workbook-analysis.md` 或 workbook 快照值的 golden-value pytest 通過
3. API endpoint 回傳該功能資料，前端頁籤能顯示
4. 九宮格與股價預估要等其依賴的功能 sheet 都完成才能組裝

## 風險邊界

- 官方源（TWSE、MOPS、TAIFEX）優先；券商/入口網站僅補充，HTML 結構視為會變，parser 要能優雅失敗
- 爬蟲節流：同股票同資料源每日最多一次；失敗時用快取舊資料，不整頁掛掉
- `app-origin` 是新建的公開 repo（`Zenobia000/tw-stock-fundamentals`），跟這個資料夾原本掛的教材 repo `origin` 無關，不要動 `origin`
