# 專案契約 — tw-stock-fundamentals

## 背景

來源：`reference/波段股價預估試算_sunny_v2.xlsx`（18 個 sheet 的 Google Sheets 匯出檔）。原本用 `IMPORTHTML` 從多個網站即時抓資料，存成 Excel 後 `IMPORTHTML` 已失效，各頁資料是 2026/08/14 的快照。本專案要用 Python 爬蟲＋SQLite 重建這個即時抓取能力，並做成網站。

產品功能與呈現以根目錄 `★★★★★★ 波段股價預估試算_sunny.xlsx` 為基準；
`reference/..._sunny_v2.xlsx` 是 Google Sheets 公式還原模板，不作為本機快取數值基準。
Sheet 能力重整、網站去向及 API 邊界見 `docs/specs/site-information-architecture.md`；
估值與 PE 河流的逐步公式見 `docs/specs/workbook-formula-contract.md`。

估值方法論代號「蘭氏」（見 `工作表1`），核心邏輯：

- **估值鏈**（以 `股價預估` 實際公式為準）：營收基準 → ×毛利率 −營業費用 +業外 → ×稅後保留率 → 扣非控制權益 → 依最新季「EPS／母公司淨利」換算預估 EPS → TTM EPS × PE 河流 → 目標價
- **本益比河流**：近五年月 PE 的 `AVERAGE ± 1/2/3 × STDEVP`；Excel 標籤雖寫「中位數」，公式實際是平均數，網站沿用公式而不沿用錯誤名稱
- **弦值**（蘭氏 ROE 選股指標，全市場排名用）：`(ROE × 本業比率) / PB`，越高代表用越低股價買到越高品質的本業 ROE
- **本業 EPS**：`EPS × 本業比率`，本業比率 = `1 − 業外損益佔比`，先剔除業外雜訊再評價
- **自由現金流**：完整資料時為 `營運現金 − 資本支出`；舊來源只有投資現金流時，網站僅顯示 `營業＋投資` 近似值並明確標示，不稱為正式 FCF
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
| 財報健檢 | 資產負債表/損益表/獲利率摘要 | TWSE OpenAPI 官方資料集（t187ap06/07_L_ci, t187ap17_L） | 官方，優先 |
| 股息&現金流 | 除權息歷史、現金流量表 | histock 除權息、現金流量表 | 入口 |
| 籌碼 | 法人買賣超、大戶比、融資券、分點 | histock、Fubon | 入口/券商 |
| 期貨籌碼 | 三大法人期貨未平倉 | `taifex.com.tw`（官方） | 官方，優先 |
| 排行榜 | 全市場成交值排行 | TWSE OpenAPI STOCK_DAY_ALL（官方） | 官方，優先 |
| 減資一覽表 | 減資股 EPS 校正值 | 手動維護（原資料源已停用） | 手動 |

**資料遷移缺口**：網站能力與資料表已保留市值排行、完整損益、資產負債細目、日股價、法人、融資券、券商分點與 ETF 持股；尚未接妥來源時 API 回傳空陣列，前端顯示「待補資料源」。估值在缺少 `income_statement_quarterly` 時可用舊 `margin_quarterly` 推回營業費用，但會附警告；缺少 65 個月 `pe_monthly` 時可用季底股價／TTM EPS 暫代，也會明確標示不等同 Excel。這兩種 fallback 不得視為正式驗收完成。

完整原始公式與每個 sheet 的欄位結構見 `docs/specs/workbook-analysis.md`（從 xlsx 逐格提取，含公式與快照值，可當 golden-value 測試的參考基準）。

## 資料庫（SQLite，`data/app.db`）

每張表都有 `fetched_at` 欄位，作為快取新鮮度判斷依據（同股票同資料源每日最多重抓一次）。核心表：

實際 schema 以 `app/db/schema.sql` 為準（下面是摘要，欄位細節請直接看該檔）：

- `stocks(code PK, name, market, industry, updated_at)`
- `stock_info(code, price, market_cap_millions, beta, pe_ratio, dividend_yield_pct, book_value_per_share, capital_billion_twd, fetched_at)`
- `revenue_monthly(code, month, revenue, fetched_at)`
- `margin_quarterly(code, quarter, revenue, cost_of_goods_sold, gross_profit, gross_margin_pct, operating_income, operating_margin_pct, non_operating_income, pretax_income, net_income, eps, fetched_at)`
- `opex_quarterly(code, quarter, ar_days, inventory_days, operating_cycle_days, fetched_at)` — 實際是週轉天數表，不是費用細目（見上方已知缺口）
- `eps_quarterly(code, quarter, eps, fetched_at)`
- `financial_health_quarterly(code, quarter, current_assets, total_assets, current_liabilities, total_liabilities, total_equity, capital, book_value_per_share, revenue, gross_profit, operating_income, pretax_income, net_income, eps, gross_margin_pct, operating_margin_pct, net_margin_pct, fetched_at)`
- `dividends(code, fiscal_year, ex_dividend_date, payout_year, cash_dividend, stock_dividend, eps, payout_ratio_pct, yield_pct, fill_dividend_days, fetched_at)` — 逐次配息事件，非年度單筆
- `cashflow_quarterly(code, quarter, operating, investing, financing, capital_expenditure, free_cash_flow, operating_plus_investing, source, fetched_at)`
- `chips_daily(code, date, foreign_holding_pct, trust_holding_pct, margin_balance, short_balance, fetched_at)`
- `futures_oi_daily(date, institution, contract, long_oi, short_oi, net_oi, fetched_at)`
- `rankings_daily(date, category, rank, code, name, value, fetched_at)`
- `market_cap_daily(date, code, market_cap, pct_of_market, fetched_at)` — 目前無填入來源（見已知缺口）
- `capital_reductions(name PK, code, resume_date, adjust_factor)`
- `income_statement_quarterly`、`balance_sheet_quarterly`、`operating_efficiency_quarterly` — 完整季度領域
- `pe_monthly`、`stock_prices_daily` — PE 河流與 K 線歷史
- `stock_events`、`dividend_annual`、`etf_holdings`、`institutional_trading_daily`、`margin_short_daily`、`broker_branches_daily` — 事件、年度股利與籌碼領域

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
