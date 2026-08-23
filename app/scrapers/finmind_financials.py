"""FinMind 個股財報歷史回補。

MoneyLink 仍是詳細資產負債與正式現金流的主要來源；這個模組只負責補上
MoneyLink 近五季快照之外的歷史季度。FinMind 金額為元，正規化後資產負債
存百萬元、現金流存千元，與既有資料表口徑一致。
"""

from __future__ import annotations

import os

import httpx

from app.scrapers.moneylink_balance import DetailedBalanceQuarter
from app.scrapers.moneylink_cashflow import DetailedCashflowQuarter

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_TOKEN_ENV_VAR = "FINMIND_API_TOKEN"
BALANCE_DATASET = "TaiwanStockBalanceSheet"
CASHFLOW_DATASET = "TaiwanStockCashFlowsStatement"


def _auth_headers() -> dict[str, str]:
    token = os.environ.get(FINMIND_TOKEN_ENV_VAR)
    return {"Authorization": f"Bearer {token}"} if token else {}


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _quarter(date: str) -> str | None:
    try:
        year, month = int(date[:4]), int(date[5:7])
    except (TypeError, ValueError):
        return None
    if month not in {3, 6, 9, 12}:
        return None
    return f"{year}Q{month // 3}"


def _records_by_quarter(payload: dict, dataset: str) -> dict[str, dict[str, float]]:
    if payload.get("status") != 200:
        raise ValueError(f"FinMind {dataset} 回應非 200：{payload}")
    grouped: dict[str, dict[str, float]] = {}
    for row in payload.get("data", []):
        quarter = _quarter(str(row.get("date", "")))
        item_type = str(row.get("type", ""))
        value = _to_float(row.get("value"))
        if quarter is None or not item_type or item_type.endswith("_per") or value is None:
            continue
        grouped.setdefault(quarter, {})[item_type] = value
    return grouped


def _first(values: dict[str, float], *names: str) -> float | None:
    return next((values[name] for name in names if name in values), None)


def _sum(values: dict[str, float], *names: str) -> float | None:
    present = [values[name] for name in names if name in values]
    return sum(present) if present else None


def _parse_balance_records(payload: dict) -> list[DetailedBalanceQuarter]:
    grouped = _records_by_quarter(payload, BALANCE_DATASET)
    results: list[DetailedBalanceQuarter] = []
    for quarter in sorted(grouped, reverse=True):
        values = grouped[quarter]
        cash_and_securities = _sum(
            values,
            "CashAndCashEquivalents",
            "CurrentFinancialAssetsAtFairvalueThroughProfitOrLoss",
            "CurrentFinancialAssetsAtFairValueThroughProfitOrLoss",
            "CurrentFinancialAssetsAtFairvalueThroughOtherComprehensiveIncome",
            "CurrentFinancialAssetsAtFairValueThroughOtherComprehensiveIncome",
            "FinancialAssetsAtAmortizedCost",
            "CurrentFinancialAssetsAtAmortizedCost",
        )
        accounts_receivable = _sum(
            values,
            "AccountsReceivableNet",
            "AccountsReceivableDuefromRelatedPartiesNet",
            "AccountsReceivableFromRelatedPartiesNet",
        )
        long_term_investments = _sum(
            values,
            "NonCurrentFinancialAssetsAtFairvalueThroughProfitOrLoss",
            "NonCurrentFinancialAssetsAtFairValueThroughProfitOrLoss",
            "FinancialAssetsAtFairvalueThroughOtherComprehensiveIncomeNonCurrent",
            "FinancialAssetsAtFairValueThroughOtherComprehensiveIncomeNonCurrent",
            "FinancialAssetsAtAmortizedCostNonCurrent",
            "InvestmentAccountedForUsingEquityMethod",
        )
        accounts_payable = _sum(
            values,
            "AccountsPayable",
            "AccountsPayableToRelatedParties",
        )
        contract_liabilities = _sum(
            values,
            "ContractLiabilitiesCurrent",
            "ContractLiabilitiesNonCurrent",
            "ContractLiabilities",
        )
        interest_bearing_debt = _sum(
            values,
            "CurrentPortionOfLongtermLiabilities",
            "CurrentPortionOfLongTermLiabilities",
            "BondsPayable",
            "LongtermBorrowings",
            "LongTermBorrowings",
            "LeaseLiabilitiesNoncurrent",
            "LeaseLiabilitiesNonCurrent",
        )
        total_assets = _first(values, "TotalAssets")
        total_equity = _first(values, "Equity", "EquityAttributableToOwnersOfParent")
        capital = _first(values, "CapitalStock", "OrdinaryShare")
        if total_assets is None:
            continue

        def millions(value: float | None) -> float | None:
            return value / 1_000_000 if value is not None else None

        results.append(
            DetailedBalanceQuarter(
                quarter=quarter,
                cash_and_securities=millions(cash_and_securities),
                accounts_receivable=millions(accounts_receivable),
                inventory=millions(_first(values, "Inventories")),
                long_term_investments=millions(long_term_investments),
                property_plant_equipment=millions(
                    _first(values, "PropertyPlantAndEquipment")
                ),
                current_assets=millions(_first(values, "CurrentAssets")),
                total_assets=millions(total_assets),
                accounts_payable=millions(accounts_payable),
                contract_liabilities=millions(contract_liabilities),
                current_liabilities=millions(_first(values, "CurrentLiabilities")),
                interest_bearing_debt=millions(interest_bearing_debt),
                total_liabilities=millions(_first(values, "Liabilities")),
                total_equity=millions(total_equity),
                capital=millions(capital),
                book_value_per_share=(
                    total_equity * 10 / capital
                    if total_equity is not None and capital
                    else None
                ),
                roe_ratio=None,
            )
        )
    return results


