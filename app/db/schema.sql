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

CREATE TABLE IF NOT EXISTS opex_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    selling_expense REAL,
    admin_expense REAL,
    rd_expense REAL,
    tax_rate REAL,
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

CREATE TABLE IF NOT EXISTS financial_health_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    cash REAL,
    accounts_receivable REAL,
    inventory REAL,
    total_assets REAL,
    current_liabilities REAL,
    total_liabilities REAL,
    total_equity REAL,
    operating_cash_flow REAL,
    capex REAL,
    financing_cash_flow REAL,
    investing_cash_flow REAL,
    shares_outstanding_millions REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

CREATE TABLE IF NOT EXISTS dividends (
    code TEXT NOT NULL REFERENCES stocks(code),
    year TEXT NOT NULL,
    cash_dividend REAL,
    stock_dividend REAL,
    yield_pct REAL,
    fill_dividend_days INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, year)
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
