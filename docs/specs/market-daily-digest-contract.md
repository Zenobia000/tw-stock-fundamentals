# 大盤日報 — 資料與公式契約

## 背景

個人盤後選股／市場理解系統：收盤後跑一次批次，把「現貨法人（三大法人）× 期貨籌碼（含大戶集中度）× 融資融券（散戶代理）」三層資料交叉比對成同步／背離訊號，再依產業資金流向與個股連續買超篩出候選股清單。不是即時看盤工具——即時監控留給訂閱的 XQ 全球贏家、籌碼K線。定位討論與研究來源見設計理念 artifact（產品設計理念草稿，2026-08-23 整合）。

**範圍邊界（已定案）**：

| 保留 | 排除 |
|---|---|
| 大盤／期貨每日 OHLC 與結算摘要 | 大盤／期貨即時分鐘走勢圖 |
| 大盤層級三大法人買賣超、融資融券（已有） | 分鐘級事件時間軸標註 |
| 期貨三大法人未平倉（已有）＋大戶集中度（新增） | 大盤即時委買委賣 |
| 依買賣超金額計算的產業資金流向（新增） | 盤中焦點快訊／即時新聞 |
| 三層同步判讀訊號（新增，本契約核心） | — |

**2026-08-24 更新**：4.5 節「選股候選清單」（`overview.stock_candidates`）已停用並被 IA 改版取代，見下方「選股候選清單的後續」。

## 現況盤點（不重造已有的輪子）

`app/dashboard_v2_service.py` 的 `build_market_overview()` 與 `GET /api/market/overview` 已整合：`market_institutional_trading_daily`（大盤層級三大法人，TWSE／TPEX 分開，且拆到「自營商(自行買賣)／自營商(避險)／投信／外資及陸資／外資自營商／合計」六個身份別）、`market_margin_short_daily`（大盤層級融資融券）、`futures_oi_daily`（期貨三大法人未平倉）、`sector_index_daily`（含板塊動能與細產業樞紐）、`market_cap_daily`、`rankings_daily`。這些是本契約的既有輸入，不重複定義。

真正缺的只有四件事，也是本契約新增的範圍：

1. 期貨大戶集中度（十大交易人／十大特定人／散戶淨未平倉）
2. 大盤／期貨每日 OHLC（目前 `sector_index_daily` 只有收盤與漲跌幅，`futures_oi_daily` 只有未平倉口數沒有價格）
3. 依買賣超金額計算的產業資金流向（板塊動能是報酬排名，口徑不同，見下方「與板塊動能的關係」）
4. 三層同步判讀公式 ＋ 選股候選清單（唯一的新公式）

## 資料源與新增 Schema

### 3.1 期貨大戶集中度 — `futures_large_trader_oi_daily`

來源：TAIFEX 大額交易人未沖銷部位結構表（`https://www.taifex.com.tw/cht/3/largeTraderFutQry`，官方）。**實際欄位與回應格式尚未用 WebFetch／瀏覽器核對過**，依 `CLAUDE.md` 開發流程規定，實作前必須先打一次真實來源確認 HTML 結構與資料單位，不得依本契約描述直接憑猜測寫 parser；以下欄位是目標語意，不是已驗證的來源格式。

```sql
CREATE TABLE IF NOT EXISTS futures_large_trader_oi_daily (
    date TEXT NOT NULL,
    contract TEXT NOT NULL,        -- e.g. 臺股期貨
    trader_group TEXT NOT NULL,    -- '十大交易人' / '十大特定法人'
    long_oi INTEGER,
    short_oi INTEGER,
    net_oi INTEGER,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, contract, trader_group)
);
```

散戶淨未平倉不落地新表，沿用截圖裡「散戶＝反推」的既有業界作法：`散戶淨未平倉 ≈ -(外資淨未平倉 + 十大交易人淨未平倉中非外資部分)`，實作時以 `futures_oi_daily`（三大法人）與本表（十大交易人／特定人）已有數字計算式呈現，不單獨儲存，避免自建一個無法對帳回官方數字的衍生欄位。

### 3.2 大盤／期貨每日 OHLC

- `sector_index_daily` 新增 `open_index REAL`、`high_index REAL`、`low_index REAL` 三欄（TWSE `MI_INDEX` 是否提供開高低需先用 WebFetch 核對，未提供則維持 NULL，不得用收盤價回推假造）。
- 新表 `futures_price_daily`（台指期貨本身的價格，`futures_oi_daily` 目前只有未平倉口數）：

```sql
CREATE TABLE IF NOT EXISTS futures_price_daily (
    date TEXT NOT NULL,
    contract TEXT NOT NULL,        -- e.g. 臺股期貨
    session TEXT NOT NULL,         -- 'day' / 'night'
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    settlement_price REAL,
    change_pct REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, contract, session)
);
```

