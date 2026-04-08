import pytest

from stock_sim.portfolio import Portfolio


@pytest.fixture
def pf(tmp_path):
    db = tmp_path / "test.sqlite"
    p = Portfolio(db, starting_cash=10_000.0)
    yield p
    p.close()


def test_initial_state(pf):
    assert pf.cash == 10_000.0
    assert pf.positions() == []
    assert pf.trades() == []


def test_buy_updates_cash_and_position(pf):
    pf.buy("AAPL", 10, 150.0, note="test")
    assert pf.cash == pytest.approx(10_000.0 - 1500.0)
    pos = pf.position("AAPL")
    assert pos is not None
    assert pos.quantity == 10
    assert pos.avg_cost == 150.0


def test_buy_then_buy_averages_cost(pf):
    pf.buy("AAPL", 10, 100.0)
    pf.buy("AAPL", 10, 120.0)
    pos = pf.position("AAPL")
    assert pos.quantity == 20
    assert pos.avg_cost == pytest.approx(110.0)


def test_sell_realizes_pnl(pf):
    pf.buy("AAPL", 10, 100.0)
    pf.sell("AAPL", 5, 120.0)
    pos = pf.position("AAPL")
    assert pos.quantity == 5
    assert pf.realized_pnl_total() == pytest.approx(100.0)  # 5 * (120-100)


def test_sell_all_closes_position(pf):
    pf.buy("MSFT", 4, 200.0)
    pf.sell("MSFT", 4, 210.0)
    assert pf.position("MSFT") is None
    assert pf.cash == pytest.approx(10_000.0 - 800.0 + 840.0)


def test_insufficient_cash_rejects(pf):
    with pytest.raises(ValueError, match="insufficient cash"):
        pf.buy("TSLA", 100, 500.0)


def test_insufficient_shares_rejects(pf):
    pf.buy("AAPL", 3, 100.0)
    with pytest.raises(ValueError, match="insufficient shares"):
        pf.sell("AAPL", 5, 110.0)


def test_equity_marks_to_market(pf):
    pf.buy("AAPL", 10, 100.0)
    eq = pf.equity({"AAPL": 110.0})
    assert eq == pytest.approx((10_000.0 - 1000.0) + 10 * 110.0)


def test_reset_restores_starting_cash(pf):
    pf.buy("AAPL", 10, 100.0)
    pf.reset()
    assert pf.cash == 10_000.0
    assert pf.positions() == []
    assert pf.trades() == []


def test_persistence_across_instances(tmp_path):
    db = tmp_path / "persist.sqlite"
    with Portfolio(db, starting_cash=5_000.0) as pf1:
        pf1.buy("NVDA", 2, 400.0)
    with Portfolio(db, starting_cash=5_000.0) as pf2:
        assert pf2.cash == pytest.approx(5_000.0 - 800.0)
        pos = pf2.position("NVDA")
        assert pos is not None and pos.quantity == 2
