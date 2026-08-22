"""財報健檢比率計算 — 對應原工作表『財報健檢』B27:B37。

純函式，吃基本數字（不綁定特定 scraper 的 dataclass），方便獨立測試與
未來替換資料源。
"""

from dataclasses import dataclass


@dataclass
class FinancialHealthRatios:
    debt_ratio: float  # 負債比率 = 負債總計 / 資產總計
    current_ratio: float | None  # 流動比率 = 流動資產 / 流動負債
    book_value_per_share: float | None
    price_to_book: float | None  # 股價淨值比 = 現價 / 每股淨值


def compute_financial_health_ratios(
    total_assets: float,
    total_liabilities: float,
    current_assets: float,
    current_liabilities: float,
    book_value_per_share: float | None,
    price: float | None = None,
) -> FinancialHealthRatios:
    debt_ratio = total_liabilities / total_assets if total_assets else 0.0
    current_ratio = (
        current_assets / current_liabilities if current_liabilities else None
    )
    price_to_book = (
        price / book_value_per_share if price and book_value_per_share else None
    )
    return FinancialHealthRatios(
        debt_ratio=debt_ratio,
        current_ratio=current_ratio,
        book_value_per_share=book_value_per_share,
        price_to_book=price_to_book,
    )