來源：TAIFEX 期貨每日交易行情（官方）。夜盤（`session='night'`）資料歸屬「次一交易日」，比照 TAIFEX 官方歸屬規則，不比照自然日。

### 3.3 產業資金流向（依金額，區別於板塊動能）

不落地額外原始資料表；由既有 `institutional_trading_daily`（個股層級三大法人買賣超）依 `stock_industry_chain` 的 `industry` 分組加總得出，屬衍生計算結果。依 `docs/specs/data-strategy-contract.md` 的「衍生結果須帶 `formula_version` 與 `as_of`」原則，落地一張快取表方便前端 treemap 查詢與之後做「連續 N 日資金流向」特徵，而非每次請求即時算：

```sql
CREATE TABLE IF NOT EXISTS industry_capital_flow_daily (
    date TEXT NOT NULL,
    industry TEXT NOT NULL,
    net_amount REAL,           -- 該產業當日三大法人買賣超金額加總
    turnover_amount REAL,      -- 該產業當日成交金額加總（面積用）
    member_count INTEGER,      -- 實際納入計算的成分股數
    formula_version TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (date, industry)
);
```

**與板塊動能的關係**：`sector_index_daily` 驅動的板塊動能（`docs/specs/sector-momentum-formula-contract.md`）是「20/60/120 日相對強度報酬排名」，回答「哪個板塊持續比大盤強」；這裡新增的產業資金流向是「當日買賣超金額」，回答「今天錢實際往哪裡流」。兩者口徑不同、互補，不得互相取代或合併成同一個排序欄位。

## 公式定義（`app/calc/market_sync.py`）

### 4.1 現貨 × 期貨同步（以外資為例）

- `spot_direction`：`market_institutional_trading_daily` 外資（`外資及陸資` ＋ `外資自營商` 合計）當日 `net_amount` 正負 → `BUY` / `SELL`。
- `futures_direction`：`futures_oi_daily` 外資 `net_oi` 相較前一交易日的增減方向 → `INCREASING` / `DECREASING`（判斷的是「變化方向」，不是單日多空口數的正負，對應第 3 節矩陣的「淨多單增加／減少」語意）。
- 對照表同設計理念 artifact 第 3.1 節四象限：`BUY`+`INCREASING` 或 `SELL`+`DECREASING` → `SYNCED`；其餘兩種組合 → `DIVERGED`（僅標示背離，不判斷是出貨還是避險，留給使用者自己核對第 3.4 節提示文字）。

### 4.2 法人 × 融資融券同步

- `margin_direction`：`market_margin_short_daily` 融資餘額 (`margin_balance`) 相較前一交易日的變動率。
- **警訊閾值（可調參數，非官方公認公式，先以此為預設）**：`abs(變動率) >= 2%` 視為「大增／大減」。
  - `spot_direction=BUY` 且融資「大增」 → `法人-散戶對做警訊`
  - `spot_direction=SELL` 且融資「大減」 → `築底訊號`
  - 其餘 → `一般`

### 4.3 大戶集中度

- `large_trader_agree`：`futures_large_trader_oi_daily` 十大交易人 `net_oi` 與十大特定人 `net_oi` 正負號是否一致（布林）。資料未到位（3.1 節新表）前，此欄位一律回傳 `null`，前端顯示「資料待補」，不得省略成 `true`。

### 4.4 綜合訊號燈 `sync_signal`

依 4.1～4.3 合成單一狀態，不做多空建議，只顯示客觀事實：

- `GREEN`（同步）：4.1 為 `SYNCED` 且 4.2 非「對做警訊」。
- `RED`（明顯背離）：4.2 判定為「法人-散戶對做警訊」。
- `YELLOW`（部分背離）：其餘情況，含 4.1 為 `DIVERGED` 但未達 4.2 警訊閾值、或 4.3 資料不足。

文字提示一律用「留意」而非「應該／建議」（呼應第 6 節 Q4 決議），例如：「外資現貨買超同時期貨空單增加，留意現貨拉高出貨的可能性」。

### 4.5 選股候選清單

1. 依 `industry_capital_flow_daily` 當日 `net_amount` 排名前 N 大流入產業（N 預設 5，可調）。
2. 這些產業成分股（`stock_industry_chain` 對應 `industry`）中，`institutional_trading_daily` 當日買超金額為正、且連續買超天數 ≥ 2 的個股。
3. 若當日 `sync_signal = RED`，當天不產生新增候選（避免在法人-散戶對做警訊當下選股），沿用既有候選但標示「今日暫停新增」。
4. 輸出欄位：股票代碼、名稱、所屬產業、連續買超天數、產業資金流向排名、當日 `sync_signal`。**不含目標價或買賣建議**——維持本專案一貫「只做可追溯資料呈現，不做投資建議」的定位。