_CASHFLOW_TYPES = {
    "operating": (
        "CashFlowsFromOperatingActivities",
        "NetCashInflowFromOperatingActivities",
    ),
    "investing": (
        "CashProvidedByInvestingActivities",
        "CashFlowsFromInvestingActivities",
    ),
    "financing": (
        "CashFlowsProvidedFromFinancingActivities",
        "CashFlowsFromFinancingActivities",
    ),
    "capex": (
        "PropertyAndPlantAndEquipment",
        "AcquisitionOfPropertyPlantAndEquipment",
    ),
}


def _parse_cashflow_records(payload: dict) -> list[DetailedCashflowQuarter]:
    grouped = _records_by_quarter(payload, CASHFLOW_DATASET)
    cumulative = {
        quarter: {
            field: _first(values, *aliases)
            for field, aliases in _CASHFLOW_TYPES.items()
        }
        for quarter, values in grouped.items()
    }
    results: list[DetailedCashflowQuarter] = []
    for quarter in sorted(cumulative):
        current = cumulative[quarter]
        q = int(quarter[-1])
        prior = cumulative.get(f"{quarter[:4]}Q{q - 1}") if q > 1 else None
        single: dict[str, float] = {}
        for field in _CASHFLOW_TYPES:
            value = current.get(field)
            if value is None:
                break
            if q > 1:
                prior_value = prior.get(field) if prior else None
                if prior_value is None:
                    break
                value -= prior_value
            single[field] = value
        if len(single) != len(_CASHFLOW_TYPES):
            continue
        operating = single["operating"] / 1000
        investing = single["investing"] / 1000
        financing = single["financing"] / 1000
        capital_expenditure = abs(single["capex"]) / 1000
        results.append(
            DetailedCashflowQuarter(
                quarter=quarter,
                operating=operating,
                investing=investing,
                financing=financing,
                capital_expenditure=capital_expenditure,
                free_cash_flow=operating - capital_expenditure,
                operating_plus_investing=operating + investing,
            )
        )
    return list(reversed(results))


def _fetch(
    dataset: str,
    stock_id: str,
    start_date: str,
    client: httpx.Client | None,
) -> dict:
    owns_client = client is None
    client = client or httpx.Client(timeout=25)
    try:
        response = client.get(
            FINMIND_URL,
            params={
                "dataset": dataset,
                "data_id": stock_id,
                "start_date": start_date,
            },
            headers=_auth_headers(),
        )
        response.raise_for_status()
        return response.json()
    finally:
        if owns_client:
            client.close()


def fetch_balance_history(
    stock_id: str, start_date: str, client: httpx.Client | None = None
) -> list[DetailedBalanceQuarter]:
    return _parse_balance_records(_fetch(BALANCE_DATASET, stock_id, start_date, client))


def fetch_cashflow_history(
    stock_id: str, start_date: str, client: httpx.Client | None = None
) -> list[DetailedCashflowQuarter]:
    return _parse_cashflow_records(_fetch(CASHFLOW_DATASET, stock_id, start_date, client))
