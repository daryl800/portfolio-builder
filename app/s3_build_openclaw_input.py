# app/s3_build_openclaw_input.py
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from app.config import DAILY_PORTFOLIO_SNAPSHOT, DAILY_PORTFOLIO_OC_INPUT
from app.llm_analysis import analyze_stock_news, analyze_stock_news_batch
from app.models import StockMetrics, Opportunity
from app.news import fetch_yahoo_news
from app.report import (
    signal_bucket,
    why_flagged,
)
from app.telegram_bot import send_telegram_message


def load_snapshot() -> dict[str, Any]:
    if not DAILY_PORTFOLIO_SNAPSHOT.exists():
        raise FileNotFoundError(f"snapshot not found: {DAILY_PORTFOLIO_SNAPSHOT}")
    with DAILY_PORTFOLIO_SNAPSHOT.open("r", encoding="utf-8") as f:
        data = json.load(f)
    print(
        f"[S3] loaded snapshot "
        f"(holdings={len(data.get('holdings', []))}, "
        f"opps={len(data.get('opportunities', []))})"
    )
    return data


def build_holding_rows(snapshot: dict[str, Any]) -> list[dict]:
    holdings_in = snapshot.get("holdings", [])
    rows: list[dict] = []
    symbol_news_pairs: list[tuple[str, list]] = []

    for h in holdings_in:
        symbol = h["symbol"]
        metrics = StockMetrics(**h["metrics"])

        news = fetch_yahoo_news(symbol, limit=3)
        symbol_news_pairs.append((symbol, news))

        rows.append(
            {
                "symbol": symbol,
                "position": h["position"],
                "avg_price": h["avg_price"],
                "entry_date": h["entry_date"],
                "currency": h["currency"],
                "market": h["market"],
                "notes": h["notes"],
                "current_price": metrics.price,
                "score": metrics.score,
                "metrics": metrics,
                "news": news,
                "pnl_pct": h["pnl_pct"],
                "pnl_value": h["pnl_value"],
            }
        )

    analysis_map = analyze_stock_news_batch(symbol_news_pairs)

    for h in rows:
        analysis = analysis_map.get(h["symbol"])
        if analysis is None:
            analysis = analyze_stock_news(h["symbol"], h["news"])
        h["analysis"] = analysis

    return rows


def build_opportunities(snapshot: dict[str, Any]) -> list[Opportunity]:
    opps_in = snapshot.get("opportunities", [])
    rows: list[dict] = []
    symbol_news_pairs: list[tuple[str, list]] = []

    for o in opps_in:
        symbol = o["symbol"]
        metrics = StockMetrics(**o["metrics"])

        news = fetch_yahoo_news(symbol, limit=3)
        symbol_news_pairs.append((symbol, news))

        rows.append({"symbol": symbol, "metrics": metrics, "news": news})

    analysis_map = analyze_stock_news_batch(symbol_news_pairs)

    opportunities: list[Opportunity] = []
    for row in rows:
        symbol = row["symbol"]
        metrics = row["metrics"]
        news = row["news"]

        analysis = analysis_map.get(symbol)
        if analysis is None:
            analysis = analyze_stock_news(symbol, news)

        opportunities.append(
            Opportunity(
                symbol=symbol,
                metrics=metrics,
                news=news,
                analysis=analysis,
            )
        )

    opportunities.sort(key=lambda x: x.metrics.score, reverse=True)
    return opportunities


