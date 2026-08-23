# 專案契約 — tw-stock-fundamentals

## 背景

本專案是個人使用的台股通用研究平台。公開市場與公司資料由 Python 擷取、正規化並保存於 SQLite；FastAPI 統一提供估值、營運品質、翁氏九宮格與籌碼市場資料，前端負責跨時間與跨領域的研究呈現。

資料來源角色、同期間衝突裁決、新鮮度與升級門檻以 `docs/specs/data-strategy-contract.md` 為準；可執行的單一真實來源是 `app/data_strategy.py`，未登錄的 dataset/source 不得接入正式 ETL。

產品資訊架構及 API 邊界見 `docs/specs/site-information-architecture.md`；估值與 PE 河流的逐步公式見 `docs/specs/workbook-formula-contract.md`。兩者都是本專案自身的契約，不依賴任何外部應用程式執行。

估值方法論代號「翁氏」，核心邏輯：

- **估值鏈**（以 `股價預估` 實際公式為準）：營收基準 → ×毛利率 −營業費用 +業外 → ×稅後保留率 → 扣非控制權益 → 依最新季「EPS／母公司淨利」換算預估 EPS → TTM EPS × PE 河流 → 目標價
- **本益比河流**：近五年月 PE 的 `平均值 ± 1/2/3 × 母體標準差`
- **弦值**（翁氏 ROE 選股指標，全市場排名用）：`(ROE × 本業比率) / PB`，越高代表用越低股價買到越高品質的本業 ROE
- **本業 EPS**：`EPS × 本業比率`，本業比率 = `1 − 業外損益佔比`，先剔除業外雜訊再評價
- **自由現金流**：完整資料時為 `營運現金 − 資本支出`；舊來源只有投資現金流時，網站僅顯示 `營業＋投資` 近似值並明確標示，不稱為正式 FCF
- **營運天數**：`收款天數 + 存貨天數`（翁氏核心效率指標，越低越好）
- 紅綠判讀：與前一季比較，多數指標「增=紅」，天數與負債比「降=紅」（方向自動反轉）

## 研究功能 → 資料源對照

| 功能 | 用途 | 主要來源 | 優先序 |
|---|---|---|---|
| 證券編碼查詢 | 代號→名稱/市場別/產業別 | `isin.twse.com.tw`（官方 ISIN） | 官方，優先 |
| 股票資訊 | 股價/股本/市值/Beta/發布日/ETF持股 | Fubon eBroker DJ | 券商 |
| 營收 | 月營收、YoY、長短期擴張收斂 | histock 財務報表、Fubon 月營收 | 券商/入口 |
| 毛利率&業外 | 毛利率/營益率/業外占比 | Fubon 獲利能力分析、histock 利潤比率 | 券商/入口 |
| 營業費用 | 損益表季度拆解、稅率、週轉天數 | histock 週轉天數優先；MoneyLink 已公布財報推導最新缺口 | 入口／財報回補 |
| 每股盈餘(EPS) | EPS成長率、PE分位目標價矩陣 | Fubon 經營績效、histock | 券商/入口 |
| 財報健檢 | 資產負債表/損益表/獲利率摘要 | TWSE OpenAPI 官方資料集（t187ap06/07_L_ci, t187ap17_L） | 官方，優先 |
| 股息&現金流 | 除權息歷史、現金流量表 | histock 除權息；MoneyLink 當期現金流、FinMind 歷史回補、histock 簡表 fallback | 當期正式來源優先／歷史補充 |
| 籌碼（個股層級） | 法人買賣超、大戶比、融資券、分點 | histock、Fubon | 入口/券商 |
| 期貨籌碼（大盤層級） | 三大法人期貨未平倉 | `taifex.com.tw`（官方） | 官方，優先 |
| 三大法人買賣超（大盤層級） | 上市／上櫃全市場三大法人買賣金額合計 | TWSE `rwd/zh/fund/BFI82U`；TPEX 開放 API `tpex_3insti_summary`（皆官方） | 官方，優先 |
| 融資融券增減（大盤層級） | 上市／上櫃全市場融資融券餘額 | TWSE `rwd/zh/marginTrading/MI_MARGN`（官方合計端點）；TPEX 無官方合計端點，改用開放 API `tpex_mainboard_margin_balance` 逐股資料在 scraper 內加總（仍為官方數字） | 官方，優先 |
| 排行榜 | 上市櫃成交值、券資比、週轉率股池 | TWSE OpenAPI STOCK_DAY_ALL；Fubon eBroker DJ 補上櫃與另兩種指標，並補官方源延遲日 | 官方優先／券商補充 |
| 板塊動能排名 | 類股輪動觀察（20/60/120日相對強度百分位排名） | TWSE MI_INDEX（官方，每日增量）／FinMind TaiwanStockPrice（入口，僅一次性歷史回補用） | 官方優先，FinMind 僅回補用 |
| 細產業動能排名 | 台灣前100大成分股依細產業分組的動能排名 | TAIFEX 月市值權重（股票池，官方）／FinMind TaiwanStockIndustryChain（標籤，需付費）／TaiwanStockPrice（僅歷史回補） | 股票池官方優先；FinMind 欄位依契約受限；見 `docs/specs/sector-momentum-formula-contract.md` |
| 減資一覽表 | 減資股 EPS 校正值 | `www.twse.com.tw/rwd/zh/reducation/TWTAVU`（官方減資預告表） | 官方，優先 |
| 重大訊息 | 個股每日重大訊息公告 | TWSE OpenAPI `t187ap04_L`；歷史回補用 MOPS `t05st01`（依代號查詢） | 官方，優先 |
| 內部人持股轉讓（大額賣股） | 董監/大股東持股轉讓事前申報 | TWSE OpenAPI `t187ap12_L`／`t187ap13_L` | 官方，優先 |
| 董監事持股與質押 | 董事長/董監事名單、持股、設質比例 | TWSE OpenAPI `t187ap11_L` | 官方，優先 |
| 大股東名單 | 持股逾 10% 大股東 | TWSE OpenAPI `t187ap02_L` | 官方，優先 |
| 個股 vs 大盤估值比較 | 個股本益比／殖利率相對全市場中位數的溢價／折價 % | TWSE OpenAPI `BWIBBU_ALL`（官方，全市場單一請求快照） | 官方，優先；上市限定，見 `docs/specs/valuation-benchmark-contract.md` |

