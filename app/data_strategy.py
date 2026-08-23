"""資料策略的單一真實來源。

每個資料集都必須在這裡明確定義粒度、正規化口徑、來源角色、更新頻率與
衝突裁決。擷取管線只接受登錄過的 dataset/source 組合，避免新來源直接寫入
正式表後，悄悄改變既有指標的意義。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

Scope = Literal["stock", "market"]
SourceTier = Literal["official", "publisher", "portal", "manual"]
Importance = Literal["critical", "supporting", "optional"]
MergeRule = Literal[
    "primary_same_period_wins",
    "preferred_source_then_freshest",
    "single_source",
]


@dataclass(frozen=True)
class DataSource:
    id: str
    label: str
    tier: SourceTier


@dataclass(frozen=True)
class DatasetPolicy:
    id: str
    label: str
    scope: Scope
    table: str
    as_of_column: str
    grain: str
    unit: str
    cadence: str
    freshness_sla_hours: int
    primary_source: str
    fallback_sources: tuple[str, ...] = ()
    backfill_sources: tuple[str, ...] = ()
    merge_rule: MergeRule = "single_source"
    scope_column: str | None = None
    scope_value: str | None = None
    source_column: str | None = None
    minimum_rows: int = 1
    allow_empty: bool = False
    importance: Importance = "supporting"

    @property
    def allowed_sources(self) -> tuple[str, ...]:
        return (
            self.primary_source,
            *self.fallback_sources,
            *self.backfill_sources,
        )

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["allowed_sources"] = list(self.allowed_sources)
        payload["source_roles"] = {
            "primary": self.primary_source,
            "fallback": list(self.fallback_sources),
            "historical_backfill_only": list(self.backfill_sources),
        }
        return payload


SOURCES = {
    source.id: source
    for source in (
        DataSource("twse-isin", "TWSE 證券編碼公告", "official"),
        DataSource("twse-openapi-financials", "TWSE OpenAPI 財報", "official"),
        DataSource("twse-stock-day", "TWSE STOCK_DAY", "official"),
        DataSource("twse-stock-day-all", "TWSE STOCK_DAY_ALL", "official"),
        DataSource("twse-capital-reduction", "TWSE 減資預告表", "official"),
        DataSource("twse-mi-index", "TWSE MI_INDEX", "official"),
        DataSource("twse-bwibbu-all", "TWSE 本益比殖利率統計", "official"),
        DataSource("taifex-futures", "TAIFEX 三大法人期貨", "official"),
        DataSource("taifex-market-cap", "TAIFEX 市值權重", "official"),
        DataSource("twse-bfi82u", "TWSE 三大法人買賣金額統計表", "official"),
        DataSource("twse-mi-margn", "TWSE 融資融券餘額", "official"),
        DataSource("tpex-3insti-summary", "TPEX 三大法人買賣金額統計表", "official"),
        DataSource("tpex-margin-balance", "TPEX 融資融券餘額(逐股加總)", "official"),
        DataSource("fubon-stock-info", "Fubon eBroker 個股資訊", "publisher"),
        DataSource("fubon-margin", "Fubon eBroker 季度損益", "publisher"),
        DataSource("fubon-eps", "Fubon eBroker EPS", "publisher"),
        DataSource("fubon-institutional", "Fubon eBroker 法人", "publisher"),
        DataSource("fubon-margin-short", "Fubon eBroker 融資券", "publisher"),
        DataSource("fubon-rankings", "Fubon eBroker 排行榜", "publisher"),
        DataSource("histock-revenue", "HiStock 營收", "portal"),
        DataSource("histock-turnover", "HiStock 週轉天數", "portal"),
        DataSource("histock-pe", "HiStock 本益比", "portal"),
        DataSource("histock-dividend", "HiStock 股利", "portal"),
        DataSource("histock-cashflow", "HiStock 現金流", "portal"),
        DataSource("histock-chips", "HiStock 籌碼", "portal"),
        DataSource("histock-brokers", "HiStock 券商分點", "portal"),
        DataSource("moneylink-income", "MoneyLink 單季損益", "portal"),
        DataSource("moneylink-balance", "MoneyLink 資產負債", "portal"),
        DataSource("moneylink-cashflow", "MoneyLink 現金流", "portal"),
        DataSource("cmoney-dividend", "CMoney 年度股利", "portal"),
        DataSource("cmoney-etf", "CMoney ETF 持股", "portal"),
        DataSource("finmind-sector-history", "FinMind 板塊歷史", "portal"),
        DataSource("finmind-stock-history", "FinMind 個股歷史", "portal"),
        DataSource("finmind-industry-chain", "FinMind 細產業標籤", "portal"),
        DataSource("finmind-market-value", "FinMind 市值快照", "portal"),
        DataSource("twse-material-news", "TWSE OpenAPI 重大訊息", "official"),
        DataSource("twse-insider-transfer", "TWSE OpenAPI 內部人持股轉讓", "official"),
        DataSource("twse-board-holdings", "TWSE OpenAPI 董監事持股", "official"),
        DataSource("twse-major-shareholders", "TWSE OpenAPI 大股東名單", "official"),
    )
}


def _stock(
    id: str,
    label: str,
    table: str,
    as_of: str,
    grain: str,
    unit: str,
    cadence: str,
    sla: int,
    primary: str,
    *,
    fallback: tuple[str, ...] = (),
    backfill: tuple[str, ...] = (),
    merge_rule: MergeRule = "single_source",
    source_column: str | None = None,
    minimum_rows: int = 1,
    allow_empty: bool = False,
    importance: Importance = "supporting",
) -> DatasetPolicy:
    return DatasetPolicy(
        id=id,
        label=label,
        scope="stock",
        table=table,
        as_of_column=as_of,
        grain=grain,
        unit=unit,
        cadence=cadence,
        freshness_sla_hours=sla,
        primary_source=primary,
        fallback_sources=fallback,
        backfill_sources=backfill,
        merge_rule=merge_rule,
        scope_column="code",
        source_column=source_column,
        minimum_rows=minimum_rows,
        allow_empty=allow_empty,
        importance=importance,
    )


def _market(
    id: str,
    label: str,
    table: str,
    as_of: str,
    grain: str,
    unit: str,
    cadence: str,
    sla: int,
    primary: str,
    *,
    fallback: tuple[str, ...] = (),
    backfill: tuple[str, ...] = (),
    merge_rule: MergeRule = "single_source",
    scope_column: str | None = None,
    scope_value: str | None = None,
    source_column: str | None = None,
    minimum_rows: int = 1,
    allow_empty: bool = False,
    importance: Importance = "supporting",
) -> DatasetPolicy:
    return DatasetPolicy(
        id=id,
        label=label,
        scope="market",
        table=table,
        as_of_column=as_of,
        grain=grain,
        unit=unit,
        cadence=cadence,
        freshness_sla_hours=sla,
        primary_source=primary,
        fallback_sources=fallback,
        backfill_sources=backfill,
        merge_rule=merge_rule,
        scope_column=scope_column,
        scope_value=scope_value,
        source_column=source_column,
        minimum_rows=minimum_rows,
        allow_empty=allow_empty,
        importance=importance,
    )


_POLICIES = (
    _stock(
        "stock_identity",
        "股票主檔",
        "stocks",
        "updated_at",
        "每股票",
        "文字",
        "按需／每週",
        168,
        "twse-isin",
        importance="critical",
    ),
    _stock(
        "stock_snapshot",
        "個股行情快照",
        "stock_info",
        "fetched_at",
        "每股票",
        "TWD／比率",
        "交易日",
        36,
        "fubon-stock-info",
        importance="critical",
    ),
    _stock(
        "revenue_monthly",
        "月營收",
        "revenue_monthly",
        "month",
        "股票×月",
        "千元 TWD",
        "每月",
        1080,
        "histock-revenue",
        minimum_rows=24,
        importance="critical",
    ),
    _stock(
        "profitability_quarterly",
        "季度獲利率",
        "margin_quarterly",
        "quarter",
        "股票×季",
        "千元 TWD／%",
        "每季",
        2400,
        "fubon-margin",
        minimum_rows=8,
        importance="critical",
    ),
    _stock(
        "income_statement_quarterly",
        "單季損益",
        "income_statement_quarterly",
        "quarter",
        "股票×季",
        "千元 TWD",
        "每季",
        2400,
        "moneylink-income",
        minimum_rows=8,
    ),
    _stock(
        "balance_sheet_quarterly",
        "資產負債",
        "balance_sheet_quarterly",
        "quarter",
        "股票×季",
        "千元 TWD",
        "每季",
        2400,
        "moneylink-balance",
        backfill=("finmind-stock-history",),
        merge_rule="primary_same_period_wins",
        minimum_rows=8,
    ),
    _stock(
        "operating_efficiency_quarterly",
        "營運效率",
        "opex_quarterly",
        "quarter",
        "股票×季",
        "天",
        "每季",
        2400,
        "histock-turnover",
        fallback=("moneylink-balance",),
        merge_rule="primary_same_period_wins",
        minimum_rows=8,
    ),
    _stock(
        "eps_quarterly",
        "季度 EPS",
        "eps_quarterly",
        "quarter",
        "股票×季",
        "TWD／股",
        "每季",
        2400,
        "fubon-eps",
        minimum_rows=8,
        importance="critical",
    ),
    _stock(
        "pe_monthly",
        "月本益比",
        "pe_monthly",
        "month",
        "股票×月",
        "倍",
        "每月",
        1080,
        "histock-pe",
        minimum_rows=60,
        importance="critical",
    ),
    _stock(
        "financial_health_quarterly",
        "財報健檢",
        "financial_health_quarterly",
        "quarter",
        "股票×季",
        "千元 TWD／%",
        "每季",
        2400,
        "twse-openapi-financials",
        minimum_rows=8,
    ),
    _stock(
        "dividend_events",
        "股利事件",
        "dividends",
        "fiscal_year",
        "股票×年度×事件",
        "TWD／股／%",
        "每月",
        1080,
        "histock-dividend",
        allow_empty=True,
        importance="optional",
    ),
    _stock(
        "dividend_annual",
        "年度股利率",
        "dividend_annual",
        "fiscal_year",
        "股票×年度",
        "TWD／股／比例",
        "每月",
        1080,
        "cmoney-dividend",
        allow_empty=True,
        importance="optional",
    ),
    _stock(
        "cashflow_quarterly",
        "季度現金流",
        "cashflow_quarterly",
        "quarter",
        "股票×季",
        "千元 TWD",
        "每季",
        2400,
        "moneylink-cashflow",
        fallback=("histock-cashflow",),
        backfill=("finmind-stock-history",),
        merge_rule="preferred_source_then_freshest",
        source_column="source",
        minimum_rows=8,
    ),
    _stock(
        "chips_daily",
        "持股籌碼",
        "chips_daily",
        "date",
        "股票×日",
        "%",
        "交易日",
        36,
        "histock-chips",
        minimum_rows=20,
    ),
    _stock(
        "institutional_trading_daily",
        "法人買賣超",
        "institutional_trading_daily",
        "date",
        "股票×日×法人",
        "股",
        "交易日",
        36,
        "fubon-institutional",
        minimum_rows=20,
    ),
    _stock(
        "margin_short_daily",
        "融資融券",
        "margin_short_daily",
        "date",
        "股票×日",
        "張／比例",
        "交易日",
        36,
        "fubon-margin-short",
        minimum_rows=20,
    ),
    _stock(
        "etf_holdings",
        "ETF 持股",
        "etf_holdings",
        "as_of_date",
        "股票×日×ETF",
        "%",
        "交易日",
        72,
        "cmoney-etf",
        allow_empty=True,
        importance="optional",
    ),
    _stock(
        "broker_branches_daily",
        "券商分點",
        "broker_branches_daily",
        "date",
        "股票×日×分點",
        "股／TWD",
        "交易日",
        36,
        "histock-brokers",
        minimum_rows=20,
        importance="optional",
    ),
    _stock(
        "stock_prices_quarterly",
        "季底股價",
        "stock_prices_quarterly",
        "price_date",
        "股票×季",
        "TWD",
        "每季",
        2400,
        "twse-stock-day",
        minimum_rows=8,
    ),
    _stock(
        "stock_prices_daily",
        "日股價",
        "stock_prices_daily",
        "date",
        "股票×日",
        "TWD／股",
        "交易日",
        36,
        "twse-stock-day",
        backfill=("finmind-stock-history",),
        merge_rule="primary_same_period_wins",
        source_column="source",
        minimum_rows=121,
        importance="critical",
    ),
    _market(
        "stock_industry_chain",
        "股票細產業標籤",
        "stock_industry_chain",
        "tagged_at",
        "股票×產業×次產業",
        "分類標籤",
        "每週",
        336,
        "finmind-industry-chain",
        minimum_rows=1000,
    ),
    _market(
        "stock_universe_top100",
        "前百大股票池",
        "stock_universe_top100",
        "as_of_date",
        "月×股票",
        "市值／名次",
        "每月",
        1080,
        "taifex-market-cap",
        fallback=("finmind-market-value",),
        merge_rule="primary_same_period_wins",
        source_column="source",
        minimum_rows=100,
    ),
    _market(
        "capital_reductions",
        "減資預告",
        "capital_reductions",
        "fetched_at",
        "公司×事件",
        "比例",
        "交易日",
        36,
        "twse-capital-reduction",
        allow_empty=True,
        importance="optional",
    ),
    _market(
        "material_news",
        "重大訊息",
        "stock_events",
        "event_date",
        "公司×事件",
        "文字",
        "每日",
        36,
        "twse-material-news",
        scope_column="event_type",
        scope_value="material_news",
        source_column="source",
        allow_empty=True,
        importance="optional",
    ),
    _market(
        "insider_transfer",
        "內部人持股轉讓",
        "stock_events",
        "event_date",
        "公司×事件",
        "文字",
        "每日",
        36,
        "twse-insider-transfer",
        scope_column="event_type",
        scope_value="insider_transfer",
        source_column="source",
        allow_empty=True,
        importance="optional",
    ),
    _market(
        "board_holdings_monthly",
        "董監事持股與質押",
        "board_holdings_monthly",
        "fetched_at",
        "公司×人",
        "股數/比例",
        "月頻",
        24 * 31,
        "twse-board-holdings",
        allow_empty=True,
        importance="optional",
    ),
    _market(
        "major_shareholders",
        "大股東名單",
        "major_shareholders",
        "as_of_date",
        "公司×大股東",
        "文字",
        "月頻",
        24 * 31,
        "twse-major-shareholders",
        allow_empty=True,
        importance="optional",
    ),
    _market(
        "futures_oi_daily",
        "期貨法人未平倉",
        "futures_oi_daily",
        "date",
        "日×法人×契約",
        "口",
        "交易日",
        36,
        "taifex-futures",
        minimum_rows=3,
    ),
    _market(
        "market_institutional_trading_twse",
        "大盤三大法人買賣超(上市)",
        "market_institutional_trading_daily",
        "date",
        "日×法人",
        "TWD",
        "交易日",
        36,
        "twse-bfi82u",
        scope_column="market",
        scope_value="TWSE",
        minimum_rows=5,
    ),
    _market(
        "market_institutional_trading_tpex",
        "大盤三大法人買賣超(上櫃)",
        "market_institutional_trading_daily",
        "date",
        "日×法人",
        "TWD",
        "交易日",
        36,
        "tpex-3insti-summary",
        scope_column="market",
        scope_value="TPEX",
        minimum_rows=5,
    ),
    _market(
        "market_margin_short_twse",
        "大盤融資融券增減(上市)",
        "market_margin_short_daily",
        "date",
        "日×市場",
        "張",
        "交易日",
        36,
        "twse-mi-margn",
        scope_column="market",
        scope_value="TWSE",
        minimum_rows=1,
    ),
    _market(
        "market_margin_short_tpex",
        "大盤融資融券增減(上櫃)",
        "market_margin_short_daily",
        "date",
        "日×市場",
        "張",
        "交易日",
        36,
        "tpex-margin-balance",
        scope_column="market",
        scope_value="TPEX",
        minimum_rows=1,
    ),
    _market(
        "ranking_turnover_listed",
        "上市成交值排行",
        "rankings_daily",
        "date",
        "日×排行",
        "TWD",
        "交易日",
        36,
        "twse-stock-day-all",
        fallback=("fubon-rankings",),
        merge_rule="primary_same_period_wins",
        scope_column="category",
        scope_value="turnover_listed",
        source_column="source",
        minimum_rows=50,
    ),
    _market(
        "ranking_turnover_otc",
        "上櫃成交值排行",
        "rankings_daily",
        "date",
        "日×排行",
        "TWD",
        "交易日",
        36,
        "fubon-rankings",
        scope_column="category",
        scope_value="turnover_otc",
        source_column="source",
        minimum_rows=50,
    ),
    _market(
        "ranking_margin_ratio_listed",
        "上市券資比排行",
        "rankings_daily",
        "date",
        "日×排行",
        "%",
        "交易日",
        36,
        "fubon-rankings",
        scope_column="category",
        scope_value="margin_ratio_listed",
        source_column="source",
        minimum_rows=50,
    ),
    _market(
        "ranking_margin_ratio_otc",
        "上櫃券資比排行",
        "rankings_daily",
        "date",
        "日×排行",
        "%",
        "交易日",
        36,
        "fubon-rankings",
        scope_column="category",
        scope_value="margin_ratio_otc",
        source_column="source",
        minimum_rows=50,
    ),
    _market(
        "ranking_turnover_rate_listed",
        "上市週轉率排行",
        "rankings_daily",
        "date",
        "日×排行",
        "%",
        "交易日",
        36,
        "fubon-rankings",
        scope_column="category",
        scope_value="turnover_rate_listed",
        source_column="source",
        minimum_rows=50,
    ),
    _market(
        "ranking_turnover_rate_otc",
        "上櫃週轉率排行",
        "rankings_daily",
        "date",
        "日×排行",
        "%",
        "交易日",
        36,
        "fubon-rankings",
        scope_column="category",
        scope_value="turnover_rate_otc",
        source_column="source",
        minimum_rows=50,
    ),
    _market(
        "market_cap_daily",
        "市值排行",
        "market_cap_daily",
        "date",
        "日×股票",
        "市值／%",
        "每月",
        1080,
        "taifex-market-cap",
        minimum_rows=100,
    ),
    _market(
        "sector_index_daily",
        "板塊指數",
        "sector_index_daily",
        "date",
        "日×指數",
        "指數點／%",
        "交易日",
        36,
        "twse-mi-index",
        backfill=("finmind-sector-history",),
        merge_rule="primary_same_period_wins",
        source_column="source",
        minimum_rows=3600,
    ),
    _market(
        "stock_valuation_daily",
        "個股本益比殖利率統計",
        "stock_valuation_daily",
        "date",
        "日×股票",
        "倍／%",
        "交易日",
        36,
        "twse-bwibbu-all",
        minimum_rows=500,
    ),
)

DATASET_POLICIES = {policy.id: policy for policy in _POLICIES}
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def validate_registry() -> None:
    if len(DATASET_POLICIES) != len(_POLICIES):
        raise ValueError("資料策略存在重複 dataset id")
    for policy in _POLICIES:
        if (
            not policy.grain
            or not policy.unit
            or policy.freshness_sla_hours <= 0
            or policy.minimum_rows < 0
            or policy.importance not in {"critical", "supporting", "optional"}
        ):
            raise ValueError(f"{policy.id} 的粒度、單位或 SLA 未完整定義")
        identifiers = (
            policy.table,
            policy.as_of_column,
            policy.scope_column,
            policy.source_column,
        )
        if any(value and not _IDENTIFIER.fullmatch(value) for value in identifiers):
            raise ValueError(f"{policy.id} 使用不合法的資料庫識別字")
        if len(set(policy.allowed_sources)) != len(policy.allowed_sources):
            raise ValueError(f"{policy.id} 的來源角色重複")
        unknown = set(policy.allowed_sources) - SOURCES.keys()
        if unknown:
            raise ValueError(f"{policy.id} 使用未登錄來源：{sorted(unknown)}")
        if (policy.scope_column is None) != (
            policy.scope_value is None
        ) and policy.scope == "market":
            raise ValueError(f"{policy.id} 的市場篩選欄位和值必須同時設定")


def get_policy(dataset_id: str) -> DatasetPolicy:
    try:
        return DATASET_POLICIES[dataset_id]
    except KeyError as exc:
        raise ValueError(f"未登錄的資料集：{dataset_id}") from exc


def assert_source_allowed(dataset_id: str, source: str) -> DatasetPolicy:
    policy = get_policy(dataset_id)
    if source not in policy.allowed_sources:
        raise ValueError(f"資料集 {dataset_id} 不允許來源 {source}")
    return policy


def strategy_payload() -> dict:
    return {
        "principles": [
            "相同期間官方來源優先",
            "補充來源只補官方尚未發布的期間",
            "歷史回補來源不得覆蓋官方資料",
            "缺值保留為空值，不以零代替",
            "每次擷取保留執行結果與資料水位",
        ],
        "sources": [asdict(source) for source in SOURCES.values()],
        "datasets": [policy.as_dict() for policy in _POLICIES],
    }


validate_registry()
