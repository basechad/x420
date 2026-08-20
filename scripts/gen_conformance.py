#!/usr/bin/env python3
"""Generate conformance/vectors.json from the reference implementation.

The vectors are the contract between implementations. Three copies of the split rule now
exist — this repo's Python, memecraft's TypeScript, and chadstash's vendored Python — and they
have already drifted twice: once over dust tie-breaking, and again when chadstash vendored a
snapshot that predates duplicate resolution and the zero-share filter.

Cases are generated from the reference rather than written by hand so they cannot disagree
with it. Regenerate after any behavioural change, and review the diff: a vector that changes
unexpectedly means the change was wider than intended.

    python3 scripts/gen_conformance.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from x420.identity import meme_id, pixel_hash  # noqa: E402
from x420.lineage import (  # noqa: E402
    Content,
    License,
    Meme,
    Parent,
    resolve_launch_splits,
    resolve_splits,
)

A = "0x" + "a" * 40
B = "0x" + "b" * 40
C = "0x" + "c" * 40
LAUNCHER = "0x" + "f" * 40


def rec(n, *, parents=(), payees=None, roy=0, dup=None, provenance="attested"):
    return Meme(
        id="x420:" + f"{n:032d}",
        content=Content(uri="u", sha256=f"{n:064d}", media_type="image/png"),
        parents=[Parent(id="x420:" + f"{p:032d}", relation=r) for p, r in parents],
        attribution=[
            {"address": a, "role": role, "share_bps": s} for a, role, s in (payees or [])
        ],
        license=License(id="l", derivatives=True, royalty_bps=roy),
        duplicate_of=("x420:" + f"{dup:032d}") if dup else None,
        provenance=provenance,
    )


def dump(store):
    return [m.model_dump(mode="json", exclude_none=True) for m in store.values()]


split_cases: list[dict] = []
launch_cases: list[dict] = []


def split_case(name, why, store, meme, budget=None):
    kw = {"budget_bps": budget} if budget is not None else {}
    split_cases.append({
        "name": name, "why": why, "store": dump(store), "meme_id": meme,
        **({"budget_bps": budget} if budget is not None else {}),
        "expected": resolve_splits(meme, store, **kw),
    })


def launch_case(name, why, store, meme, launcher):
    launch_cases.append({
        "name": name, "why": why, "store": dump(store), "meme_id": meme,
        "launcher": launcher, "expected": resolve_launch_splits(meme, store, launcher),
    })


# --- lineage ------------------------------------------------------------------------------

orig = rec(1, payees=[(A, "creator", 10000)], roy=2000)
remix = rec(2, parents=[(1, "remix")], payees=[(B, "creator", 10000)], roy=2000)
deep = rec(3, parents=[(2, "remix")], payees=[(C, "creator", 10000)], roy=2000)
chain = {m.id: m for m in (orig, remix, deep)}

split_case("single-generation carve",
           "a parent takes its own royalty_bps off the top", chain, remix.id)
split_case("three-generation compounding",
           "each generation carves from gross, so ancestors decay geometrically",
           chain, deep.id)

# Dust: the tie-break must not depend on insertion order — this diverged once already.
tie = rec(4, payees=[(B, "creator", 5000), (A, "editor", 5000)])
split_case("dust ties break on the lower address",
           "max() alone resolves ties by insertion order, which is not portable",
           {tie.id: tie}, tie.id, budget=9999)

# Zero shares must be dropped: LineageSplitter rejects a zero payee at construction.
minor = rec(5, payees=[(A, "creator", 9999), (B, "letterer", 1)])
split_case("minority payees that round to nothing are dropped",
           "an emitted zero-bps payee makes the splitter revert",
           {minor.id: minor}, minor.id, budget=5)

# Free to use: an empty attribution means nobody is owed, distinct from unknown-creator.
free = rec(6, payees=[], roy=0, provenance="unknown")
heir = rec(7, parents=[(6, "template")], payees=[(A, "creator", 10000)])
split_case("a free-to-use meme owes nobody",
           "empty attribution is meaningful, not malformed", {free.id: free}, free.id)
split_case("a free-to-use parent carves nothing",
           "and the remaining ancestry still totals exactly",
           {free.id: free, heir.id: heir}, heir.id)

# Duplicates resolve to the canonical record, and the carve rate comes from it.
copy = rec(8, payees=[(B, "creator", 10000)], roy=0, dup=1)
via_copy = rec(9, parents=[(8, "remix")], payees=[(C, "creator", 10000)])
dupes = {orig.id: orig, copy.id: copy, via_copy.id: via_copy}
split_case("a duplicate pays the original, not the re-uploader",
           "duplicate_of is equivalence, not derivation", dupes, copy.id)
split_case("remixing a copy cannot launder away the royalty",
           "the carve rate resolves canonically, so a zeroed duplicate does not strip it",
           dupes, via_copy.id)

# --- launches -----------------------------------------------------------------------------

launch_case("launcher keeps 10000 minus the royalty",
            "resolve_splits omits the launcher because the launcher is the payer",
            chain, remix.id, LAUNCHER)
launch_case("launching your own meme merges into one payee",
            "a duplicate payee address reverts at construction", chain, orig.id, A)
launch_case("a free-to-use meme leaves the launcher everything",
            "no lineage obligation means no splitter is needed at all",
            {free.id: free}, free.id, LAUNCHER)

# The v3 wire contract: memecraft signs payees already resolved at the royalty budget, and a
# consumer composes the launch by addition alone. v2 signed them at 10000 and left the consumer
# rescaling, which disagreed with the reference in 370 of 400 randomised lineages.
for _name, _store, _meme in [("two generations", chain, remix.id), ("three", chain, deep.id)]:
    _roy = _store[_meme].license.royalty_bps
    launch_cases.append({
        "name": f"v3 wire composition — {_name}",
        "why": "signed payees sum to royalty_bps; the launcher is added, never rescaled",
        "store": dump(_store), "meme_id": _meme, "launcher": LAUNCHER,
        "signed_payees_at_royalty_budget": resolve_splits(_meme, _store, budget_bps=_roy),
        "royalty_bps": _roy,
        "expected": resolve_launch_splits(_meme, _store, LAUNCHER),
    })

# --- identity -----------------------------------------------------------------------------

identity_cases = [
    {"name": "ascii", "utf8": "hello world", "expected": meme_id(b"hello world")},
    {"name": "empty", "utf8": "", "expected": meme_id(b"")},
    {"name": "binary", "hex": "89504e470d0a1a0a", "expected": meme_id(bytes.fromhex("89504e470d0a1a0a"))},
]

_raster = bytes([255, 0, 0, 255, 0, 255, 0, 255])
pixel_cases = [
    {"name": "2x1 rgba", "width": 2, "height": 1, "rgba_hex": _raster.hex(),
     "expected": pixel_hash(2, 1, _raster)},
    {"name": "1x2 transposed differs", "width": 1, "height": 2, "rgba_hex": _raster.hex(),
     "expected": pixel_hash(1, 2, _raster)},
]

out = {
    "x420_conformance": "0.1",
    "note": "Generated by scripts/gen_conformance.py. Every implementation must reproduce "
            "these exactly. Do not hand-edit.",
    "identity": identity_cases,
    "pixel_hash": pixel_cases,
    "splits": split_cases,
    "launch_splits": launch_cases,
}

path = Path(__file__).resolve().parent.parent / "conformance" / "vectors.json"
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(out, indent=2, sort_keys=False) + "\n")
print(f"wrote {path.relative_to(Path.cwd())}")
print(f"  identity {len(identity_cases)} · pixel_hash {len(pixel_cases)} · "
      f"splits {len(split_cases)} · launch_splits {len(launch_cases)}")
