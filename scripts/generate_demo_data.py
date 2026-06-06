"""Write a synthetic ZIP+4 patient-count CSV to ``data/raw/synthetic.csv``."""
from __future__ import annotations

import argparse
from pathlib import Path

from regional_viz.synthetic import generate_synthetic_zip4


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--out", type=Path, default=Path("data/raw/synthetic.csv"),
    )
    args = ap.parse_args()

    df = generate_synthetic_zip4(n_rows=args.rows, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df):,} rows -> {args.out}")
    print(
        f"  unique ZIPs: {df['eps_zip'].nunique():,}   "
        f"total patients: {df['patients'].sum():,}"
    )


if __name__ == "__main__":
    main()
