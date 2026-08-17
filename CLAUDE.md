# CLAUDE.md

## 專案是什麼

台股波段股價預估網站：把使用者原本在 Google Sheets／Excel（`reference/波段股價預估試算_sunny_v2.xlsx`）手動維護的「蘭氏」基本面選股模型，轉成一個可爬蟲自動更新、SQLite 儲存歷史快照、彭博終端風格 UI 的網站。

輸入股票代碼 → 抓回基本面／籌碼面資料 → 跑估值鏈算出預估 EPS 與目標價 → 九宮格圖表呈現。

## 專案契約

契約全文在 `docs/agents/project.md`（來源分析、資料表 schema、估值公式、驗收標準）。修改資料流、schema 或估值公式前先讀那份文件；那份文件過時就先更新它，不要憑記憶做決策。

**Quality commands**

- Focused test: `poetry run pytest tests/<path> -k <name>`
- Full test: `poetry run pytest`
- Lint: `poetry run ruff check .`
- Run dev server: `poetry run uvicorn app.main:app --reload`

**Git workflow**

- Remote：`app-origin` → `https://github.com/Zenobia000/tw-stock-fundamentals`（新 repo，與這個資料夾原本的教材 repo `origin` 無關，不要 push 到 `origin`）
- Branch：`product`（目前開發分支，push 到 app-origin 的 `main`）
- Commit style：Conventional Commits，body 說明 WHY

**Risk boundary**

- 需再次確認：force push、刪除資料庫檔案、大量高頻爬取（可能觸發對方網站封鎖）
- 對外部網站爬蟲一律：附正常 User-Agent、單一股票查詢節流（同一股票同一資料源每日最多重抓一次，靠 `fetched_at` 快取判斷）、失敗時降級用快取舊資料而非整頁失敗
- 官方資料源（TWSE ISIN、MOPS、TAIFEX）優先於券商/入口網站（Fubon eBroker DJ、CMoney、histock、money-link、MoneyDJ）；後者僅在無官方等價資料時使用，且要假設 HTML 結構會變、每個 scraper 要能優雅失敗並記錄

## 開發方式

每個 sheet = 一個功能，任務清單見 session 內的 TaskList。每個功能落地前：

1. 用瀏覽器或 `httpx` 打一次真實來源，確認實際 HTML 結構（不要假設跟 Excel 裡記錄的一致，來源網站會變）
2. 寫最小 scraper，正規化成 SQLite schema
3. 對照 `reference/` 工作表裡的快照值（尤其「財報健檢」頁已有 TSMC 2Q26 官方數字）寫 golden-value 測試，紅燈證據保留
4. 轉綠後才接進 API／前端

不確定的官方資料端點，先用 WebFetch/瀏覽器確認回應格式，不要憑猜測寫 parser。

## 回覆方式

- 使用繁體中文，技術術語保留英文。
- 結論先行，只保留一條主要建議。
- 每次回覆結尾給一個可執行的下一步。