### 選股候選清單的後續（2026-08-24）

上面 4.5 節描述的「依產業資金流向＋連續買超天數＋`sync_signal` 閘門」候選清單，已被 IA 改版（使用者要求把 Dashboard 重要資訊往上擺、次要資訊收進第二層）取代，不再接進 `/api/market/overview`：

- 模組 `app/calc/stock_candidates.py` 與 `tests/test_stock_candidates.py` 保留檔案作歷史對照，不刪除，但呼叫端已移除。
- 取代它的是 `app/calc/stock_rankings.py`（`overview.stock_rankings`）：台灣前100大成分股當日強勢股／弱勢股／成交量／漲停／跌停五個排行維度，**不含**連續買超天數、產業資金流向排名或 `sync_signal` 閘門這些條件——是單純的當日排行榜，不是「候選」語意。
- 同一輪改版新增 `app/calc/industry_rankings.py`（`overview.industry_rankings`）：依 `stock_industry_chain` 分組的產業漲幅／跌幅／成交量／成交金額排行（成交金額加權平均近似值，非官方板塊指數），含 `members_by_industry` 供點擊產業看成分股。
- 若之後要重新做「候選清單」語意的功能，應該重新評估要不要接回 4.5 節這套公式，或設計新公式；不要假設 `stock_candidates.py` 還能直接接回去用（`market_stock_snapshot_daily`／`stock_universe_top100` 等周邊資料表在這之後也持續在變動）。

## API 邊界（擴充既有 `/api/market/overview`）

沿用現有「單一入口」慣例（板塊動能、細產業動能都已整併進 `build_market_overview()`），新增欄位而非另開分散端點：

- `overview.futures_large_trader`：十大交易人／十大特定人淨未平倉
- `overview.index_ohlc`：`twse`/`otc` 當日收盤摘要（含 `open_index`/`high_index`/`low_index`/`amplitude_pct`/`high_low_spread`，櫃買指數暫無官方開高低故為 `null`）、`futures` 最新一筆日盤+夜盤、`futures_series`（台指期貨日盤歷史 OHLC 序列）、`otc_trend`（櫃買指數收盤歷史序列）——後兩者是給 K 線細項與「指數對照」疊圖頁用的完整序列，不只是最新一筆
- `overview.industry_capital_flow`：產業資金流向排行（treemap 用），已與 `industry_rankings` 的 `members_by_industry` 合併呈現
- `overview.sync_signal`：4.4 節燈號與明細
- `overview.stock_rankings`：見上方「選股候選清單的後續」，取代 `overview.stock_candidates`
- `overview.industry_rankings`：見上方「選股候選清單的後續」
- `overview.stock_change_distribution`：個股漲跌分佈，含 `monthly_high_count`/`monthly_low_count`（歷史交易日不足 20 天時為 `null`，不是 0）與對應成分股清單

`GET /api/market/overview` 維持現有回傳結構向後相容，新欄位缺資料時回傳 `null` 或空陣列，不得省略欄位或用 `0` 偽裝。

## 驗收標準

1. `futures_large_trader_oi_daily` 與 `futures_price_daily` 的 scraper 對真實 TAIFEX 來源跑過一次，欄位型別正確（非全 NULL），且已用 WebFetch／瀏覽器核對過實際 HTML 結構（不得依本文件臆測欄位直接寫 parser）。
2. `industry_capital_flow_daily` 的固定基準案例（挑一個已知交易日與產業）與手算金額一致，golden-value pytest 通過。
3. `sync_signal` 四種狀態（`SYNCED`／`DIVERGED`／對做警訊／築底訊號）各自至少一組固定基準案例覆蓋，含「大戶資料缺失時 `large_trader_agree` 回傳 `null`」的邊界情況。
4. ~~`stock_candidates` 在 `sync_signal=RED` 當日不新增候選的規則有測試覆蓋。~~ 該功能已停用（見上方「選股候選清單的後續」），規則仍由 `tests/test_stock_candidates.py` 覆蓋已停用模組本身，但不再是 `/api/market/overview` 的驗收項目。
5. `GET /api/market/overview` 新增欄位後，既有測試（`tests/test_dashboard_v2_market_overview.py`）維持綠燈，不破壞既有回傳結構。
6. 前端新增產業資金流向 treemap 元件，面積綁定 `turnover_amount`、顏色綁定 `net_amount` 正規化值，不綁定單純漲跌幅（呼應設計理念 artifact 第 4 節原則）。
7. 所有新欄位在畫面上標示資料來源與 `fetched_at`／`data_as_of`，不得讓使用者誤以為是即時資料。
