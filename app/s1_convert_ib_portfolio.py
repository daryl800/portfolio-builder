# app/s1_convert_ib_portfolio.py
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

from app.config import INPUT_DIR, HOLDINGS_CSV


def _infer_symbol(raw: str) -> str:
    """
    從 IB 的 Financial Instrument Description 推出我們要用的 symbol。

    - 去掉前後空白
    - 把中間多餘空白縮成一個
    - 特例：C PRN -> CPRN（你實際使用的 ticker）
    - 其他一律大寫
    """
    s = " ".join(raw.strip().split())
    if s.upper() == "C PRN":
        return "CPRN"
    return s.upper()


def _infer_market(symbol: str, currency: str) -> str:
    c = (currency or "").upper()
    if c == "USD":
        return "US"
    if c == "HKD":
        return "HK"
    # fallback：用 currency 當 market 字串
    return c or "UNKNOWN"


def _iter_ib_portfolio_rows(path: Path) -> Iterable[dict]:
    """
    從 IB export CSV 中抓出 "Portfolio" 段落的股票列 (Security Type == STK)。
    """
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 找到 "Portfolio" 標題行
    start_idx = None
    for i, row in enumerate(rows):
        if row and (row[0] or "").strip().lower() == "portfolio":
            start_idx = i
            break
    if start_idx is None:
        raise ValueError(f"cannot find 'Portfolio' section in {path}")

    # 下一行是表頭
    header_idx = start_idx + 1
    header = [h.strip() for h in rows[header_idx]]

    # 從 header 之後到遇到空行 / "Cash Balances" 為止
    data_idx = header_idx + 1
    while data_idx < len(rows):
        row = rows[data_idx]
        first = (row[0] or "").strip() if row else ""
        if not row or first.lower() in {"cash balances", ""}:
            break
        rec = dict(zip(header, row))
        yield rec
        data_idx += 1


def _find_latest_ib_portfolio() -> Path:
    """
    在 input/ 目錄中尋找最新的 portfolio*.csv。
    """
    candidates = sorted(INPUT_DIR.glob("portfolio*.csv"))
    if not candidates:
        raise FileNotFoundError(f"no portfolio*.csv found in {INPUT_DIR}")
    latest = candidates[-1]
    print(f"[S1] auto-detected latest IB file: {latest.name}")
    return latest


def convert_ib_portfolio(
    src: Path,
    dst: Path | None = None,
    entry_date: date | None = None,
) -> Path:
    """
    讀 IB export CSV，產生 input/holdings.csv。

    :param src: IB 匯出檔路徑
    :param dst: holdings.csv 目標路徑，預設用 HOLDINGS_CSV
    :param entry_date: 若未指定，用今天日期
    :return: 產生的 holdings.csv 路徑
    """
    dst = dst or HOLDINGS_CSV
    entry_date = entry_date or date.today()

    if not src.exists():
        raise FileNotFoundError(f"IB portfolio CSV not found: {src}")

    print(f"[S1] reading IB portfolio from {src}")
    rows = list(_iter_ib_portfolio_rows(src))

    out_records: list[dict] = []
    for r in rows:
        sec_type = (r.get("Security Type") or "").strip().upper()
        if sec_type != "STK":
            continue  # 只保留股票

        desc = r.get("Financial Instrument Description") or ""
        currency = (r.get("Currency") or "").strip().upper()
        position_str = (r.get("Position") or "").strip()
        avg_price_str = (r.get("Average Price") or "").strip()

        if not position_str:
            continue

        try:
            position = int(float(position_str))
        except ValueError:
            print(f"[S1] skip row with invalid Position: {position_str!r}")
            continue

        try:
            avg_price = float(avg_price_str) if avg_price_str else 0.0
        except ValueError:
            print(f"[S1] skip row with invalid Average Price: {avg_price_str!r}")
            continue

        symbol = _infer_symbol(desc)

        # 港股：IB 檔裡是 9988, 9696, 3968...，你習慣加 .HK
        if currency == "HKD" and symbol.isdigit():
            symbol = f"{symbol}.HK"

        market = _infer_market(symbol, currency)

        out_records.append(
            {
                "symbol": symbol,
                "position": position,
                "avg_price": f"{avg_price:.6f}",
                "entry_date": entry_date.isoformat(),
                "currency": currency,
                "market": market,
                "notes": "",
            }
        )

    # 輸出 holdings.csv
    dst.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "position",
        "avg_price",
        "entry_date",
        "currency",
        "market",
        "notes",
    ]

    with dst.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in out_records:
            writer.writerow(rec)

    print(f"[S1] written holdings to {dst} (rows={len(out_records)})")
    return dst


def main(src_path: str | None = None) -> None:
    if src_path:
        src = Path(src_path)
    else:
        src = _find_latest_ib_portfolio()
    convert_ib_portfolio(src=src)


if __name__ == "__main__":
    main()