**資料覆蓋缺口**：網站能力與資料表已保留市值排行、完整損益、資產負債細目、日股價、法人、融資券、券商分點與 ETF 持股。資產負債與現金流細目由 MoneyLink 提供當期資料，FinMind 回補歷史季度；同季一律保留 MoneyLink。HiStock 尚未提供最新週轉天數時，可由已公布的 MoneyLink 資產負債表與損益表依相同口徑回補。來源仍未發布的季度維持 `null`，前端標明目前截至季度，不得補零或推估。其他尚未接妥來源時 API 回傳空陣列，前端顯示「待補資料源」。估值在缺少 `income_statement_quarterly` 時可用 `margin_quarterly` 推回營業費用，但會附警告；缺少 65 個月 `pe_monthly` 時可用季底股價／TTM EPS 暫代，並標示為非正式月 PE 河流口徑。這兩種 fallback 不得視為正式驗收完成。

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
- `chips_daily(code, date, concentration_pct, foreign_holding_pct, big_holder_pct, insider_holding_pct, fetched_at)` — 個股層級大戶／外資持股與籌碼集中度；融資券餘額與法人買賣超已拆到 `margin_short_daily`／`institutional_trading_daily`，不在這張表
- `futures_oi_daily(date, institution, contract, long_oi, short_oi, net_oi, fetched_at)` — 大盤層級期貨未平倉
- `market_institutional_trading_daily(date, market, institution, buy_amount, sell_amount, net_amount, source, fetched_at)` — 大盤層級三大法人買賣超（TWSE/TPEX 各自最新一天，非個股加總）
- `market_margin_short_daily(date, market, margin_buy, margin_sell, margin_redemption, margin_balance, short_buy, short_sell, short_redemption, short_balance, source, fetched_at)` — 大盤層級融資融券增減（單位：張，跟個股層級 `margin_short_daily` 一致，方便相對強弱比較）
- `rankings_daily(date, category, rank, code, name, value, source, fetched_at)`
- `market_cap_daily(date, code, rank, name, market_cap, pct_of_market, fetched_at)` — TAIFEX 官方月市值權重
- `sector_index_daily(date, index_name, close_index, change_direction, change_points, change_pct, remark, source, fetched_at)` — 板塊動能排名用，見 `docs/specs/sector-momentum-formula-contract.md`
- `stock_industry_chain(stock_id, industry, sub_industry, tagged_at, fetched_at)` — 股票↔細產業標籤，慢變動維度表非時序
- `stock_universe_top100(as_of_date, rank, stock_id, stock_name, market_value, source, fetched_at)` — 台灣前100大股票池；canonical 來源為 TAIFEX 月市值權重
- `capital_reductions(name PK, code, stop_date, resume_date, exchange_ratio, adjust_factor, reason, source, fetched_at)`
- `board_holdings_monthly(code, report_month, title, person_name, shares_held, pledged_shares, pledged_ratio, source, fetched_at)` — TWSE 董監事持股與設質明細
- `major_shareholders(code, as_of_date, shareholder_name, source, fetched_at)` — TWSE 持股逾 10% 大股東名單
- `stock_valuation_daily(date, code, pe_ratio, dividend_yield_pct, pb_ratio, source, fetched_at)` — TWSE 官方全市場本益比／殖利率／PBR 快照，用來算大盤中位數比較基準，見 `docs/specs/valuation-benchmark-contract.md`
- `ingestion_runs(dataset_id, scope_key, source, started_at, finished_at, status, data_as_of, row_count, error)` — 每次 ETL 稽核紀錄
- `dataset_watermarks(dataset_id, scope_key, canonical_source, data_as_of, last_success_at, row_count)` — 經來源裁決後的供應水位
- `income_statement_quarterly`、`balance_sheet_quarterly`、`operating_efficiency_quarterly` — 完整季度領域
- `pe_monthly`、`stock_prices_daily` — PE 河流與 K 線歷史
- `stock_events`、`dividend_annual`、`etf_holdings`、`institutional_trading_daily`、`margin_short_daily`、`broker_branches_daily` — 事件、年度股利與個股層級籌碼領域；`institutional_trading_daily`／`margin_short_daily` 都是逐股（`code` 為主鍵一部分），對應的大盤層級版本見上方 `market_institutional_trading_daily`／`market_margin_short_daily`；`stock_events` 的 `event_type` 含 `material_news`（重大訊息，TWSE `t187ap04_L`）、`insider_transfer`（內部人持股轉讓，TWSE `t187ap12_L`/`t187ap13_L`）

