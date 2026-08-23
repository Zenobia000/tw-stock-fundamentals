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
    source TEXT NOT NULL DEFAULT 'unknown',
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
    open_index REAL,               -- 只有「發行量加權股價指數」有值（TWSE MI_5MINS_HIST 官方來源，
    high_index REAL,                -- 逐月回傳；見 app.scrapers.twse_index_ohlc）；其餘板塊指數
    low_index REAL,                 -- 官方沒有逐日開高低資料，維持 NULL，不得回推假造
    source TEXT NOT NULL,          -- 'twse-mi-index'
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, index_name)
);

-- 慢變動維度表（FinMind TaiwanStockIndustryChain），不是逐日時序，一次性/週期回補。
CREATE TABLE IF NOT EXISTS stock_industry_chain (
    stock_id TEXT NOT NULL,
    industry TEXT NOT NULL,
    sub_industry TEXT NOT NULL,    -- 一檔股票可能有多個 (industry, sub_industry) 標籤
    tagged_at TEXT,                -- FinMind 原始 date 欄位：這筆標籤最後確認日
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (stock_id, industry, sub_industry)
);

-- 台灣前100大成分股快照（依市值），細產業動能排名的股票池；覆蓋式更新，不逐日累積。
CREATE TABLE IF NOT EXISTS stock_universe_top100 (
    as_of_date TEXT NOT NULL,
    rank INTEGER NOT NULL,
    stock_id TEXT NOT NULL,
    stock_name TEXT,
    market_value REAL,
    source TEXT NOT NULL DEFAULT 'unknown',
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (as_of_date, stock_id)
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

CREATE TABLE IF NOT EXISTS stock_valuation_daily (
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    pe_ratio REAL,
    dividend_yield_pct REAL,
    pb_ratio REAL,
    source TEXT NOT NULL DEFAULT 'twse-bwibbu-all',
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
    fetched_at TEXT,
    PRIMARY KEY (name)
);

CREATE TABLE IF NOT EXISTS board_holdings_monthly (
    code TEXT NOT NULL REFERENCES stocks(code),
    report_month TEXT NOT NULL,
    title TEXT NOT NULL,
    person_name TEXT NOT NULL,
    shares_held INTEGER,
    pledged_shares INTEGER,
    pledged_ratio REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, report_month, title, person_name)
);

CREATE TABLE IF NOT EXISTS major_shareholders (
    code TEXT NOT NULL REFERENCES stocks(code),
    as_of_date TEXT NOT NULL,
    shareholder_name TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (code, as_of_date, shareholder_name)
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

-- 大盤層級三大法人買賣超（TWSE/TPEX 官方每日合計，非個股加總）。
CREATE TABLE IF NOT EXISTS market_institutional_trading_daily (
    date TEXT NOT NULL,
    market TEXT NOT NULL,          -- 'TWSE' / 'TPEX'
    institution TEXT NOT NULL,     -- 自營商(自行買賣) / 自營商(避險) / 投信 / 外資及陸資 / 外資自營商 / 合計
    buy_amount REAL,
    sell_amount REAL,
    net_amount REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, market, institution)
);

-- 大盤層級融資融券餘額（TWSE 為官方合計端點；TPEX 無官方合計端點，
-- 由官方逐股資料在 scraper 內加總得出，仍屬官方數字非券商入口網站）。
CREATE TABLE IF NOT EXISTS market_margin_short_daily (
    date TEXT NOT NULL,
    market TEXT NOT NULL,          -- 'TWSE' / 'TPEX'
    margin_buy REAL,
    margin_sell REAL,
    margin_redemption REAL,
    margin_balance REAL,
    short_buy REAL,
    short_sell REAL,
    short_redemption REAL,
    short_balance REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, market)
);

-- 期貨大戶集中度（TAIFEX 大額交易人未沖銷部位結構表，官方）。trader_group='十大交易人'
-- 是全體，'十大特定法人' 是其子集；contract 用官方原始契約名稱（含組成公式，例如
-- 「臺股期貨(TX+MTX/4+TMF/20)」），不是簡稱「臺股期貨」。
CREATE TABLE IF NOT EXISTS futures_large_trader_oi_daily (
    date TEXT NOT NULL,
    contract TEXT NOT NULL,
    trader_group TEXT NOT NULL,
    long_oi INTEGER,
    short_oi INTEGER,
    net_oi INTEGER,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, contract, trader_group)
);

