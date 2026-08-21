# tw-stock-fundamentals

台股基本面研究工作台。以 `★★★★★★ 波段股價預估試算_sunny.xlsx` 為功能基準，將 17 個 Sheet 重整為「決策總覽、營運基本面、財務品質與回報、蘭氏九宮格、籌碼與市場」五個區域。核心估值公式在 Python 後端運算，前端不複製公式；Google Sheets 的 `IMPORTHTML` 則由爬蟲與 SQLite 歷史資料取代。

## 快速開始

```bash
poetry install
poetry run uvicorn app.main:app --reload
poetry run pytest
```

## 專案結構

```text
app/
  scrapers/   每個資料源一個 scraper 模組
  calc/       估值鏈、弦值、九宮格等純計算邏輯
  db/         SQLite schema 與存取
  api/        FastAPI route
web/          前端（純 HTML/CSS/JS，彭博終端風格）
tests/        pytest（含對照 Excel 快照值的 golden-value 測試）
docs/agents/project.md       專案契約
docs/specs/workbook-analysis.md  原始 Excel 逐格公式分析
docs/specs/workbook-formula-contract.md  Sunny 估值公式契約
docs/specs/site-information-architecture.md  17 Sheet → 5 功能區對照
reference/    原始 Excel 檔案
```

## 資料來源

官方來源優先（TWSE 證券編碼查詢、公開資訊觀測站 MOPS 財報、期交所期貨籌碼），券商/入口網站補充非官方公開資料。介面會把尚未落地的來源標成「待補資料源」，不以 0 偽裝。完整對照表見 `docs/agents/project.md`。
