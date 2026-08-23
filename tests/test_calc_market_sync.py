from app.calc.market_sync import (
    futures_direction,
    large_trader_agree,
    margin_signal,
    spot_direction,
    spot_futures_sync,
    sync_signal,
)

# ---------------------------------------------------------------------------
# spot_direction — market_institutional_trading_daily.net_amount 正負
# ---------------------------------------------------------------------------


def test_spot_direction_positive_net_amount_is_buy():
    assert spot_direction(1_200_000_000.0) == "BUY"


def test_spot_direction_negative_net_amount_is_sell():
    assert spot_direction(-850_000_000.0) == "SELL"


def test_spot_direction_zero_net_amount_is_buy():
    # 契約未明講 0 該歸哪邊；採 >=0 視為 BUY 的邊界慣例。
    assert spot_direction(0.0) == "BUY"


# ---------------------------------------------------------------------------
# futures_direction — futures_oi_daily.net_oi 相較前一日的「變化方向」
# 契約 4.1 節重點：看的是變化方向，不是單日 net_oi 本身的正負。
# ---------------------------------------------------------------------------


def test_futures_direction_net_oi_grows_is_increasing():
    # 前一日淨空單 -500，今日淨空單 -200 -> 仍是負值，但空單減少 = 淨多方向增加
    assert futures_direction(today_net_oi=-200.0, prev_net_oi=-500.0) == "INCREASING"


def test_futures_direction_net_oi_shrinks_is_decreasing():
    # 前一日淨多單 800，今日淨多單 300 -> 兩者皆正值，但方向是減少
    assert futures_direction(today_net_oi=300.0, prev_net_oi=800.0) == "DECREASING"


def test_futures_direction_single_day_sign_does_not_determine_direction():
    # 單日 net_oi 是負值（空單），但相較前一日是增加的 -> 仍判 INCREASING，
    # 證明這裡看的是變化方向而非當日正負號。
    assert futures_direction(today_net_oi=-100.0, prev_net_oi=-900.0) == "INCREASING"


def test_futures_direction_equal_net_oi_is_increasing():
    assert futures_direction(today_net_oi=500.0, prev_net_oi=500.0) == "INCREASING"


# ---------------------------------------------------------------------------
# spot_futures_sync — 契約 4.1 節四象限
# ---------------------------------------------------------------------------


def test_spot_futures_sync_buy_and_increasing_is_synced():
    assert spot_futures_sync("BUY", "INCREASING") == "SYNCED"


def test_spot_futures_sync_sell_and_decreasing_is_synced():
    assert spot_futures_sync("SELL", "DECREASING") == "SYNCED"


def test_spot_futures_sync_buy_and_decreasing_is_diverged():
    assert spot_futures_sync("BUY", "DECREASING") == "DIVERGED"


def test_spot_futures_sync_sell_and_increasing_is_diverged():
    assert spot_futures_sync("SELL", "INCREASING") == "DIVERGED"


# ---------------------------------------------------------------------------
# margin_signal — 契約 4.2 節，threshold 預設 2%
# ---------------------------------------------------------------------------


def test_margin_signal_buy_with_large_margin_increase_is_warning():
    assert margin_signal("BUY", 0.035) == "法人-散戶對做警訊"


def test_margin_signal_buy_at_exact_threshold_is_warning():
    assert margin_signal("BUY", 0.02) == "法人-散戶對做警訊"


def test_margin_signal_buy_with_small_margin_increase_is_neutral():
    assert margin_signal("BUY", 0.01) == "一般"


def test_margin_signal_sell_with_large_margin_decrease_is_bottoming():
    assert margin_signal("SELL", -0.04) == "築底訊號"


def test_margin_signal_sell_at_exact_negative_threshold_is_bottoming():
    assert margin_signal("SELL", -0.02) == "築底訊號"


def test_margin_signal_sell_with_small_margin_decrease_is_neutral():
    assert margin_signal("SELL", -0.005) == "一般"


def test_margin_signal_buy_with_margin_decrease_is_neutral():
    # 法人買超但融資反而減少 -> 不構成對做警訊
    assert margin_signal("BUY", -0.03) == "一般"


def test_margin_signal_sell_with_margin_increase_is_neutral():
    # 法人賣超但融資增加 -> 不構成築底訊號
    assert margin_signal("SELL", 0.03) == "一般"


def test_margin_signal_custom_threshold_is_configurable():
    assert margin_signal("BUY", 0.015, threshold=0.01) == "法人-散戶對做警訊"
    assert margin_signal("BUY", 0.005, threshold=0.01) == "一般"


# ---------------------------------------------------------------------------
# large_trader_agree — 契約 4.3 節，十大交易人 vs 十大特定人 net_oi 正負號
# ---------------------------------------------------------------------------


def test_large_trader_agree_both_positive_is_true():
    assert large_trader_agree(1200.0, 300.0) is True


def test_large_trader_agree_both_negative_is_true():
    assert large_trader_agree(-500.0, -100.0) is True


def test_large_trader_agree_opposite_signs_is_false():
    assert large_trader_agree(800.0, -200.0) is False


def test_large_trader_agree_zero_treated_as_non_negative():
    # 沿用 spot_direction 的 >=0 慣例：0 視為非負，與負值不一致
    assert large_trader_agree(0.0, 500.0) is True
    assert large_trader_agree(0.0, -500.0) is False


def test_large_trader_agree_top10_trader_missing_is_none():
    # 3.1 節新表資料未到位 -> 一律回傳 None，不得省略成 True
    assert large_trader_agree(None, 300.0) is None


def test_large_trader_agree_top10_specific_missing_is_none():
    assert large_trader_agree(1200.0, None) is None


def test_large_trader_agree_both_missing_is_none():
    assert large_trader_agree(None, None) is None


# ---------------------------------------------------------------------------
# sync_signal — 契約 4.4 節綜合訊號燈
# ---------------------------------------------------------------------------


def test_sync_signal_synced_and_neutral_margin_is_green():
    assert sync_signal("SYNCED", "一般") == "GREEN"


def test_sync_signal_synced_and_bottoming_margin_is_green():
    # 4.2 的「築底訊號」不是「對做警訊」，不影響 GREEN 判定
    assert sync_signal("SYNCED", "築底訊號") == "GREEN"


def test_sync_signal_margin_warning_is_red_regardless_of_spot_futures():
    assert sync_signal("SYNCED", "法人-散戶對做警訊") == "RED"
    assert sync_signal("DIVERGED", "法人-散戶對做警訊") == "RED"


def test_sync_signal_diverged_and_neutral_margin_is_yellow():
    assert sync_signal("DIVERGED", "一般") == "YELLOW"


def test_sync_signal_diverged_and_bottoming_margin_is_yellow():
    assert sync_signal("DIVERGED", "築底訊號") == "YELLOW"