## 驗收標準

每個功能落地時：

1. scraper 對真實來源跑過一次，資料寫進 SQLite，欄位型別正確（非全 NULL）
2. 已核對的固定基準案例與 golden-value pytest 通過
3. API endpoint 回傳該功能資料，前端頁籤能顯示
4. 九宮格與股價預估要等其依賴的資料領域完成後才能組裝

## 產品呈現與資料時效契約

- 儀表板先回答決策問題，再提供明細；營運基本面預設只呈現月營收、利潤率、EPS 三組關鍵圖，明細改由「表格」模式查看。
- 翁氏九宮格在桌機寬度必須同頁維持 3 × 3，可直接橫向、縲向比較；延伸圖表預設收合。
- 所有圖表共用座標、圖例與游標提示規格。長條圖每一根都必須標示所屬日期；縮放瀏覽器時不得累乘 Canvas 高度或破壞比例。
- 資料日期分頻率揭露：每日行情、月營收、季財報各自顯示資料截止日，不以單一擷取時間混稱為資料日期。
- 伺服器運行期間於台北時間週一至週五 18:30 背景刷新已追蹤股票與市場排行；使用者也可由頁首手動更新。兩者都必須保留舊資料直到新資料成功寫入。
- 市場排行是股池發現工具，資訊架構採「排行主題 → 上市／上櫃 → 個股明細」三層。成交值、券資比與週轉率是不同指標，不得互相冒充；資料源未接妥時顯示缺口。
- 大盤層級籌碼（指數走勢、三大法人買賣超、融資融券增減、期貨未平倉、市值占大盤比重、產業資金流向）是獨立頂層 view（`/api/market/overview`），不需先搜尋股票代碼即可見，跟個股 workspace 平行；個股頁「籌碼與市場」分頁只放個股層級籌碼，並附一張精簡的大盤快照卡（同一份資料）供相對強弱比較，不重複整份大盤報表。

## 風險邊界

- 官方源（TWSE、MOPS、TAIFEX）優先；券商/入口網站僅補充，HTML 結構視為會變，parser 要能優雅失敗
- 爬蟲節流：同股票同資料源每日最多一次；失敗時用快取舊資料，不整頁掛掉
- `app-origin` 是新建的公開 repo（`Zenobia000/tw-stock-fundamentals`），跟這個資料夾原本掛的教材 repo `origin` 無關，不要動 `origin`
