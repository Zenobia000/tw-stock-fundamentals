# CLAUDE.md

## 專案是什麼

個人使用的台股研究平台：以公開資料、可追溯估值模型、SQLite 歷史資料與終端風格 UI，整合個股估值、營運品質、蘭氏九宮格及市場籌碼。

輸入股票代碼 → 抓回基本面／籌碼面資料 → 跑估值鏈算出預估 EPS 與目標價 → 九宮格圖表呈現。

## 專案契約

契約全文在 `docs/agents/project.md`（來源分析、資料表 schema、估值公式、驗收標準）。修改資料流、schema 或估值公式前先讀那份文件；那份文件過時就先更新它，不要憑記憶做決策。

**Quality commands**

- Install/sync: `uv sync`
- Focused test: `uv run pytest tests/<path> -k <name>`
- Full test: `uv run pytest`
- Lint: `uv run ruff check .`
- Refresh data: `uv run python -m app.ingest 2330 3037`
- Run dev server（第一次啟動）: `uv run uvicorn app.main:app --reload`
- Restart dev server（port 已有殘留進程、或路由沒更新到最新程式碼時用這個）: `./scripts/restart-dev-server.ps1`——用 `taskkill /F /T` 把整棵 process tree（含 `--reload` 用 multiprocessing 生出來的 worker 子行程）殺乾淨再重開，並自動 smoke-test `/api/market/overview`。只用 `Ctrl+C` 或關終端機結束 `--reload` 常會留下孤兒 worker 卡住 port，之後同一個 port 會被舊 worker 跟新 worker 隨機分流回應（見 2026-08-23 大盤總覽 404 的事故）

**Git workflow**

- Remote：`origin` → `https://github.com/Zenobia000/tw-stock-fundamentals`（唯一 remote；原本叫 `app-origin`，這個資料夾原本教材 repo 的舊 `origin` 已移除，2026-08-23 把 `app-origin` 改名回 `origin`）
- Branch：`main`（唯一開發分支，push 到 `origin/main`；`product` 已於 2026-08-23 fast-forward 進 main 後刪除）
- Commit style：Conventional Commits，body 說明 WHY

**Risk boundary**

- 需再次確認：force push、刪除資料庫檔案、大量高頻爬取（可能觸發對方網站封鎖）
- 對外部網站爬蟲一律：附正常 User-Agent、單一股票查詢節流（同一股票同一資料源每日最多重抓一次，靠 `fetched_at` 快取判斷）、失敗時降級用快取舊資料而非整頁失敗
- 官方資料源（TWSE ISIN、MOPS、TAIFEX）優先於券商/入口網站（Fubon eBroker DJ、CMoney、histock、money-link、MoneyDJ）；後者僅在無官方等價資料時使用，且要假設 HTML 結構會變、每個 scraper 要能優雅失敗並記錄

## 開發方式

每個研究功能落地前：

1. 用瀏覽器或 `httpx` 打一次真實來源，確認實際 HTML 結構與資料單位（來源網站會變）
2. 寫最小 scraper，正規化成 SQLite schema
3. 以已核對的官方資料或固定基準案例寫 golden-value 測試，紅燈證據保留
4. 轉綠後才接進 API／前端

不確定的官方資料端點，先用 WebFetch/瀏覽器確認回應格式，不要憑猜測寫 parser。

## 回覆方式

- 使用繁體中文，技術術語保留英文。
- 結論先行，只保留一條主要建議。
- 每次回覆結尾給一個可執行的下一步。
