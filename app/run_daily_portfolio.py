# app/run_daily_portfolio.py
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
import sys

from app import s1_convert_ib_portfolio, s2_build_daily_portfolio, s3_build_openclaw_input
from app.config import (
    VPS_USER,
    VPS_HOST,
    VPS_TARGET_PATH,
)

ROOT = Path(__file__).resolve().parent.parent

def run_scp(src: Path, dest: str) -> None:
    cmd = ["scp", str(src), dest]
    print(f"[RUN] SCP: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    print("[RUN] SCP done")

def main() -> None:
    # 1) S1: IB export -> input/holdings.csv
    print("[RUN] Step 1: convert IB portfolio -> input/holdings.csv")
    s1_convert_ib_portfolio.main(None)

    # 2) S2: holdings + watchlist + yfinance -> data/daily_portfolio_snapshot.json
    print("[RUN] Step 2: build daily portfolio snapshot")
    s2_build_daily_portfolio.main()

    # 3) S3: snapshot -> full profile + Telegram + data/daily_portfolio_openclaw_input.json
    print("[RUN] Step 3: build full profile & OpenClaw input + Telegram")
    oc_input_path = s3_build_openclaw_input.main()  

    # 4) 加 timestamp 本地留存一份，並 scp 一份固定檔名到 VPS
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    dated_path = oc_input_path.with_name(
        f"daily_portfolio_openclaw_input_{ts}{oc_input_path.suffix}"
    )
    print(f"[RUN] rename {oc_input_path.name} -> {dated_path.name}")
    oc_input_path.rename(dated_path)

    dest = f"{VPS_USER}@{VPS_HOST}:{VPS_TARGET_PATH}/daily_portfolio_openclaw_input.json"
    run_scp(dated_path, dest)

    print("[RUN] All steps completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[RUN] ERROR: {e}", file=sys.stderr)
        sys.exit(1)
