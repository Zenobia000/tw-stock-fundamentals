# 資料策略契約

## 決策

本系統目前採「Python ETL + SQLite WAL + FastAPI」的單機架構。資料量、使用者數與
寫入模式都還不需要 Spark 或 PostgreSQL；現階段效能的主要風險是外部來源延遲、
重複請求、來源互相覆蓋，以及無法判斷資料日期，而不是單機運算量不足。

程式中的唯一正式契約是 `app/data_strategy.py`。新增或替換來源時，必須先在該檔案
登錄 dataset、來源角色、粒度、單位、更新頻率、SLA 與合併規則，才能接入 ETL。

## 五項不可破壞的規則

1. 相同資料期間以官方來源為 canonical；券商或入口網站不得覆蓋官方列。
2. 補充來源只能補官方尚未發布的較新期間，不能用「抓取時間較新」推翻「資料期間相同」的官方值。
3. 標為 `historical_backfill_only` 的來源只填歷史缺口；官方資料存在時必須保留官方值與 source。
4. 缺值維持 `NULL` 並在產品端揭露；不把缺值轉成 0，也不把 fallback 說成正式口徑。
5. 每次 ETL 都要留下 `ingestion_runs`；對外供應的資料水位由 `dataset_watermarks` 表示。

## 三種時間

- `data_as_of`：資料實際代表的交易日、月份、季度或年度，是新鮮度與衝突裁決的主鍵。
- `fetched_at`：本機何時成功取得並寫入該列，只用於快取與稽核，不能冒充資料日期。
- `last_success_at`：該 dataset/source 的 ETL 最後成功時間；來源成功但回來的是舊資料時，水位仍不能前進。

## 來源層級與裁決

- `official`：TWSE、TAIFEX 等官方資料，為同期間最高優先。
- `publisher`：券商公開頁面；可作官方延遲時的較新期間補充，或在無官方欄位時成為明定主源。
- `portal`：入口資料站；只用於契約明定的欄位、fallback 或歷史回補。
- `manual`：只有無穩定公開來源且可追溯維護者時使用；不得默默混進自動資料。

目前兩個已落地的來源保護：

- 上市成交值：TWSE 同日排行優先；Fubon 只寫入比現有官方水位更新的交易日。
- 板塊指數：FinMind 只做歷史回補；同一日期已有 TWSE MI_INDEX 時不可覆蓋。
- 資產負債與現金流：MoneyLink 同季資料優先；FinMind
  `TaiwanStockBalanceSheet`／`TaiwanStockCashFlowsStatement` 僅做歷史回補，HiStock
  現金流簡表為最低優先，任何回補來源都不能把既有完整欄位降級成空值。
- 營運效率：HiStock 週轉天數優先；若已公布的 MoneyLink 資產負債表與損益表
  比 HiStock 更新，可用季初／季末平均餘額與 90 天單季口徑補缺口，且不得覆蓋
  已有 HiStock 數值。
- 前百大股票池：TAIFEX 月市值權重為正式來源；FinMind MarketValue 權限驗證失敗時只記錄
  `failed`，不得推進 canonical watermark。

## 更新、失敗與服務規則

- 每個來源獨立失敗；其他來源繼續執行，畫面沿用既有 canonical 資料。
- `success` 表示步驟完成，`partial` 表示部分期間失敗，`failed` 表示來源或解析失敗。
- 背景個股更新使用最多 4 個 I/O worker，避免大量未知代碼同時建立無上限執行緒。
- 服務啟動時預設不掛每日排程；只有設定 `FORTUNE_ENABLE_SCHEDULED_REFRESH=1` 才啟用週間排程。
- SQLite 使用 WAL、`busy_timeout=5000ms`、`synchronous=NORMAL`，並為常用日期查詢建立索引。
- `/api/data-strategy` 提供契約與儲存邊界；`/api/data-strategy/status?code=2330` 提供水位與最近 ETL 紀錄。

## 健康狀態判定

`/api/data-health` 只在請求時依 watermark 與最近執行紀錄計算，不另建常駐監控服務：

- `healthy`：時效、分析所需最少列數與主要來源皆符合契約。
- `degraded`：仍有可用快取，但目前採備援來源，或最近更新失敗／部分完成。
- `incomplete`：資料日期正確，但歷史列數不足 `minimum_rows` 所定義的分析窗口。
- `stale`：交易日、月份或季度落後應有發布期間；週末不會要求不存在的交易日。
- `unavailable`：沒有 canonical watermark；若最新擷取失敗，保留失敗原因與 HTTP 狀態。
- `not_selected`：尚未選股票時的個股資料；不納入整體健康度。

每個資料集另定義 `importance`：`critical` 會直接影響核心判讀、`supporting` 用於交叉驗證、
`optional` 是額外脈絡。只有核心資料過期或不可用才把整體狀態標成「核心資料受阻」；輔助或
選配資料異常仍會列入優先清單，但整體只標示「需注意」，避免單一非核心來源造成告警疲勞。

允許正常為空的事件型資料必須明定 `allow_empty`，且只有成功完成的空結果才算健康；來源解析
失敗不會因為該資料「可能為空」就被掩蓋。瀏覽器的網站 API 回應時間只保留在本次頁面記憶體，
重新開頁即歸零，不寫入 SQLite。

## 升級門檻

只有出現下列任一條件，才把交易型儲存升級 PostgreSQL：

- 服務改成多人或多主機，且會同時寫入。
- 背景工作需要跨程序佇列、鎖與一致的 job claim。
- WAL 仍持續發生寫入鎖競爭，且縮短交易、建立索引與限制 worker 後仍無法解決。
- 需要線上 schema migration、權限隔離、備援或 point-in-time recovery。

若只是歷史行情掃描或大量研究查詢，先在 SQLite 旁加入 Parquet + DuckDB/Polars 的分析層；
不要因為查詢分析變大就直接把所有資料搬到 PostgreSQL。Spark 只在資料已跨多節點或單機
記憶體明顯不足時評估；Numba 只用在 profiling 證實為純數值迴圈瓶頸的模型計算。

## 變更驗收

新增資料集或來源時，PR/提交至少要包含：

1. `app/data_strategy.py` 的 policy 與 source 角色。
2. 原始 fixture、parser golden test、repository round-trip test。
3. 同期間來源衝突測試，證明低優先來源不能覆蓋高優先來源。
4. `ingestion_runs` 成功／失敗紀錄與 `dataset_watermarks` 水位測試。
5. 資料日期、單位、缺值與 fallback 在 API/畫面上的揭露。
