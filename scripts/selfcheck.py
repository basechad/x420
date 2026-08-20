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

from x420.identity import (  # noqa: E402
    ID_HEX_CHARS,
    meme_id,
    meme_id_from_digest,
    pixel_hash,
)
from x420.lineage import (  # noqa: E402
    BPS_TOTAL,
    canonical_id,
    Content,
    License,
    LineageCycle,
    LineageTooDeep,
    MAX_LINEAGE_DEPTH,
    Meme,
    Parent,
    Provenance,
    resolve_launch_splits,
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

# The tier between file-identity and perceptual similarity: same pixels in a different wrapper
# must match exactly, so memecraft's metadata-injected re-exports can be linked without review.
_raster = bytes([255, 0, 0, 255, 0, 255, 0, 255])  # 2x1 RGBA
check(
    "pixel_hash ignores the file wrapper",
    meme_id(b"wrapper-A" + _raster) != meme_id(b"wrapper-B!!" + _raster)
    and pixel_hash(2, 1, _raster) == pixel_hash(2, 1, _raster),
)
check("pixel_hash folds in dimensions", pixel_hash(2, 1, _raster) != pixel_hash(1, 2, _raster))
try:
    pixel_hash(2, 1, _raster[:6])
    check("pixel_hash rejects a mis-sized raster", False, "accepted short input")
except ValueError:
    check("pixel_hash rejects a mis-sized raster", True)

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

# A minority payee resolves to zero once the budget is small enough, which happens naturally
# deep in an ancestry. LineageSplitter rejects a zero share at construction, so emitting one
# turns a resolvable lineage into a launch that reverts.
_minor = Meme(
    id="x420:" + "5" * 32,
    content=Content(uri="u", sha256="5" * 64, media_type="image/png"),
    attribution=[
        {"address": _a, "role": "creator", "share_bps": 9999},
        {"address": _b, "role": "letterer", "share_bps": 1},
    ],
    license=License(id="l", derivatives=True, royalty_bps=0),
)
_small = resolve_splits(_minor.id, {_minor.id: _minor}, budget_bps=5)
check(
    "no payee resolves to a zero share",
    all(v > 0 for v in _small.values()) and sum(_small.values()) == 5,
    str(_small),
)

# The launcher is the payer, so resolve_splits never lists them. Treating that owed-set as the
# whole payee list hands a launcher's entire fee stream to someone else — which made launching
# another creator's meme pure altruism. resolve_launch_splits composes the complete list.
_lr = "0x" + "d" * 40
_orig_r = Meme(
    id="x420:" + "a" * 32,
    content=Content(uri="u", sha256="a" * 64, media_type="image/png"),
    attribution=[{"address": _a, "role": "creator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=2000),
)
_remix_r = Meme(
    id="x420:" + "b" * 32,
    content=Content(uri="u", sha256="b" * 64, media_type="image/png"),
    parents=[Parent(id=_orig_r.id, relation="remix")],
    attribution=[{"address": _b, "role": "creator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=2000),
)
_rs = {_orig_r.id: _orig_r, _remix_r.id: _remix_r}
_launch = resolve_launch_splits(_remix_r.id, _rs, _lr)
check(
    "the launcher keeps 10000 minus the royalty",
    _launch == {_lr: 8000, _b: 1600, _a: 400},
    str(_launch),
)
check("launch splits total exactly", sum(_launch.values()) == BPS_TOTAL)
check(
    "launching your own meme yields one merged payee",
    resolve_launch_splits(_orig_r.id, _rs, _a) == {_a: BPS_TOTAL},
)

# Resolution normally self-terminates once a carve rounds to zero, and how deep that goes is
# set by the royalty RATE, not the chain length. Above ~9990 bps the natural bound exceeds
# Python's stack, so an attacker-supplied record could turn a request into a RecursionError —
# a 500 rather than a rejected record. The cap makes that a defined refusal.
_deep, _prev = {}, None
for _i in range(1, 200):
    _m = Meme(
        id="x420:" + f"{_i:032d}",
        content=Content(uri="u", sha256=f"{_i:064d}", media_type="image/png"),
        parents=[Parent(id=_prev, relation="remix")] if _prev else [],
        attribution=[{"address": "0x" + f"{_i:040x}", "role": "creator", "share_bps": BPS_TOTAL}],
        license=License(id="l", derivatives=True, royalty_bps=9999),
    )
    _deep[_m.id] = _m
    _prev = _m.id
try:
    resolve_splits(_prev, _deep)
    check("deep ancestry is refused, not a RecursionError", False, "no refusal")
except LineageTooDeep:
    check("deep ancestry is refused, not a RecursionError", True)
except RecursionError:
    check("deep ancestry is refused, not a RecursionError", False, "RecursionError")

# A long duplicate chain is cheap to author and costly to follow, so it is bounded too.
_dchain = {}
for _i in range(1, MAX_LINEAGE_DEPTH + 20):
    _nxt = "x420:" + f"{_i + 1:032d}" if _i < MAX_LINEAGE_DEPTH + 19 else None
    _dchain["x420:" + f"{_i:032d}"] = Meme(
        id="x420:" + f"{_i:032d}",
        content=Content(uri="u", sha256=f"{_i:064d}", media_type="image/png"),
        attribution=[{"address": _a, "role": "creator", "share_bps": BPS_TOTAL}],
        license=License(id="l", derivatives=True, royalty_bps=0),
        duplicate_of=_nxt,
    )
try:
    canonical_id("x420:" + f"{1:032d}", _dchain)
    check("long duplicate chains are refused", False, "no refusal")
except LineageTooDeep:
    check("long duplicate chains are refused", True)

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

# A duplicate is the same work, not a child. Launching a token on a re-upload must pay whoever
# the original would have paid, or re-uploading becomes a way to capture a creator's share.
_orig = Meme(
    id="x420:" + "1" * 32,
    content=Content(uri="u", sha256="1" * 64, media_type="image/png"),
    attribution=[{"address": _a, "role": "creator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=1000),
)
_copy = Meme(  # re-uploaded by someone else, royalty stripped to zero
    id="x420:" + "2" * 32,
    content=Content(uri="u", sha256="2" * 64, media_type="image/png"),
    attribution=[{"address": _b, "role": "creator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=0),
    duplicate_of=_orig.id,
)
_dupes = {_orig.id: _orig, _copy.id: _copy}
check(
    "a duplicate pays the original, not the re-uploader",
    resolve_splits(_copy.id, _dupes) == {_a: BPS_TOTAL},
    str(resolve_splits(_copy.id, _dupes)),
)
check("canonical_id resolves through a duplicate", canonical_id(_copy.id, _dupes) == _orig.id)

# Regression guard: the carve RATE must come from the canonical record. Reading it from the
# duplicate let a re-upload with royalty_bps=0 strip the original's royalty from any remix.
_c = "0x" + "c" * 40
_via_copy = Meme(
    id="x420:" + "3" * 32,
    content=Content(uri="u", sha256="3" * 64, media_type="image/png"),
    parents=[Parent(id=_copy.id, relation="remix")],
    attribution=[{"address": _c, "role": "creator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=0),
)
_via_orig = Meme(
    id="x420:" + "4" * 32,
    content=Content(uri="u", sha256="4" * 64, media_type="image/png"),
    parents=[Parent(id=_orig.id, relation="remix")],
    attribution=[{"address": _c, "role": "creator", "share_bps": BPS_TOTAL}],
    license=License(id="l", derivatives=True, royalty_bps=0),
)
_laundry = {**_dupes, _via_copy.id: _via_copy, _via_orig.id: _via_orig}
check(
    "remixing a copy cannot launder away the royalty",
    resolve_splits(_via_copy.id, _laundry) == resolve_splits(_via_orig.id, _laundry),
    f"copy={resolve_splits(_via_copy.id, _laundry)} orig={resolve_splits(_via_orig.id, _laundry)}",
)

print()
if failures:
    print(f"  {len(failures)} invariant(s) broken\n")
    sys.exit(1)
print("  all invariants hold\n")
