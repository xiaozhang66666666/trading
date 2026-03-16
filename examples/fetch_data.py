from __future__ import annotations

from market_signal_system.data import DataManager


def main() -> None:
    svc = DataManager()
    qqq = svc.get_history(symbol="QQQ", start="2020-01-01", end="2025-12-31", interval="1d")
    eth = svc.get_history(symbol="ETH", start="2020-01-01", end="2025-12-31", interval="1d")

    print("QQQ rows:", len(qqq), "range:", qqq.index.min(), "->", qqq.index.max())
    print("ETH rows:", len(eth), "range:", eth.index.min(), "->", eth.index.max())


if __name__ == "__main__":
    main()
