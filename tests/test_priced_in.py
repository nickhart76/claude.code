from stock_sim.pricing.priced_in import priced_in_score


def test_no_drift_gives_low_score():
    closes = [100.0 + (i % 2) * 0.1 for i in range(40)]
    assert priced_in_score(closes, expected_direction=1) < 0.2


def test_aligned_strong_uptrend_scores_high():
    closes = [100.0 * (1.01 ** i) for i in range(40)]  # ~1% daily for 40d
    score = priced_in_score(closes, expected_direction=1, lookback=10)
    assert score > 0.5


def test_opposite_direction_scores_zero():
    closes = [100.0 * (0.99 ** i) for i in range(40)]  # declining
    assert priced_in_score(closes, expected_direction=1) == 0.0


def test_short_series_returns_zero():
    assert priced_in_score([100.0, 101.0], expected_direction=1) == 0.0
