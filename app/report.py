# report.py
import csv
import json
from pathlib import Path

from app.config import REPORT_CSV, REPORT_JSON, REPORT_MD


def signal_bucket(score, momentum_1m, macd_hist):
    if score >= 25 and momentum_1m > 0 and macd_hist > 0:
        return "Strong"
    if score >= 15 or macd_hist > 0:
        return "Watch"
    return "Weak"


def why_flagged(opportunity):
    reasons = []

    m = opportunity.metrics

    if m.momentum_1m > 0.08:
        reasons.append("1M momentum strong")
    elif m.momentum_1m > 0:
        reasons.append("1M momentum positive")
    else:
        reasons.append("1M momentum weak")

    if m.volume_ratio > 1.5:
        reasons.append("volume above average")
    elif m.volume_ratio < 0.8:
        reasons.append("volume below average")

    if m.macd_hist > 0:
        reasons.append("MACD positive")
    else:
        reasons.append("MACD negative")

    return "; ".join(reasons)


def save_opportunities_csv(opportunities):
    REPORT_CSV.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "symbol",
                "price",
                "score",
                "signal_bucket",
                "why_flagged",
                "momentum_1m_pct",
                "volume_ratio",
                "macd_hist",
                "sentiment",
                "action_label",
                "confidence",
                "short_term_view",
                "long_term_view",
            ],
        )
        writer.writeheader()

        for idx, o in enumerate(opportunities, start=1):
            writer.writerow({
                "rank": idx,
                "symbol": o.symbol,
                "price": round(o.metrics.price, 2),
                "score": round(o.metrics.score, 2),
                "signal_bucket": signal_bucket(
                    o.metrics.score,
                    o.metrics.momentum_1m,
                    o.metrics.macd_hist,
                ),
                "why_flagged": why_flagged(o),
                "momentum_1m_pct": round(o.metrics.momentum_1m * 100, 2),
                "volume_ratio": round(o.metrics.volume_ratio, 2),
                "macd_hist": round(o.metrics.macd_hist, 4),
                "sentiment": o.analysis.sentiment,
                "action_label": o.analysis.action_label,
                "confidence": o.analysis.confidence,
                "short_term_view": o.analysis.short_term_view,
                "long_term_view": o.analysis.long_term_view,
            })


def save_report_json(payload):
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_report_md(content):
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)

    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write(content)


def build_opportunities_markdown(opportunities):
    lines = ["# Daily Opportunities", ""]

    if not opportunities:
        lines.append("No opportunities found today.")
        lines.append("")
        return "\n".join(lines)

    for idx, o in enumerate(opportunities, start=1):
        bucket = signal_bucket(
            o.metrics.score,
            o.metrics.momentum_1m,
            o.metrics.macd_hist,
        )

        lines.append(f"## {idx}. {o.symbol}")
        lines.append(f"- Price: {o.metrics.price:.2f}")
        lines.append(f"- Score: {o.metrics.score:.2f}")
        lines.append(f"- Signal: {bucket}")
        lines.append(f"- Why flagged: {why_flagged(o)}")
        lines.append(f"- 1M momentum: {o.metrics.momentum_1m * 100:+.2f}%")
        lines.append(f"- Volume ratio: {o.metrics.volume_ratio:.2f}x")
        lines.append(f"- MACD hist: {o.metrics.macd_hist:+.4f}")
        lines.append(f"- Sentiment: {o.analysis.sentiment}")
        lines.append(f"- Action: {o.analysis.action_label}")
        lines.append(f"- Confidence: {o.analysis.confidence}")
        lines.append(f"- Short term: {o.analysis.short_term_view}")
        lines.append(f"- Long term: {o.analysis.long_term_view}")
        if o.analysis.risks:
            lines.append(f"- Risks: {'; '.join(o.analysis.risks[:3])}")
        lines.append("")

    return "\n".join(lines)


def split_telegram_text(text, max_len=3500):
    if not text:
        return []

    chunks = []
    current = ""

    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue

        candidate = block if not current else current + "\n\n" + block

        if len(candidate) <= max_len:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        if len(block) <= max_len:
            current = block
            continue

        lines = block.split("\n")
        small = ""
        for line in lines:
            candidate_line = line if not small else small + "\n" + line
            if len(candidate_line) <= max_len:
                small = candidate_line
            else:
                if small:
                    chunks.append(small)
                small = line

        if small:
            current = small

    if current:
        chunks.append(current)

    return chunks


def save_full_markdown_report(summary_text, opportunities=None):
    parts = ["# Daily Stock Profile", "", summary_text.strip(), ""]

    if opportunities is not None:
        parts.append(build_opportunities_markdown(opportunities))

    save_report_md("\n".join(parts).strip() + "\n")
