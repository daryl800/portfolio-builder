# app/portfolio.py
from __future__ import annotations

import csv
from pathlib import Path
from typing import List

from app.config import HOLDINGS_CSV
from app.models import Holding


def load_holdings(path: Path | None = None) -> List[Holding]:
    """
    從 input/holdings.csv 讀取持股清單。

    CSV 欄位：
    symbol,position,avg_price,entry_date,currency,market,notes
    """
    csv_path = path or HOLDINGS_CSV
    holdings: List[Holding] = []

    if not csv_path.exists():
        print(f"[PORTFOLIO] holdings file not found: {csv_path}")
        return holdings

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue

            position_str = (row.get("position") or "").strip()
            avg_price_str = (row.get("avg_price") or "").strip()
            entry_date = (row.get("entry_date") or "").strip()
            currency = (row.get("currency") or "").strip().upper()
            market = (row.get("market") or "").strip().upper()
            notes = (row.get("notes") or "").strip()

            if not position_str:
                continue

            try:
                position = int(float(position_str))
            except ValueError:
                print(f"[PORTFOLIO] skip row with invalid position: {position_str!r}")
                continue

            try:
                avg_price = float(avg_price_str) if avg_price_str else 0.0
            except ValueError:
                print(f"[PORTFOLIO] skip row with invalid avg_price: {avg_price_str!r}")
                continue

            holdings.append(
                Holding(
                    symbol=symbol,
                    position=position,
                    avg_price=avg_price,
                    entry_date=entry_date,
                    currency=currency,
                    market=market,
                    notes=notes,
                )
            )

    print(f"[PORTFOLIO] loaded {len(holdings)} holdings from {csv_path}")
    return holdings
