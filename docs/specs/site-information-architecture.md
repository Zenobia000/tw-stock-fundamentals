# 產品資訊架構契約

## 原則

網站依個人投資決策流程整合成六個主要功能區。所有頁面共用同一份正規化歷史資料、
公式引擎與資料新鮮度資訊，不在前端重複推導公式。

## 六大功能區

| 功能區 | 研究範圍 | 必備功能 |
|---|---|---|
| 決策總覽 | 估值與公司事件 | 八個模型選項、估值鏈、中間值、預估季/TTM EPS、PE 河流、目標價、PEG、股利、殖利率、總報酬、減資警示、紅綠訊號 |
| 營運基本面 | 營收、獲利與 EPS | 月營收與 YoY、3/12 月動能、八季損益、毛利/營益、業外、本業比率、推銷/管理/研發費、季與 TTM EPS |
| 財務品質與股東回報 | 財務結構與現金回報 | 資產負債、收款/存貨/付款天數、負債與流動比、三大現金流、自由現金流、股利/發放率/殖利率/填息、公司事件（重大訊息/內部人持股轉讓）與減資、董監事持股與質押比例、大股東名單 |
| 翁氏九宮格 | 九項核心品質指標 | 九張八季核心比較圖、月營收布林、合約負債、K 線；共用季度軸、單位與紅綠判讀 |
| 籌碼與市場雷達 | 個股與全市場籌碼 | 法人/大戶/董監、融資券、券資比、分點、期貨日夜盤、上市櫃排行榜與市值占比 |
| 板塊動能觀察 | 全市場板塊輪動 | TWSE 官方類股指數 20/60/120 日報酬同組百分位排名、對大盤超額報酬、20/40/40 加權綜合 Rank；不需先選股票，獨立頁籤；內含「細產業」子分頁（FinMind industry→sub_industry 兩層可展開樞紐表，台灣前100大成分股動能排名，含 120 日走勢 sparkline、可排序欄位、無 REL） |

## 跨頁能力

| 跨域能力 | 網站去向 |
|---|---|
| 股票資訊、證券編碼查詢 | 全域股票搜尋與固定個股資訊列；重要日期、ETF 與上下游資訊可展開 |
| 模型與資料說明 | 公式/資料來源說明抽屜與新手導覽，不進主導覽 |
| 減資一覽表 | 公司事件資料與估值校正警示；維護介面屬管理功能 |

## 九宮格固定語意

1. 營收 + 毛利率/淨利率
2. 收款/存貨/付款天數
3. 營業/自由現金流 + 負債比
4. 營業現金流 vs 營業利益 + ROE
5. 資本支出 + 弦值
6. 本業/業外 EPS + 本業比率
7. 營收同季比較
8. 營運天數同季比較
9. 近一年現金流分類

延伸區固定為月營收 3/12 月均線與布林、合約負債、股價 K 線。九宮格至少使用八季，
月營收至少 24 月；PE 河流依原始 HiStock 表格使用 65 個月樣本。

## 資料領域

- 公司與事件：`stocks`、`stock_info`、`stock_events`（含 `material_news`、`insider_transfer`）、`capital_reductions`、`board_holdings_monthly`、`major_shareholders`、`dividend_annual`、`etf_holdings`
- 月資料：`revenue_monthly`、`pe_monthly`
- 季資料：`income_statement_quarterly`、`financial_health_quarterly`、
  `cashflow_quarterly`、`operating_efficiency_quarterly`
- 日/週資料：`stock_prices_daily`、`chips_daily`、`broker_branches_daily`、
  `futures_oi_daily`、`rankings_daily`、`market_cap_daily`、`sector_index_daily`
- 慢變動維度資料：`stock_industry_chain`（股票↔細產業標籤）、
  `stock_universe_top100`（台灣前100大成分股快照）

每筆事實資料須能追溯 `source`、資料期間與 `fetched_at`。衍生結果須帶 `formula_version`
與 `as_of`，讓歷史快照可重現。

## API 邊界

- `GET /api/stocks/{code}/dashboard-v2`：全域個股資訊、決策總覽、五區資料可用性與更新時間
- `GET /api/stocks/{code}/fundamentals`：營運基本面時間序列
- `GET /api/stocks/{code}/financial-quality`：財務品質與股東回報
- `GET /api/stocks/{code}/nine-grid`：八季標準化圖表 view model
- `GET /api/stocks/{code}/chips-market`：個股籌碼
- `GET /api/market/radar`：期貨、排行榜與市值雷達
- `GET /api/market/sector-momentum`：板塊動能排名（見 `docs/specs/sector-momentum-formula-contract.md`）
- `GET /api/market/sub-industry-momentum`：細產業動能排名（同一份公式契約「細產業版」一節）
- `POST /api/market/sub-industry-momentum/refresh` ／ `GET .../refresh-status`：手動觸發細產業資料回補的背景工作（比照個股 `refresh`／`refresh-status` 同一套輪詢模式）

## 驗收矩陣

1. 六大功能區的每項使用者能力都有網站去向或明確的背景服務去向。
2. 2330 固定基準案例的預設選項必須得到：預估季 EPS `29.2687245391`、預估 TTM EPS
   `98.1087245391`、PE 平均 `23.1073846154`、母體標準差 `5.8994905326`。
3. 八個模型選項切換後由後端重算；前端不自行複製核心公式。
4. 換股票後所有區域以同一 `code`、`as_of` 與資料版本刷新，不需手動貼值。
5. 每個區塊顯示來源、更新時間、缺項與過期狀態；缺資料不可用 `0` 偽裝。
6. 板塊動能觀察頁籤不依賴已選股票的 `code`，可獨立瀏覽；歷史不足 121 個交易日時
   對應板塊的 `rank_120d`／`rank` 回傳 `null`，不得以 0 或其他數字填補。
7. 細產業子分頁不得顯示 REL 欄位（沒有天然 benchmark 可比）；`member_count` 必須
   如實顯示，不得隱藏成分股數過少、排名參考價值較低的組別。
8. 細產業樞紐表的父層是 FinMind 自身的 industry（不是 TWSE 板塊分類，兩套分類
   系統不同），預設全部收合；sub_industry 子層排名口徑維持全市場（不因巢狀顯示
   限縮母體）；欄位標題可點擊排序，排序只影響父層順序，不影響子層內部順序。
