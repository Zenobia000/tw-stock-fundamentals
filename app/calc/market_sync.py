"""現貨×期貨同步、法人×融資融券同步、大戶集中度、綜合訊號燈 — 契約 4.1～4.4 節。

全部函式吃已從資料庫取出的純數值/字串，不碰 DB／HTTP。資料來源見
`market_institutional_trading_daily`、`futures_oi_daily`、`market_margin_short_daily`、
`futures_large_trader_oi_daily`（見 app/db/schema.sql，最後一表為契約 3.1 節新增，
尚未落地）。

命名慣例：函式名對應契約小節。4.1／4.2 的四個函式簽名（spot_direction、
futures_direction、spot_futures_sync、margin_signal）已定案，不要改動；
4.3／4.4 見 `large_trader_agree`、`sync_signal`。

本檔刻意不含「留意...」語氣文字提示的產生函式：4.4 節只定義 GREEN/RED/YELLOW
三種客觀狀態，範例提示文字屬前端／文案層級的變化組合（依 spot/futures/margin
排列組合會爆出很多句子），不是契約要求的計算契約，硬做成小函式或字典只是把
文案搬進 calc 層，不會讓判斷邏輯更正確，屬於過度設計；之後若前端真的需要
共用文案，再依實際需求另開函式，不要在此預先猜測介面。
"""

SpotDirection = str  # 'BUY' | 'SELL'
FuturesDirection = str  # 'INCREASING' | 'DECREASING'
SyncStatus = str  # 'SYNCED' | 'DIVERGED'
MarginSignal = str  # '法人-散戶對做警訊' | '築底訊號' | '一般'

DEFAULT_MARGIN_THRESHOLD = 0.02


def spot_direction(net_amount: float) -> SpotDirection:
    """依 market_institutional_trading_daily 當日 net_amount 正負判斷方向。

    契約 4.1 節：net_amount >= 0 視為買超（BUY），否則賣超（SELL）。
    """
    return "BUY" if net_amount >= 0 else "SELL"


def futures_direction(today_net_oi: float, prev_net_oi: float) -> FuturesDirection:
    """依 futures_oi_daily net_oi 相較前一交易日的「變化方向」判斷，
    不是單日淨多空口數本身的正負（契約 4.1 節特別強調這個差異）。
    """
    return "INCREASING" if today_net_oi >= prev_net_oi else "DECREASING"


def spot_futures_sync(
    spot: SpotDirection, futures: FuturesDirection
) -> SyncStatus:
    """契約 4.1 節四象限：BUY+INCREASING 或 SELL+DECREASING → SYNCED；其餘 → DIVERGED。"""
    if spot == "BUY" and futures == "INCREASING":
        return "SYNCED"
    if spot == "SELL" and futures == "DECREASING":
        return "SYNCED"
    return "DIVERGED"


def margin_signal(
    spot: SpotDirection,
    margin_change_pct: float,
    threshold: float = DEFAULT_MARGIN_THRESHOLD,
) -> MarginSignal:
    """契約 4.2 節：法人現貨方向 × 融資餘額變動率的對照。

    threshold 為警訊閾值（預設 2%，非官方公認公式，可調）。
    - spot=BUY 且融資大增（變動率 >= threshold） → 法人-散戶對做警訊
    - spot=SELL 且融資大減（變動率 <= -threshold） → 築底訊號
    - 其餘 → 一般
    """
    if spot == "BUY" and margin_change_pct >= threshold:
        return "法人-散戶對做警訊"
    if spot == "SELL" and margin_change_pct <= -threshold:
        return "築底訊號"
    return "一般"


def large_trader_agree(
    top10_trader_net_oi: float | None, top10_specific_net_oi: float | None
) -> bool | None:
    """契約 4.3 節：十大交易人 net_oi 與十大特定人 net_oi 正負號是否一致。

    來源表 `futures_large_trader_oi_daily`（契約 3.1 節新表）尚未落地前，
    任一參數為 None 一律回傳 None（對應「資料未到位」情境），不得省略成
    True——由呼叫端／前端顯示「資料待補」。

    正負號比較沿用本檔 `spot_direction` 的 >=0 為非負慣例，0 與正值同號。
    """
    if top10_trader_net_oi is None or top10_specific_net_oi is None:
        return None
    return (top10_trader_net_oi >= 0) == (top10_specific_net_oi >= 0)


def sync_signal(spot_futures: SyncStatus, margin: MarginSignal) -> str:
    """契約 4.4 節：依 4.1（現貨×期貨同步）與 4.2（法人×融資融券）合成單一燈號。

    不做多空建議，只顯示客觀事實：
    - RED（明顯背離）：4.2 判定為「法人-散戶對做警訊」——優先於其餘判斷，
      即使 4.1 恰好是 SYNCED，也判 RED（契約 4.4 節原文只以 4.2 定義 RED，
      未加 4.1 條件）。
    - GREEN（同步）：4.1 為 SYNCED 且 4.2 非「對做警訊」。
    - YELLOW（部分背離）：其餘情況，含 4.1 為 DIVERGED 但未達 4.2 警訊閾值、
      或 4.3 大戶集中度資料不足（4.3 的 large_trader_agree 目前只是「其餘
      情況」的成因描述，不是額外參數，本函式故意不吃 large_trader_agree，
      避免為了尚未使用的維度硬加參數）。
    """
    if margin == "法人-散戶對做警訊":
        return "RED"
    if spot_futures == "SYNCED":
        return "GREEN"
    return "YELLOW"
