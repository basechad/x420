#!/usr/bin/env python3
"""Verify an implementation against conformance/vectors.json.

Checks this repo's reference by default. The vectors are language-agnostic — every field is
plain JSON — so memecraft's TypeScript and chadstash's vendored Python should each run an
equivalent of this against the same file. Divergence then fails CI instead of a payout.

    python3 scripts/check_conformance.py
    python3 scripts/check_conformance.py --vectors ../other/vectors.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from x420.identity import meme_id, pixel_hash  # noqa: E402
from x420.lineage import Meme, resolve_launch_splits, resolve_splits  # noqa: E402

failures: list[str] = []


def compare(section: str, name: str, expected, actual) -> None:
    if expected == actual:
        print(f"  ok   [{section}] {name}")
    else:
        failures.append(f"[{section}] {name}\n         expected {expected}\n         actual   {actual}")
        print(f"  FAIL [{section}] {name}")
        print(f"         expected {expected}")
        print(f"         actual   {actual}")


def load_store(records: list[dict]) -> dict[str, Meme]:
    memes = [Meme.model_validate(r) for r in records]
    return {m.id: m for m in memes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vectors", default=None)
    args = ap.parse_args()

    path = Path(args.vectors) if args.vectors else (
        Path(__file__).resolve().parent.parent / "conformance" / "vectors.json"
    )
    data = json.loads(path.read_text())
    print(f"conformance vectors {data.get('x420_conformance')} — {path.name}\n")

    for case in data["identity"]:
        raw = bytes.fromhex(case["hex"]) if "hex" in case else case["utf8"].encode()
        compare("identity", case["name"], case["expected"], meme_id(raw))

    for case in data["pixel_hash"]:
        compare("pixel_hash", case["name"], case["expected"],
                pixel_hash(case["width"], case["height"], bytes.fromhex(case["rgba_hex"])))

    for case in data["splits"]:
        store = load_store(case["store"])
        kw = {"budget_bps": case["budget_bps"]} if "budget_bps" in case else {}
        compare("splits", case["name"], case["expected"],
                resolve_splits(case["meme_id"], store, **kw))

    for case in data["launch_splits"]:
        store = load_store(case["store"])
        compare("launch", case["name"], case["expected"],
                resolve_launch_splits(case["meme_id"], store, case["launcher"]))

    total = sum(len(data[k]) for k in ("identity", "pixel_hash", "splits", "launch_splits"))
    print()
    if failures:
        print(f"  {len(failures)} of {total} vectors failed — this implementation has diverged\n")
        return 1
    print(f"  all {total} vectors reproduced\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
