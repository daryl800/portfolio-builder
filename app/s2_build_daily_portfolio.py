# app/s2_build_daily_portfolio.py
from __future__ import annotations

import json
import csv
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.config import WATCHLIST_CSV, HOLDINGS_CSV, DAILY_PORTFOLIO_SNAPSHOT
from app.market_data import get_stock_metrics
from app.portfolio import load_holdings


def load_watchlist_symbols() -> list[str]:
    symbols: list[str] = []
    if WATCHLIST_CSV.exists():
        with WATCHLIST_CSV.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = (row.get("symbol") or "").strip().upper()
                if symbol:
                    symbols.append(symbol)
    # 去重，保留順序
    return list(dict.fromkeys(symbols))


def build_holdings_block() -> list[dict]:
    """
    從 input/holdings.csv 載入 Holding（用 position 欄位），
    搭配行情計算 pnl_pct / pnl_value，輸出 holdings 區塊。
    """
    positions = load_holdings()
    holdings_out: list[dict] = []

    for p in positions:
        metrics = get_stock_metrics(p.symbol)
        if not metrics:
            print(f"[S2] skip holding {p.symbol}: no metrics")
            continue

        pnl_pct = (
            (metrics.price - p.avg_price) / p.avg_price
            if p.avg_price
            else 0.0
        )
        pnl_value = (metrics.price - p.avg_price) * p.position

        holdings_out.append(
            {
                "symbol": p.symbol,
                "position": p.position,
                "avg_price": p.avg_price,
                "entry_date": p.entry_date,
                "currency": p.currency,
                "market": p.market,
                "notes": p.notes,
                "metrics": asdict(metrics),
                "pnl_pct": pnl_pct,
                "pnl_value": pnl_value,
            }
        )

    return holdings_out


def build_opportunities_block() -> list[dict]:
    """
    以 watchlist - holdings 得到 watchlist-only symbols，
    對每一檔抓 metrics，輸出 opportunities 區塊。
    """
    holdings = load_holdings()
    holding_symbols = {p.symbol for p in holdings}

    watchlist_symbols = load_watchlist_symbols()
    watchlist_only = [s for s in watchlist_symbols if s not in holding_symbols]

    opps_out: list[dict] = []

    for symbol in watchlist_only:
        metrics = get_stock_metrics(symbol)
        if not metrics:
            print(f"[S2] skip opp {symbol}: no metrics")
            continue

        opps_out.append(
            {
                "symbol": symbol,
                "metrics": asdict(metrics),
                "notes": None,
            }
        )

    return opps_out


def main() -> Path:
    holdings_block = build_holdings_block()
    opps_block = build_opportunities_block()

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "holdings": holdings_block,
        "opportunities": opps_block,
    }

    DAILY_PORTFOLIO_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    with DAILY_PORTFOLIO_SNAPSHOT.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"[S2] written snapshot to {DAILY_PORTFOLIO_SNAPSHOT} "
        f"(holdings={len(holdings_block)}, opps={len(opps_block)})"
    )

    return DAILY_PORTFOLIO_SNAPSHOT


if __name__ == "__main__":
    main()
