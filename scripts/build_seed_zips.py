"""Regenerate ``src/regional_viz/_seed_zips.py``.

Deterministically samples up to N ZIPs per state + DC from the public
``bgruber/zip2fips`` crosswalk (the same one the dominant-county strategy
uses at runtime), preferring distinct counties within a state so the
choropleth has spatial spread even in low-population states.

Run from the repo root::

    python scripts/build_seed_zips.py --per-state 10 --seed 20260606
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import urllib.request
from pathlib import Path

ZIP2FIPS_URL = "https://raw.githubusercontent.com/bgruber/zip2fips/master/zip2fips.json"

STATE_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}


def build(per_state: int, seed: int) -> list[tuple[str, str, str]]:
    with urllib.request.urlopen(ZIP2FIPS_URL) as r:
        raw = json.load(r)

    by_state: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for z, f in raw.items():
        z, f = str(z).zfill(5), str(f).zfill(5)
        state_prefix = f[:2]
        if state_prefix in STATE_FIPS:
            by_state[state_prefix].append((z, f))

    rng = random.Random(seed)
    out: list[tuple[str, str, str]] = []
    for sp in sorted(by_state):
        pool = list(by_state[sp])
        rng.shuffle(pool)
        seen, primary, secondary = set(), [], []
        for z, f in pool:
            (primary if f not in seen else secondary).append((z, f))
            seen.add(f)
        for z, f in (primary + secondary)[:per_state]:
            out.append((z, f, STATE_FIPS[sp]))
    return out


def emit(rows: list[tuple[str, str, str]], dest: Path, seed: int, per_state: int) -> None:
    lines = [
        '"""Curated seed of real (ZIP5, county FIPS, state) triples.',
        "",
        f"Sampled deterministically (rng seed {seed}) from the public",
        f"bgruber/zip2fips crosswalk: up to {per_state} ZIPs per state + DC, preferring",
        "distinct counties within a state so the choropleth has spatial spread",
        "even in low-population states. By construction every entry round-trips",
        "through the dominant-county crosswalk used at runtime.",
        "",
        "To regenerate, see scripts/build_seed_zips.py.",
        '"""',
        "from __future__ import annotations",
        "",
        "SEED_ZIPS: list[tuple[str, str, str]] = [",
    ]
    last_state = None
    for z, f, s in rows:
        if s != last_state:
            lines.append(f"    # {s}")
            last_state = s
        lines.append(f'    ("{z}", "{f}", "{s}"),')
    lines.append("]")
    dest.write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-state", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260606)
    ap.add_argument(
        "--dest",
        type=Path,
        default=Path("src/regional_viz/_seed_zips.py"),
    )
    args = ap.parse_args()

    rows = build(args.per_state, args.seed)
    emit(rows, args.dest, args.seed, args.per_state)
    counties = {f for _, f, _ in rows}
    print(
        f"wrote {args.dest}: {len(rows)} ZIPs across "
        f"{len({s for *_, s in rows})} jurisdictions, {len(counties)} unique counties"
    )


if __name__ == "__main__":
    main()
