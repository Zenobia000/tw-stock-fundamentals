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
