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
    quarter TEXT NOT NULL,         -- 原始格式如 "115.2Q"（民國年.季別，未轉西元）
    revenue REAL,
    cost_of_goods_sold REAL,
    gross_profit REAL,
    gross_margin_pct REAL,
    operating_income REAL,
    operating_margin_pct REAL,
    non_operating_income REAL,
    pretax_income REAL,
    net_income REAL,
    eps REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

-- 舊的營運效率來源只有週轉天數（histock），不是推銷/管理/研發費用細目
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

-- 季底收盤價（TWSE STOCK_DAY 官方），給每股盈餘(EPS)頁的
-- 本益比高中低分位→目標價矩陣用。只存季底那一天，不存整月。
CREATE TABLE IF NOT EXISTS stock_prices_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,       -- e.g. 2026Q2
    close_price REAL,
    price_date TEXT,             -- 實際交易日（季底可能是假日，會往前找）
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
    capital_expenditure REAL,
    free_cash_flow REAL,
    operating_plus_investing REAL,
    source TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

-- histock 大戶籌碼頁沒有投信持股/融資融券餘額，先留給之後的 Fubon zcl/zcn 頁補；
-- 現況欄位對應該頁實際的四個數字。
CREATE TABLE IF NOT EXISTS chips_daily (
    code TEXT NOT NULL REFERENCES stocks(code),
    date TEXT NOT NULL,
    concentration_pct REAL,      -- 籌碼集中度
    foreign_holding_pct REAL,    -- 外資籌碼
    big_holder_pct REAL,         -- 大戶籌碼
    insider_holding_pct REAL,    -- 董監持股
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS futures_oi_daily (
    date TEXT NOT NULL,
    institution TEXT NOT NULL,     -- 自營商 / 投信 / 外資
    contract TEXT NOT NULL,        -- e.g. 臺股期貨
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

CREATE TABLE IF NOT EXISTS sector_index_daily (
    date TEXT NOT NULL,
    index_name TEXT NOT NULL,      -- TWSE 官方指數中文名稱，例如「半導體類指數」「發行量加權股價指數」
    close_index REAL,
    change_direction TEXT,         -- '+' / '-' / NULL
    change_points REAL,
    change_pct REAL,
    remark TEXT,
    source TEXT NOT NULL,          -- 'twse-mi-index'
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, index_name)
);

CREATE TABLE IF NOT EXISTS market_cap_daily (
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    rank INTEGER,
    name TEXT,
    market_cap REAL,
    pct_of_market REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, code)
);

CREATE TABLE IF NOT EXISTS capital_reductions (
    name TEXT NOT NULL,
    code TEXT,
    stop_date TEXT,
    resume_date TEXT,
    exchange_ratio REAL,
    adjust_factor REAL,
    reason TEXT,
    source TEXT,
    PRIMARY KEY (name)
);

-- Website v2 domain tables. These normalized tables cover the research capabilities
-- that cannot be represented by the earlier compact schema. Existing tables stay
-- in place during migration so ingestion remains backwards compatible.
CREATE TABLE IF NOT EXISTS income_statement_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    revenue REAL,
    gross_profit REAL,
    selling_expense REAL,
    administrative_expense REAL,
    research_expense REAL,
    operating_expense REAL,
    operating_income REAL,
    non_operating_income REAL,
    pretax_income REAL,
    net_income REAL,                 -- 本期淨利（含非控制權益）
    parent_net_income REAL,          -- 母公司業主淨利
    noncontrolling_income REAL,
    income_tax_expense REAL,
    eps REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

CREATE TABLE IF NOT EXISTS balance_sheet_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    cash_and_securities REAL,
    accounts_receivable REAL,
    inventory REAL,
    long_term_investments REAL,
    property_plant_equipment REAL,
    current_assets REAL,
    total_assets REAL,
    accounts_payable REAL,
    contract_liabilities REAL,
    current_liabilities REAL,
    interest_bearing_debt REAL,
    total_liabilities REAL,
    total_equity REAL,
    capital REAL,
    book_value_per_share REAL,
    roe_ratio REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

CREATE TABLE IF NOT EXISTS operating_efficiency_quarterly (
    code TEXT NOT NULL REFERENCES stocks(code),
    quarter TEXT NOT NULL,
    ar_days REAL,
    inventory_days REAL,
    payable_days REAL,
    operating_cycle_days REAL,
    inventory_turnover REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, quarter)
);

CREATE TABLE IF NOT EXISTS pe_monthly (
    code TEXT NOT NULL REFERENCES stocks(code),
    month TEXT NOT NULL,
    pe_ratio REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, month)
);

CREATE TABLE IF NOT EXISTS stock_prices_daily (
    code TEXT NOT NULL REFERENCES stocks(code),
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS stock_events (
    code TEXT NOT NULL REFERENCES stocks(code),
    event_date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, event_date, event_type, title)
);

CREATE TABLE IF NOT EXISTS etf_holdings (
    code TEXT NOT NULL REFERENCES stocks(code),
    as_of_date TEXT NOT NULL,
    etf_code TEXT NOT NULL,
    etf_name TEXT,
    holding_ratio REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, as_of_date, etf_code)
);

CREATE TABLE IF NOT EXISTS dividend_annual (
    code TEXT NOT NULL REFERENCES stocks(code),
    fiscal_year INTEGER NOT NULL,
    cash_dividend REAL,
    payout_ratio REAL,              -- fraction；33.2% 存 0.332
    yield_ratio REAL,               -- fraction
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, fiscal_year)
);

CREATE TABLE IF NOT EXISTS institutional_trading_daily (
    code TEXT NOT NULL REFERENCES stocks(code),
    date TEXT NOT NULL,
    institution TEXT NOT NULL,
    buy REAL,
    sell REAL,
    net REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, date, institution)
);

CREATE TABLE IF NOT EXISTS margin_short_daily (
    code TEXT NOT NULL REFERENCES stocks(code),
    date TEXT NOT NULL,
    margin_balance REAL,
    short_balance REAL,
    margin_utilization_ratio REAL,
    short_margin_ratio REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, date)
);

CREATE TABLE IF NOT EXISTS broker_branches_daily (
    code TEXT NOT NULL REFERENCES stocks(code),
    date TEXT NOT NULL,
    branch TEXT NOT NULL,
    buy REAL,
    sell REAL,
    net REAL,
    average_price REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, date, branch)
);