-- 台指期貨每日 OHLC（TAIFEX 期貨每日交易行情下載，官方）。session='day'/'night'；
-- 夜盤 date 是 TAIFEX 官方歸屬的次一營業日，不是自然日隔天。
CREATE TABLE IF NOT EXISTS futures_price_daily (
    date TEXT NOT NULL,
    contract TEXT NOT NULL,
    session TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    settlement_price REAL,
    change_pct REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, contract, session)
);

-- 全市場個股每日收盤快照（TWSE MI_INDEX type=ALLBUT0999，官方，約1377檔含股票與ETF，
-- 不篩選）。change_pct 是本模組自算（官方原始 table 沒有這欄），見
-- app.scrapers.twse_market_snapshot 模組說明。market 目前固定 'TWSE'；TPEX 版本另案處理。
CREATE TABLE IF NOT EXISTS market_stock_snapshot_daily (
    date TEXT NOT NULL,
    market TEXT NOT NULL,          -- 'TWSE' / 'TPEX'
    code TEXT NOT NULL,
    name TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    change_pct REAL,
    volume REAL,
    transaction_count REAL,
    turnover REAL,
    pe_ratio REAL,
    last_bid_volume REAL,          -- 最後揭示買量；僅 TWSE 有，TPEX 固定 NULL
    last_ask_volume REAL,          -- 最後揭示賣量；僅 TWSE 有，TPEX 固定 NULL
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (date, market, code)
);

-- 產業資金流向（衍生計算，依 institutional_trading_daily × stock_industry_chain 分組加總，
-- 不是原始擷取表，沒有官方 source）。注意 net_amount 目前實際單位是「張」不是新台幣金額——
-- institutional_trading_daily 唯一資料源（Fubon）本身就是張數，不是金額；turnover_amount
-- 目前資料庫沒有個股成交金額欄位可算，固定 NULL，不得用 volume×close 湊近似值。
-- 詳見 app/calc/industry_capital_flow.py 模組說明。
CREATE TABLE IF NOT EXISTS industry_capital_flow_daily (
    date TEXT NOT NULL,
    industry TEXT NOT NULL,
    net_amount REAL,
    turnover_amount REAL,
    member_count INTEGER,
    formula_version TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (date, industry)
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

-- 資料策略控制面：每次來源擷取都保留結果，watermark 只指向依來源優先序
-- 裁決後的 canonical 資料。兩者不取代 domain tables 的 fetched_at/source。
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed')),
    data_as_of TEXT,
    row_count INTEGER,
    error TEXT,
    duration_ms REAL,
    http_status INTEGER,
    error_type TEXT
);

CREATE TABLE IF NOT EXISTS dataset_watermarks (
    dataset_id TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    canonical_source TEXT NOT NULL,
    data_as_of TEXT,
    last_success_at TEXT NOT NULL,
    row_count INTEGER,
    PRIMARY KEY (dataset_id, scope_key)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_lookup
    ON ingestion_runs(dataset_id, scope_key, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_rankings_category_date
    ON rankings_daily(category, date DESC, rank);
CREATE INDEX IF NOT EXISTS idx_futures_date
    ON futures_oi_daily(date DESC, institution, contract);
CREATE INDEX IF NOT EXISTS idx_stock_events_code_date
    ON stock_events(code, event_date DESC);
CREATE INDEX IF NOT EXISTS idx_etf_holdings_code_date
    ON etf_holdings(code, as_of_date DESC, holding_ratio DESC);
CREATE INDEX IF NOT EXISTS idx_sector_index_name_date
    ON sector_index_daily(index_name, date DESC);
CREATE INDEX IF NOT EXISTS idx_board_holdings_code_month
    ON board_holdings_monthly(code, report_month DESC);
CREATE INDEX IF NOT EXISTS idx_major_shareholders_code_date
    ON major_shareholders(code, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_market_institutional_trading_date
    ON market_institutional_trading_daily(date DESC, market, institution);
CREATE INDEX IF NOT EXISTS idx_market_margin_short_date
    ON market_margin_short_daily(date DESC, market);
CREATE INDEX IF NOT EXISTS idx_market_stock_snapshot_date
    ON market_stock_snapshot_daily(date DESC, market, code);
CREATE INDEX IF NOT EXISTS idx_futures_large_trader_date
    ON futures_large_trader_oi_daily(date DESC, contract, trader_group);
CREATE INDEX IF NOT EXISTS idx_futures_price_date
    ON futures_price_daily(date DESC, contract, session);
CREATE INDEX IF NOT EXISTS idx_industry_capital_flow_date
    ON industry_capital_flow_daily(date DESC, net_amount DESC);
