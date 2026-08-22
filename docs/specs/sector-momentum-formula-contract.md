# 板塊動能觀察 — 公式契約

## 背景

仿照 Google Sheet「全市場動量觀察表｜Market Momentum Dashboard」(TheMarketMemo)
的相對強度動能輪動邏輯，套用在 TWSE 官方類股指數上。核心概念：在同一組標的
（板塊）內，用短中長期報酬做百分位排名，找出資金正在往哪個板塊移動。

母體：TWSE `MI_INDEX` 官方回應中名稱以「類指數」結尾的列（目前約 30～37 檔，
依 TWSE 當時公布的類股分類而定），不含大盤/規模指數（發行量加權股價指數、臺灣50
指數等）。Benchmark：`發行量加權股價指數`。

## 資料源

- 每日增量：`app.scrapers.twse_sector_index`（官方，`www.twse.com.tw/exchangeReport/MI_INDEX`）
- 歷史回補：`app.scrapers.finmind_sector_index`（FinMind，入口網站等級，僅一次性回補用；
  `FINMIND_TO_TWSE_NAME` 是用同一天收盤數字逐一核對過的對照表，不是憑名稱猜測）

兩個來源寫進同一張 `sector_index_daily` 表，`date` 一律正規化成 ISO `YYYY-MM-DD`。

## 公式定義（`app/calc/sector_momentum.py`）

- **N 日報酬** `n_day_return`：`(最新收盤 − N 個交易日前收盤) ÷ N 個交易日前收盤`。
  歷史不足 N+1 筆資料時回傳 `None`。
- **百分位排名** `percentile_rank`：某板塊的 N 日報酬，在當天所有板塊的 N 日報酬
  母體中的百分位排名，0～99，數值越大代表相對強度越高；並列用平均名次處理。
- **REL（相對大盤超額報酬）**：`板塊 N 日報酬 − benchmark N 日報酬`（同一個 N）。
- **Rank（綜合排名）** `composite_rank`：`20R`／`60R`／`120R` 的**簡單平均**。
  **這是我方近似值，不是 TheMarketMemo 原表 Rank 欄位的精確復刻**——從公開範本的
  樣本數字反推不出它實際用的加權公式（試過簡單平均與幾種加權組合都對不上部分列），
  所以先用最簡單、可解釋的簡單平均頂替。任一橫向報酬缺值時 `Rank` 整體回傳 `None`，
  不得用部分資料湊出一個假排名。

## 已知限制（板塊版）

- 只做到「板塊」顆粒度（等同官方類股分類，約 30～37 類）。細產業／概念股顆粒度見下方
  「細產業版」。
- `Rank` 加權公式是近似值（見上），不得對外宣稱等同 TheMarketMemo 原表數字。

## 細產業版

板塊層只有官方 ~30～37 類，顆粒度不夠細（沒有 AI伺服器/PCB/被動元件這種概念股層級）。
細產業版改用 FinMind Backer/Sponsor 等級的 `TaiwanStockIndustryChain`（逐股 industry/
sub_industry 標籤，47 個 industry、數百個 sub_industry），成分股限定「台灣前100大」
（依市值，見下方資料源），用成分股股價報酬組出等權重合成指數，套用**同一組**
`n_day_return`／`percentile_rank`／`composite_rank`（不重新發明公式）。

### 資料源

- `app.scrapers.finmind_industry_chain`（FinMind `TaiwanStockIndustryChain`，需要
  Backer/Sponsor 付費等級與 `FINMIND_API_TOKEN` 環境變數）：股票↔細產業標籤，`date`
  是「這筆標籤最後確認日」，不是逐日時序，屬於慢變動維度表，週期性回補即可，不需要
  每天刷新。
- `app.scrapers.taifex_market_cap` + `market_cap_daily`：前100大股票池的正式來源；使用
  TAIFEX 官方月市值權重，更新頻率跟來源一致，不宣稱為每日名單。
- `app.scrapers.finmind_market_value`（FinMind `TaiwanStockMarketValue` + `TaiwanStockInfo`
  排除 ETF）：只保留為明確指定的補充來源；2026-08-22 實測匿名／free 等級均回覆
  `Please update your user level`，不得列為目前可用的主來源。
- `app.scrapers.finmind_stock_price`：前100大成分股歷史股價一次性回補，寫進既有
  `stock_prices_daily`（`source='finmind-stock-history'`）；每日增量這輪不做，只交付
  「回補到目前為止」的靜態快照（見下方已知限制）。

### 合成指數定義（`app.calc.sector_momentum.equal_weighted_index`）

成分股上市時間不同、股價序列長度可能不一樣。取所有非空成分股序列共同覆蓋的最近
`min_len` 個交易日，每檔各自 rebase 成「這個共同窗口起點（最舊那天）=100」，橫斷面
取平均，組成等權重合成指數。這是我方近似合成指數，不是官方發布的產業指數。

### 跟板塊版的差異

- **沒有 REL（相對大盤超額報酬）欄位**：細產業沒有天然的 benchmark 可比，不像板塊層
  有官方大盤指數。
- 母體只涵蓋「台灣前100大成分股實際落在的 sub_industry」，`member_count` 欄位標示
  每組實際成分股數；`member_count` 少（例如只有1檔）的組排名參考價值較低，前端跟
  文件都要如實標示，不能隱藏這個限制。
- 一檔股票可能同時屬於多個 sub_industry（例如某公司同時做食品跟雲端運算），會分別
  計入兩邊的合成指數，不是 bug。

### 手動觸發回補（`app.sub_industry_refresh_service`）

前100大名單已經是官方 TAIFEX 每日排程自動更新，不需要手動觸發；但產業標籤跟
前100大成分股歷史股價還是要手動回補。網站「細產業」分頁上的「重新回補細產業
資料」按鈕（`POST /api/market/sub-industry-momentum/refresh` 觸發、
`GET .../refresh-status` 輪詢，跟個股「更新資料」按鈕同一套背景工作模式）依序
執行 `backfill_industry_chain` → `backfill_stock_universe` → `backfill_top100_prices_finmind`
三支腳本的 `main()`；單一步驟失敗不擋住其他步驟，回傳結果標示哪些步驟失敗與
原因（例如 `FINMIND_API_TOKEN` 未設定時，「產業標籤」那步會失敗，但「前100大
名單」「前100大股價」仍會正常完成，因為它們不依賴 Backer/Sponsor 權限）。

### 已知限制（細產業版）

- 每日增量目前不做，只有「回補當下」的靜態快照；股價資料會隨時間變舊，之後要接每日
  增量需要評估對官方 TWSE STOCK_DAY 逐日打 100 檔的請求量（風險邊界：大量高頻爬取），
  屬於下一輪工作範圍。
- 台灣前100大清單來自 TAIFEX 官方月市值權重，不是官方 0050 成分股清單；名單按月更新，
  `stock_universe_top100.source` 保留來源，供應版本以 `dataset_watermarks` 裁決。
- `TaiwanStockIndustryChain` 需要 FinMind 付費 Backer/Sponsor 等級才能存取，免費/
  register 等級會被拒絕（`Your level is free/register. Please update your user level.`）。
- `TaiwanStockMarketValue` 在目前帳號等級同樣不可用；除非權限驗證成功，不得讓它取代
  TAIFEX 股票池。