def build_summary(holding_rows: list[dict], opportunities: list[Opportunity]) -> str:
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = ["<b>Daily Stock Profile</b>", ""]

    if holding_rows:
        lines.append(f"<b>Holdings Review</b> ({now_text})")
        for h in holding_rows:
            symbol = escape(h["symbol"])
            market = escape(h["market"] or h["currency"])
            notes = escape(h["notes"] or "")
            sentiment = escape(h["analysis"].sentiment or "")
            action = escape(h["analysis"].action_label or "")
            short_view = escape(h["analysis"].short_term_view or "")
            long_view = escape(h["analysis"].long_term_view or "")
            risks = [escape(r) for r in (h["analysis"].risks or [])]

            pnl_pct_text = f"{h['pnl_pct'] * 100:+.1f}%"
            lines.append(
                f"<b>{symbol}</b> [{market}] | 持有 {h['position']} 股 | 成本 {h['avg_price']:.2f} | "
                f"現價 {h['current_price']:.2f} | PnL {pnl_pct_text}"
            )
            if notes:
                lines.append(f"分類: {notes}")
            lines.append(f"情緒/動作: {sentiment} / {action}")
            lines.append(f"短期: {short_view}")
            lines.append(f"長期: {long_view}")
            if risks:
                lines.append(f"風險: {'；'.join(risks[:2])}")
            lines.append("")

    if opportunities:
        lines.append(f"<b>Watchlist / Opportunities</b> ({now_text})")
        for o in opportunities:
            symbol = escape(o.symbol)
            sentiment = escape(o.analysis.sentiment or "")
            action = escape(o.analysis.action_label or "")
            short_view = escape(o.analysis.short_term_view or "")
            long_view = escape(o.analysis.long_term_view or "")
            risks = [escape(r) for r in (o.analysis.risks or [])]

            bucket = signal_bucket(
                o.metrics.score, o.metrics.momentum_1m, o.metrics.macd_hist
            )

            lines.append(
                f"<b>{symbol}</b> | ${o.metrics.price:.2f} | score {o.metrics.score:.1f} | "
                f"{bucket} | {sentiment} | {action}"
            )
            lines.append(
                f"技術: 1M {o.metrics.momentum_1m*100:+.1f}% | Vol {o.metrics.volume_ratio:.2f}x | "
                f"MACD {o.metrics.macd_hist:+.2f}"
            )
            lines.append(f"原因: {escape(why_flagged(o))}")
            lines.append(f"短期: {short_view}")
            lines.append(f"長期: {long_view}")
            if risks:
                lines.append(f"風險: {'；'.join(risks[:2])}")
            lines.append("")

    return "\n".join(lines)


def _split_telegram_text(text: str, max_len: int = 3500) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    cur_len = 0

    for line in text.splitlines():
        line_len = len(line) + 1  # 包含換行
        if cur_len + line_len > max_len and buf:
            chunks.append("\n".join(buf))
            buf = []
            cur_len = 0
        buf.append(line)
        cur_len += line_len

    if buf:
        chunks.append("\n".join(buf))

    return chunks


def main() -> Path:
    snapshot = load_snapshot()

    holding_rows = build_holding_rows(snapshot)
    opportunities = build_opportunities(snapshot)

    print(f"[S3] holding_rows count: {len(holding_rows)}")
    print(f"[S3] opportunities count: {len(opportunities)}")

    # 組成「全胖版」 payload
    payload = {
        "generated_at": snapshot.get("generated_at"),
        "holdings": [
            {
                "symbol": h["symbol"],
                "position": h["position"],
                "avg_price": h["avg_price"],
                "entry_date": h["entry_date"],
                "currency": h["currency"],
                "market": h["market"],
                "notes": h["notes"],
                "current_price": h["current_price"],
                "score": h["score"],
                "pnl_pct": h["pnl_pct"],
                "pnl_value": h["pnl_value"],
                "metrics": asdict(h["metrics"]),
                "analysis": asdict(h["analysis"]),
                "news": [asdict(n) for n in h["news"]],
            }
            for h in holding_rows
        ],
        "opportunities": [
            {
                "symbol": o.symbol,
                "metrics": asdict(o.metrics),
                "analysis": asdict(o.analysis),
                "news": [asdict(n) for n in o.news],
            }
            for o in opportunities
        ],
    }

    DAILY_PORTFOLIO_OC_INPUT.parent.mkdir(parents=True, exist_ok=True)
    with DAILY_PORTFOLIO_OC_INPUT.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[S3] written full profile to {DAILY_PORTFOLIO_OC_INPUT}")

    # Telegram summary
    summary = build_summary(holding_rows, opportunities)
    print("[S3] summary preview:\n", summary[:500])

    chunks = _split_telegram_text(summary)
    ok = True
    msg = "ok"
    for chunk in chunks:
        ok, msg = send_telegram_message(chunk)
        if not ok:
            print(f"[S3] Telegram send failed: {msg}")
            break

    print("[S3] Done.")
    return DAILY_PORTFOLIO_OC_INPUT


if __name__ == "__main__":
    main()
