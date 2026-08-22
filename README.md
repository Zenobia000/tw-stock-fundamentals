# tw-stock-fundamentals

為個人投資研究打造的台股通用平台，整合「決策總覽、營運基本面、財務品質與回報、翁氏九宮格、籌碼與市場」五個區域。估值公式由 Python 後端統一運算，公開資料經正規化後保存於 SQLite，前端只負責一致地呈現研究結果。

## 快速開始

```bash
uv sync
uv run python -m app.ingest 2330 3037
uv run uvicorn app.main:app --reload
uv run pytest
```

`uv sync` 會依 `uv.lock` 建立或更新專案的 `.venv`。

服務預設採個人按需模式：啟動本身不會建立每日背景排程；查詢股票後可按「更新資料」，
資料健康中心也只在開啟或按「重新評估」時讀取本機狀態。若確實需要週間自動更新，才以
`FORTUNE_ENABLE_SCHEDULED_REFRESH=1 uv run uvicorn app.main:app` 明確啟用。

## 專案結構

```text
app/
  scrapers/   每個資料源一個 scraper 模組
  calc/       估值鏈、弦值、九宮格等純計算邏輯
  db/         SQLite schema 與存取
  api/        FastAPI route
web/          前端（純 HTML/CSS/JS，彭博終端風格）
tests/        pytest（含固定基準案例與 API 整合測試）
docs/agents/project.md       專案契約
docs/specs/   估值模型、資料來源與產品資訊架構
```

## 資料來源

官方來源優先（TWSE 證券編碼查詢、公開資訊觀測站 MOPS 財報、期交所期貨籌碼），券商/入口網站補充非官方公開資料。介面會把尚未落地的來源標成「待補資料源」，不以 0 偽裝。完整對照表見 `docs/agents/project.md`。

資料粒度、單位、來源角色、同期間衝突與新鮮度的嚴格定義見 `docs/specs/data-strategy-contract.md`；執行中的契約由 `app/data_strategy.py` 提供。網站的「資料健康」入口會依相同契約呈現資料集、來源、網站 API 與最近更新紀錄；原始狀態可由 `/api/data-health?code=2330` 查詢。
