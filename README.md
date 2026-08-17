# tw-stock-fundamentals

台股波段股價預估網站。把「蘭氏」基本面選股模型從 Excel 轉成可自動爬蟲更新的網站：輸入股票代碼 → 抓回基本面／籌碼面資料 → 估值鏈算出預估 EPS 與目標價 → 彭博終端風格的九宮格圖表儀表板。

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
reference/    原始 Excel 檔案
```

## 資料來源

官方來源優先（TWSE 證券編碼查詢、公開資訊觀測站 MOPS 財報、期交所期貨籌碼），券商/入口網站（Fubon eBroker DJ、CMoney、histock、money-link）補充非官方公開資料。完整對照表見 `docs/agents/project.md`。
