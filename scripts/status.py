#!/usr/bin/env python3
"""Report what has actually landed across the five CHAD repos.

Cross-repo status kept in prose or in conversation drifts, and the failure is silent: B1 and
B2 were both believed complete while untouched in both repos. Every check here is a predicate
over real files, so the answer is observed rather than remembered.

Usage:
    python3 scripts/status.py            # all phases
    python3 scripts/status.py --blockers # only what gates mainnet

Repo locations override via env: X420_DIR, MEMECRAFT_DIR, CHADSTASH_DIR, CHADPAD_DIR,
CHADBRAIN_DIR, CHADSMASH_DIR.

Exit code is non-zero if any mainnet blocker is unmet.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPOS = {
    "x420": Path(os.environ.get("X420_DIR", "~/PycharmProjects/x420")).expanduser(),
    "memecraft": Path(os.environ.get("MEMECRAFT_DIR", "~/PycharmProjects/memecraft")).expanduser(),
    "chadstash": Path(os.environ.get("CHADSTASH_DIR", "~/PycharmProjects/chad_stash")).expanduser(),
    "chadpad": Path(os.environ.get("CHADPAD_DIR", "~/PycharmProjects/chadpad")).expanduser(),
    "chadbrain": Path(os.environ.get("CHADBRAIN_DIR", "~/PycharmProjects/chad-brain")).expanduser(),
    "chadsmash": Path(os.environ.get("CHADSMASH_DIR", "~/PycharmProjects/chad-smash")).expanduser(),
}


@dataclass(frozen=True)
class Check:
    id: str
    phase: str
    repo: str
    what: str
    glob: str
    pattern: str
    # True  → the pattern must appear somewhere in the matched files
    # False → the pattern must appear nowhere (used for "stop doing X" milestones)
    want: bool = True
    blocker: bool = False
    hint: str = ""


CHECKS = [
    # ---- Phase 1: the demo path -------------------------------------------------------
    Check("M1", "phase 1", "memecraft", "persists x420_id at publish",
          "src/lib/meme-publishing.ts", r"x420_id"),
    Check("M1b", "phase 1", "memecraft", "derives the id from served bytes",
          "src/lib/x420.ts", r"x420IdFromRenderedBytes"),
    Check("M2", "phase 1", "memecraft", "serves resolved lineage splits",
          "src/app/api/x420/**/splits/route.ts", r"resolveSplits"),
    Check("C1", "phase 1", "chadpad", "deploys a splitter in the launch flow",
          "packages/web/app/CreateToken.tsx", r"deployLineageSplitter"),
    Check("C2", "phase 1", "chadpad", "resolves creator to the human at index time",
          "packages/indexer/src/lineage.ts", r"primaryCreator"),
    Check("C3", "phase 1", "chadpad", "gates launches on provenance",
          "packages/web/lib/x420.ts", r"LAUNCHABLE_PROVENANCE|provenance"),
    Check("C4", "phase 1", "chadpad", "indexes the splitter address",
          "packages/indexer/ponder.schema.ts", r"splitter"),

    # ---- Mainnet blockers -------------------------------------------------------------
    Check("B1a", "blocker", "memecraft", "persists the full SHA-256 (content_sha256)",
          "src/lib/*.ts", r"content_sha256", blocker=True,
          hint="schema + publish-path write; see docs/X420.md Task 2c"),
    Check("B1b", "blocker", "memecraft", "returns content_sha256 from the splits endpoint",
          "src/app/api/x420/**/splits/route.ts", r"content_sha256", blocker=True,
          hint="64 lowercase hex, no 0x prefix"),
    Check("B1c", "blocker", "chadpad", "no longer deploys zero anchors",
          "packages/web/app/CreateToken.tsx", r"UNSET_ANCHOR", want=False, blocker=True,
          hint="splitters are immutable — every zero anchor is permanent"),
    Check("B2a", "blocker", "memecraft", "signs the splits response",
          "src/app/api/x420/**/splits/route.ts", r"signature|signTypedData", blocker=True,
          hint="chadpad trusts this response to set an immutable payee list"),
    Check("B2b", "blocker", "chadpad", "verifies the splits signature",
          "packages/web/lib/x420.ts", r"verifyTypedData|verifyMessage", blocker=True),
    Check("B3", "blocker", "chadpad", "tests the x420 integration path",
          "packages/web/**/*x420*.test.ts", r".", blocker=True,
          hint="lib/x420.ts and lib/lineage.ts decide who gets paid, and are untested"),

    # ---- Shared implementation --------------------------------------------------------
    Check("SH1", "shared", "x420", "publishes conformance vectors",
          "conformance/*.json", r"x420_conformance"),
    Check("SH1b", "shared", "x420", "is installable as a package",
          "pyproject.toml", r"name = \"x420\""),
    # Vendoring is what let chadstash drift four changes behind, including duplicate
    # resolution — its copy paid a re-uploader instead of the original.
    Check("SH1c", "shared", "chadstash", "imports x420 rather than vendoring it",
          "backend/app/x420/lineage.py", r"def resolve_splits", want=False),
    # Was "ships a TypeScript package". A package prevents drift; the vectors catch it, which
    # is nearly all the value for a fraction of the work — and it was the *absence* of vector
    # runs, not the vendoring, that let chadstash's copy go four changes behind unnoticed.
    Check("SH2", "shared", "memecraft", "reproduces the conformance vectors",
          "src/**/*x420*.test.ts", r"vectors|conformance"),
    Check("SH3", "shared", "chadpad", "tests the python->solidity handoff",
          "packages/contracts/test/X420Handoff.t.sol", r"resolvedSplitsDeploy"),

    # ---- Phase 3: registry ------------------------------------------------------------
    Check("S1", "phase 3", "chadstash", "has an x420_id column",
          "backend/app/models.py", r"x420_id"),
    Check("S2", "phase 3", "chadstash", "has a phash column",
          "backend/app/models.py", r"phash"),
    Check("S2b", "phase 3", "chadstash", "has a provenance column",
          "backend/app/models.py", r"provenance"),
    # Globs the package, not one file: chadstash put the derivation in app/x420/registry.py
    # and called it from services.py, which a services-only check reported as missing work.
    Check("S2c", "phase 3", "chadstash", "computes x420_id at ingest",
          "backend/app/**/*.py", r"apply_x420_fields|content_digest"),
    Check("S3", "phase 3", "chadstash", "serves the record API",
          "backend/app/api/routes/*.py", r"x420"),
    Check("M4", "phase 3", "memecraft", "registers records with chadstash",
          "src/lib/*.ts", r"chadstash|CHADSTASH"),

    # ---- Phase 4 ----------------------------------------------------------------------
    Check("BR1", "phase 4", "chadbrain", "registers generated images",
          "**/*.py", r"x420"),
    Check("SM1", "phase 4", "chadsmash", "ships a sprite manifest",
          "public/x420-manifest.json", r"."),
]

PASS, FAIL, SKIP = "PASS", "FAIL", "n/a"

# Vendored and generated trees produce false positives that are hard to spot: a `**/*.py` scan
# of chad-brain matched "x420" inside a hex table in a bundled copy of `idna`, reporting an
# integration that did not exist.
# Note "lib" is deliberately absent: it is a real source directory in both memecraft
# (`src/lib`) and chadpad (`packages/web/lib`). Foundry's vendored deps are named explicitly
# instead, since excluding "lib" wholesale silently blanks the checks that matter most.
EXCLUDED = {
    ".venv", "venv", "node_modules", ".next", ".git", "__pycache__", "dist", "build",
    "out", "cache", "artifacts", "broadcast", "site-packages", ".ponder",
    "forge-std", "openzeppelin-contracts",
}


def _vendored(path: Path, root: Path) -> bool:
    return any(part in EXCLUDED for part in path.relative_to(root).parts)


def evaluate(check: Check) -> tuple[str, str]:
    root = REPOS.get(check.repo)
    if root is None or not root.is_dir():
        return SKIP, f"{check.repo} not found"

    matches = [
        p for p in root.glob(check.glob) if p.is_file() and not _vendored(p, root)
    ]
    if not matches:
        # An absent file satisfies a "must not appear" check and fails a "must appear" one.
        return (PASS, "") if not check.want else (FAIL, "no matching file")

    rx = re.compile(check.pattern)
    hits = [p for p in matches if rx.search(p.read_text(errors="ignore"))]

    if check.want:
        return (PASS, "") if hits else (FAIL, "pattern absent")
    return (FAIL, f"still present in {hits[0].name}") if hits else (PASS, "")


def fixture_drift() -> str | None:
    """The Solidity handoff fixture is generated here and vendored into chadpad, because
    Foundry sandboxes reads to its own project. Two copies drift, so compare them."""
    out = []
    for label, src_rel, dst_repo, dst_rel in [
        ("solidity fixture", "conformance/solidity_fixtures.json",
         "chadpad", "packages/contracts/test/fixtures/x420_splits.json"),
        ("conformance vectors", "conformance/vectors.json",
         "memecraft", "src/lib/__fixtures__/x420_vectors.json"),
    ]:
        src, dst = REPOS["x420"] / src_rel, REPOS[dst_repo] / dst_rel
        if not src.is_file():
            out.append(f"{label}: source missing")
        elif not dst.is_file():
            out.append(f"{label}: not yet vendored into {dst_repo}")
        elif src.read_text() != dst.read_text():
            out.append(f"{label}: {dst_repo}'s copy is STALE")
    return "; ".join(out) or None


def repo_head(root: Path) -> str:
    """Short SHA and subject of the checked-out commit, for spotting a stale path.

    Reading a moved repo's old location once produced a confidently wrong report that every
    blocker was unmet, when two had shipped. Printing what was actually inspected makes that
    failure visible instead of silent.
    """
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return "not a git repo"
    ref = head.read_text().strip()
    if ref.startswith("ref: "):
        target = root / ".git" / ref[5:]
        sha = target.read_text().strip() if target.is_file() else "?"
        return f"{sha[:8]} ({ref[5:].rsplit('/', 1)[-1]})"
    return ref[:8]


def print_repos() -> None:
    print("\n  INSPECTING")
    for name, root in REPOS.items():
        if root.is_dir():
            print(f"    {name:<10} {repo_head(root):<24} {root}")
        else:
            print(f"    {name:<10} {'MISSING':<24} {root}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blockers", action="store_true", help="only mainnet blockers")
    parser.add_argument("--quiet", action="store_true", help="skip the repo header")
    args = parser.parse_args()

    if not args.quiet:
        print_repos()

    checks = [c for c in CHECKS if c.blocker] if args.blockers else CHECKS
    results = [(c, *evaluate(c)) for c in checks]

    width = max(len(f"{c.repo} {c.what}") for c, _, _ in results)
    current_phase = None
    failed_blockers = 0

    for check, status, note in results:
        if check.phase != current_phase:
            current_phase = check.phase
            print(f"\n  {current_phase.upper()}")
        label = f"{check.repo} {check.what}".ljust(width)
        mark = {PASS: "  ok ", FAIL: "MISS ", SKIP: "  -- "}[status]
        detail = f"  ({note})" if note else ""
        print(f"  {mark} {check.id:<4} {label}{detail}")
        if status == FAIL and check.blocker:
            failed_blockers += 1
            if check.hint:
                print(f"        {' ' * 4} └─ {check.hint}")

    drift = fixture_drift()
    if drift and not args.blockers:
        print(f"\n  !! vendored fixtures — {drift}")
        print("     regenerate with scripts/gen_conformance.py, then copy into the consumer")

    done = sum(1 for _, s, _ in results if s == PASS)
    print(f"\n  {done}/{len(results)} checks passing")

    if failed_blockers:
        print(f"  {failed_blockers} mainnet blocker(s) unmet — do not launch lineage on mainnet\n")
        return 1
    print("  no outstanding mainnet blockers\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
