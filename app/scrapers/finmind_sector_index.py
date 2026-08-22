"""類股指數歷史 — FinMind 開源資料 API (api.finmindtrade.com)。

入口網站等級來源，不是官方（見 docs/agents/project.md 的優先序：TWSE 官方
優先，這裡僅用於初次歷史回補）。改用這個來源的原因：TWSE 官方 MI_INDEX
舊版 CGI 逐日回補約90次循序請求後會被 IP 層級限流（HTTP 428，無
Retry-After），FinMind 的 TaiwanStockPrice 資料集用同一個 data_id 一次
回傳「全部歷史」，不需要逐日打，且不需要 API key。

FINMIND_TO_TWSE_NAME 是實測驗證過的對照表（用同一天的收盤數字比對
TWSE MI_INDEX 官方回應逐一核對，不是憑名稱猜測）：FinMind 的
data_id 名稱跟 TWSE 官方指數中文名稱不是逐字對應（例如 FinMind
"Electronic" 對應官方「電子工業類指數」而不是字面的「電子類指數」），
用中文名稱去對兩邊資料一定會兜錯，所以用這份人工核對過的表。

每日增量還是用 app.scrapers.twse_sector_index（官方），這個模組只在
一次性回補時使用。
"""

import httpx

from app.scrapers.twse_sector_index import SectorIndex

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
FINMIND_DATASET = "TaiwanStockPrice"

# data_id -> TWSE 官方指數中文名稱，2026-08-21 收盤值逐一核對過。
FINMIND_TO_TWSE_NAME: dict[str, str] = {
    "TAIEX": "發行量加權股價指數",
    "TPEx": "櫃買指數",
    "Semiconductor": "半導體類指數",
    "Electronic": "電子工業類指數",
    "OtherElectronic": "其他電子類指數",
    "ElectronicPartsComponents": "電子零組件類指數",
    "ElectronicProductsDistribution": "電子通路類指數",
    "ComputerPeripheralEquipment": "電腦及週邊設備類指數",
    "CommunicationsInternet": "通信網路類指數",
    "Optoelectronic": "光電類指數",
    "InformationService": "資訊服務類指數",
    "FinancialInsurance": "金融保險類指數",
    "IronSteel": "鋼鐵類指數",
    "OilGasElectricity": "油電燃氣類指數",
    "Tourism": "觀光餐旅類指數",
    "PaperPulp": "造紙類指數",
    "Textiles": "紡織纖維類指數",
    "Rubber": "橡膠類指數",
    "ShippingTransportation": "航運類指數",
    "Plastics": "塑膠類指數",
    "GlassCeramic": "玻璃陶瓷類指數",
    "BiotechnologyMedicalCare": "生技醫療類指數",
    "ElectricMachinery": "電機機械類指數",
    "ElectricalCable": "電器電纜類指數",
    "ChemicalBiotechnologyMedicalCare": "化學生技醫療類指數",
    "Chemical": "化學類指數",
    "Cement": "水泥類指數",
    "BuildingMaterialConstruction": "建材營造類指數",
    "Automobile": "汽車類指數",
    "Food": "食品類指數",
    "TradingConsumersGoods": "貿易百貨類指數",
    "Other": "其他類指數",
}


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_finmind_records(payload: dict, index_name: str) -> list[SectorIndex]:
    if payload.get("status") != 200:
        raise ValueError(f"FinMind 回應非 200：{payload}")

    results: list[SectorIndex] = []
    for row in payload.get("data", []):
        close = _to_float(row.get("close"))
        spread = _to_float(row.get("spread"))
        prev_close = close - spread if close is not None and spread is not None else None
        change_pct = (
            round(spread / prev_close * 100, 2)
            if spread is not None and prev_close not in (None, 0)
            else None
        )
        direction = None
        if spread is not None and spread > 0:
            direction = "+"
        elif spread is not None and spread < 0:
            direction = "-"
        results.append(
            SectorIndex(
                date=row["date"],
                index_name=index_name,
                close_index=close,
                change_direction=direction,
                change_points=spread,
                change_pct=change_pct,
                remark="",
            )
        )
    return results


def fetch_sector_index_history(
    data_id: str,
    index_name: str,
    start_date: str,
    client: httpx.Client | None = None,
) -> list[SectorIndex]:
    """start_date: YYYY-MM-DD。回傳從 start_date 到最新的整段歷史，單次請求。"""
    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        resp = client.get(
            FINMIND_URL,
            params={
                "dataset": FINMIND_DATASET,
                "data_id": data_id,
                "start_date": start_date,
            },
        )
        resp.raise_for_status()
    finally:
        if owns_client:
            client.close()

    return _parse_finmind_records(resp.json(), index_name)
