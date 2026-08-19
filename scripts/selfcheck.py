#!/usr/bin/env python3
"""Invariants the reference implementation must never break.

Fast enough to run on every commit. Each case corresponds to a property other repos rely on,
and two of them are regressions for bugs that actually shipped.

Run directly, or via the pre-commit hook in scripts/hooks/pre-commit.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from x420.identity import ID_HEX_CHARS, meme_id, meme_id_from_digest  # noqa: E402
from x420.lineage import (  # noqa: E402
    BPS_TOTAL,
    Content,
    License,
    LineageCycle,
    Meme,
    Parent,
    Provenance,
    resolve_splits,
)
from x420.store import MEMES  # noqa: E402

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        failures.append(f"{name}{f' — {detail}' if detail else ''}")
        print(f"  FAIL {name}{f' — {detail}' if detail else ''}")


# --- identity ---------------------------------------------------------------------------

check(
    "id derivation is stable",
    meme_id(b"hello world") == "x420:b94d27b9934d3e08a52e52d7da7dabfa",
    meme_id(b"hello world"),
)
check("id carries no chain segment", meme_id(b"x").count(":") == 1)
check("id is 128 bits", len(meme_id(b"x").split(":")[1]) == ID_HEX_CHARS == 32)

try:
    meme_id_from_digest("not-a-digest")
    check("short digests are rejected", False, "accepted a malformed digest")
except ValueError:
    check("short digests are rejected", True)

# --- splits -----------------------------------------------------------------------------

for meme in MEMES.values():
    splits = resolve_splits(meme.id, MEMES)
    check(
        f"splits sum to {BPS_TOTAL} for {meme.id[:14]}…",
        sum(splits.values()) == BPS_TOTAL,
        f"got {sum(splits.values())}",
    )

# Regression: dust was assigned with max(), which resolves ties by insertion order. The
# TypeScript port sorted by address, so the two implementations paid different payees the
# remainder. Ties must break on the lower address in both.
_a = "0x" + "a" * 40
_b = "0x" + "b" * 40
_tie = Meme(
    id="x420:" + "0" * 32,
    content=Content(uri="x", sha256="0" * 64, media_type="image/png"),
    attribution=[
        {"address": _b, "role": "creator", "share_bps": 5000},
        {"address": _a, "role": "editor", "share_bps": 5000},
    ],
    license=License(id="l", derivatives=True, royalty_bps=0),
)
_split = resolve_splits(_tie.id, {_tie.id: _tie}, budget_bps=9999)
check(
    "dust ties break on the lower address",
    _split[_a] > _split[_b] and sum(_split.values()) == 9999,
    str(_split),
)

# Regression: a registry where records name their parents is a graph, not a tree, so
# resolution must refuse to recurse forever.
_x = "x420:" + "1" * 32
_y = "x420:" + "2" * 32
_cyclic = {
    _x: Meme(
        id=_x,
        content=Content(uri="x", sha256="1" * 64, media_type="image/png"),
        parents=[Parent(id=_y, relation="remix")],
        attribution=[{"address": _a, "role": "creator", "share_bps": BPS_TOTAL}],
        license=License(id="l", derivatives=True, royalty_bps=1000),
    ),
    _y: Meme(
        id=_y,
        content=Content(uri="y", sha256="2" * 64, media_type="image/png"),
        parents=[Parent(id=_x, relation="remix")],
        attribution=[{"address": _b, "role": "creator", "share_bps": BPS_TOTAL}],
        license=License(id="l", derivatives=True, royalty_bps=1000),
    ),
}
try:
    resolve_splits(_x, _cyclic)
    check("lineage cycles are refused", False, "recursed without raising")
except LineageCycle:
    check("lineage cycles are refused", True)

# --- provenance -------------------------------------------------------------------------

# An empty `parents` on an `unknown` record means provenance was never captured, NOT that the
# meme is an origin. Conflating them lets every backfilled record claim full allocation.
_unknown = Meme(
    id="x420:" + "3" * 32,
    content=Content(uri="z", sha256="3" * 64, media_type="image/png"),
    attribution=[{"address": _a, "role": "curator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=0),
    provenance=Provenance.UNKNOWN,
)
check("unknown provenance is not a verified original", not _unknown.is_verified_original)

# "Nobody is owed" must stay distinct from "nobody knows who is owed". Encoding public domain
# as a commons payee would route a whole fee stream to the holding pool for work that was never
# owed to anyone. See SPEC.md 3.3.
_pd = Meme(
    id="x420:" + "9" * 32,
    content=Content(uri="u", sha256="9" * 64, media_type="image/png"),
    attribution=[],
    license=License(id="x420-public-domain", derivatives=True, royalty_bps=0),
)
check("free-to-use memes owe nobody", resolve_splits(_pd.id, {_pd.id: _pd}) == {} and _pd.is_free_to_use)

# A free-to-use parent carves nothing, and the rest of the ancestry still totals exactly.
_heir = Meme(
    id="x420:" + "8" * 32,
    content=Content(uri="u", sha256="8" * 64, media_type="image/png"),
    parents=[Parent(id=_pd.id, relation="template")],
    attribution=[{"address": _a, "role": "creator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=0),
)
_hs = resolve_splits(_heir.id, {_pd.id: _pd, _heir.id: _heir})
check("a free-to-use parent carves nothing", _hs == {_a: BPS_TOTAL}, str(_hs))

print()
if failures:
    print(f"  {len(failures)} invariant(s) broken\n")
    sys.exit(1)
print("  all invariants hold\n")
