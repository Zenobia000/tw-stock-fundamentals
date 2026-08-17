-- tw-stock-fundamentals SQLite schema
-- Every fact table carries fetched_at (ISO8601 UTC) so scrapers can decide
-- whether cached data is fresh enough to skip a re-fetch.

CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT,           -- 上市 / 上櫃 / 興櫃
    industry TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_info (
    code TEXT PRIMARY KEY REFERENCES stocks(code),
    price REAL,
    market_cap_millions REAL,
    beta REAL,
    pe_ratio REAL,
    dividend_yield_pct REAL,
    book_value_per_share REAL,
    capital_billion_twd REAL,      -- 股本(億, 台幣)
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revenue_monthly (
    code TEXT NOT NULL REFERENCES stocks(code),
    month TEXT NOT NULL,           -- YYYY-MM
    revenue REAL,                  -- 千元
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, month)
);

CREATE TABLE IF NOT EXISTS margin_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,         -- e.g. 2026Q2
    revenue REAL,
    gross_profit REAL,
    gross_margin REAL,
    operating_income REAL,
    non_operating_income REAL,
    eps REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

-- 營業費用 sheet 實際可拿的是週轉天數（histock），不是選銷/管理/研發費用細目
-- （那要 MOPS 附註 XBRL 才有）。稅率改由 financial_health_quarterly 的
-- 所得稅費用/稅前淨利算，不在這裡重複存。
CREATE TABLE IF NOT EXISTS opex_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,          -- e.g. 2026Q1
    ar_days REAL,                   -- 應收帳款收現天數
    inventory_days REAL,            -- 存貨週轉天數
    operating_cycle_days REAL,      -- 營運週轉天數 = ar_days + inventory_days
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

CREATE TABLE IF NOT EXISTS eps_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    eps REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

-- 官方 TWSE OpenAPI 財報快照（app/scrapers/twse_financials.py）。
-- 該 API 沒有現金/應收帳款/存貨細項，也沒有現金流量表 dataset，
-- 對應數字改由 cashflow_quarterly（股息&現金流 scraper 來源）補。
CREATE TABLE IF NOT EXISTS financial_health_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    current_assets REAL,
    total_assets REAL,
    current_liabilities REAL,
    total_liabilities REAL,
    total_equity REAL,
    capital REAL,
    book_value_per_share REAL,
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    pretax_income REAL,
    net_income REAL,
    eps REAL,
    gross_margin_pct REAL,
    operating_margin_pct REAL,
    net_margin_pct REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

CREATE TABLE IF NOT EXISTS dividends (
    code TEXT NOT NULL REFERENCES stocks(code),
    fiscal_year INTEGER NOT NULL,       -- 所屬年度
    ex_dividend_date TEXT NOT NULL,     -- 除息日 MM/DD；同一年度可能多筆（半年配/季配）
    payout_year INTEGER,                -- 發放年度
    cash_dividend REAL,
    stock_dividend REAL,
    eps REAL,
    payout_ratio_pct REAL,
    yield_pct REAL,
    fill_dividend_days INTEGER,         -- 目前無穩定來源，先留空
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, fiscal_year, ex_dividend_date)
);

CREATE TABLE IF NOT EXISTS cashflow_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    operating REAL,
    investing REAL,
    financing REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

CREATE TABLE IF NOT EXISTS chips_daily (
    code TEXT NOT NULL REFERENCES stocks(code),
    date TEXT NOT NULL,
    foreign_holding_pct REAL,
    trust_holding_pct REAL,
    margin_balance REAL,
    short_balance REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS futures_oi_daily (
    date TEXT NOT NULL,
    institution TEXT NOT NULL,     -- 自營商 / 投信 / 外資
    contract TEXT NOT NULL,        -- e.g. TX 臺股期貨
    long_oi INTEGER,
    short_oi INTEGER,
    net_oi INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, institution, contract)
);

CREATE TABLE IF NOT EXISTS rankings_daily (
    date TEXT NOT NULL,
    category TEXT NOT NULL,        -- turnover_listed / turnover_otc / margin_ratio_listed / margin_ratio_otc
    rank INTEGER NOT NULL,
    code TEXT,
    name TEXT,
    value REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, category, rank)
);

CREATE TABLE IF NOT EXISTS market_cap_daily (
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    market_cap REAL,
    pct_of_market REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, code)
);

CREATE TABLE IF NOT EXISTS capital_reductions (
    name TEXT NOT NULL,
    code TEXT,
    resume_date TEXT,
    adjust_factor REAL,
    PRIMARY KEY (name)
);
