from __future__ import annotations

from collections import defaultdict, deque
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

BPS_TOTAL = 10_000

# Resolution normally terminates on its own: each generation carves `royalty_bps` from the
# remainder, so a distant ancestor's share reaches zero and `carve == 0` stops the walk. How
# deep that goes is set by the RATE, not the chain length — 5000 bps stops after ~14
# generations, 9900 after ~517. Above roughly 9990 the natural bound exceeds Python's stack,
# and an attacker-supplied record could turn a request into a RecursionError, i.e. a 500.
#
# So the depth is capped explicitly and raises a defined error instead. 64 is well past the
# point of usefulness: a linear chain yields at most one payee per generation, and
# LineageSplitter accepts only 32, so anything deeper is unlaunchable regardless. It also
# matches the limit memecraft already applies in its splits route.
MAX_LINEAGE_DEPTH = 64

Address = Annotated[str, StringConstraints(pattern=r"^0x[a-fA-F0-9]{40}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
MemeId = Annotated[str, StringConstraints(pattern=r"^x420:[a-f0-9]{32}$")]


class Relation(StrEnum):
    REMIX = "remix"
    DERIVATIVE = "derivative"
    REACTION = "reaction"
    TRANSLATION = "translation"
    # Used as a structural format — an existing meme taken as a starting layout, then
    # re-captioned or re-assembled. Weaker derivation than a remix of a specific meme, and
    # kept distinct so it can carry its own royalty rate without re-deriving lineage.
    TEMPLATE = "template"


class Provenance(StrEnum):
    """How much the lineage on a record can be trusted. See SPEC.md §3.1."""

    ATTESTED = "attested"
    ASSERTED = "asserted"
    UNKNOWN = "unknown"


class Parent(BaseModel):
    id: MemeId
    relation: Relation


class Role(StrEnum):
    """What a payee is being compensated for.

    `commons` is the holding address for work whose author cannot be identified. It must
    never be recorded as `creator` — that would assert authorship the record cannot support,
    the same error as reading empty `parents` as "verified original". See SPEC.md §8.1.
    """

    CREATOR = "creator"
    EDITOR = "editor"
    CURATOR = "curator"
    COMMONS = "commons"


class Payee(BaseModel):
    address: Address
    # Free-form rather than the Role enum: apps may carry roles this reference does not know
    # about, and an unrecognised role must not make a record unparseable. Role never affects
    # split arithmetic — only who is credited for what.
    role: str
    share_bps: int = Field(ge=1, le=BPS_TOTAL)


class License(BaseModel):
    id: str
    derivatives: bool
    royalty_bps: int = Field(ge=0, le=BPS_TOTAL)


class Content(BaseModel):
    uri: str
    # Of the file as served. Decides identity.
    sha256: Sha256
    media_type: str
    # Of the decoded raster (SPEC §3.4). Exact, but blind to the file wrapper — an equal
    # `pixel_hash` with a differing `sha256` is the same image re-encoded, and is safe to link
    # as a duplicate without review.
    pixel_hash: Sha256 | None = None
    # Perceptual. Suggests similarity; never decides identity or payouts.
    phash: str | None = None


class Origin(BaseModel):
    """The producing app and its native key, so the mapping stays reversible."""

    app: str
    ref: str | None = None


class Meme(BaseModel):
    x420: str = "0.1"
    id: MemeId
    content: Content
    parents: list[Parent] = Field(default_factory=list)
    attribution: list[Payee]
    license: License
    provenance: Provenance = Provenance.ASSERTED
    origin: Origin | None = None
    # The canonical record for the same underlying work, when this artifact is a re-encode,
    # resize, or re-upload of one already registered.
    #
    # This is EQUIVALENCE, not derivation, and the distinction is load-bearing. A duplicate is
    # not a child: modelling it as a parent edge would hand the copier a creator's share and
    # leave the original with only a royalty carve, which rewards re-uploading. Resolving to
    # the canonical record instead means launching a token on a copy pays exactly who the
    # original would have paid, removing the incentive entirely. See SPEC.md §3.4.
    duplicate_of: MemeId | None = None

    def model_post_init(self, _context: object) -> None:
        # An EMPTY attribution list is meaningful, not a mistake: it means nobody is owed —
        # public domain, waived, or otherwise free to use. That is a different state from
        # "someone is owed but we cannot identify them", which is `unknown` provenance with a
        # commons payee. Conflating the two routes money to the commons pool for work that was
        # never owed to anyone. See SPEC.md §3.3.
        if not self.attribution:
            return
        total = sum(p.share_bps for p in self.attribution)
        if total != BPS_TOTAL:
            raise ValueError(f"attribution must sum to {BPS_TOTAL} bps, got {total}")

    @property
    def is_free_to_use(self) -> bool:
        """Nobody is owed for this meme itself, and descendants carve nothing from it."""
        return not self.attribution and self.license.royalty_bps == 0

    @property
    def is_verified_original(self) -> bool:
        """True only when the absence of parents is a claim someone stands behind.

        Empty `parents` on an `unknown` record means provenance was never captured, not
        that the meme is an origin. Conflating the two lets every backfilled record claim
        full allocation.
        """
        return not self.parents and self.provenance is not Provenance.UNKNOWN


class UnknownMeme(KeyError):
    pass


class LineageCycle(ValueError):
    pass


class LineageTooDeep(ValueError):
    """Raised instead of exhausting the stack. A defined refusal beats a RecursionError,
    which surfaces as a 500 on a request path rather than a rejected record."""


def resolve_splits(
    meme_id: str,
    store: dict[str, Meme],
    *,
    budget_bps: int = BPS_TOTAL,
    _seen: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """Distribute budget_bps across every address owed a share of one payment.

    Each parent carves its own license.royalty_bps off the top, recursively; whatever
    survives the carve is split among this meme's own attribution.
    """
    if meme_id in _seen:
        raise LineageCycle(f"lineage cycle through {meme_id}")
    # `_seen` accumulates along one path rather than across the whole graph, so its size is
    # the current depth even when the ancestry branches.
    if len(_seen) >= MAX_LINEAGE_DEPTH:
        raise LineageTooDeep(f"ancestry deeper than {MAX_LINEAGE_DEPTH} at {meme_id}")
    try:
        meme = store[meme_id]
    except KeyError:
        raise UnknownMeme(meme_id) from None

    seen = _seen | {meme_id}

    # A duplicate short-circuits everything: it is the same work, so its payouts and its
    # ancestry are the canonical record's. Any parents or attribution declared on the
    # duplicate itself are ignored — otherwise re-uploading with invented lineage would be a
    # way to rewrite who gets paid.
    if meme.duplicate_of is not None:
        if meme.duplicate_of not in store:
            raise UnknownMeme(meme.duplicate_of)
        return resolve_splits(meme.duplicate_of, store, budget_bps=budget_bps, _seen=seen)
    payouts: defaultdict[str, int] = defaultdict(int)
    remaining = budget_bps

    for parent in meme.parents:
        # Take the carve RATE from the canonical record, not from whatever the named parent
        # says. Otherwise re-uploading a meme as a duplicate with `royalty_bps: 0` and then
        # remixing that copy would strip the original's royalty while still looking like a
        # well-formed lineage.
        ancestor = store.get(canonical_id(parent.id, store))
        if ancestor is None:
            raise UnknownMeme(parent.id)
        carve = min(budget_bps * ancestor.license.royalty_bps // BPS_TOTAL, remaining)
        if carve == 0:
            continue
        for address, bps in resolve_splits(
            parent.id, store, budget_bps=carve, _seen=seen
        ).items():
            payouts[address] += bps
        remaining -= carve

    for payee in meme.attribution:
        payouts[payee.address] += remaining * payee.share_bps // BPS_TOTAL

    # Integer division sheds dust; the largest payee absorbs it so splits stay exact. Ties
    # break on address so two implementations cannot disagree about who gets the remainder —
    # `max()` alone would resolve ties by insertion order, which is not portable.
    dust = budget_bps - sum(payouts.values())
    if dust and payouts:
        absorber = min(payouts, key=lambda a: (-payouts[a], a))
        payouts[absorber] += dust

    # Drop payees whose resolved share rounded to nothing. A minority payee — a 1-bps letterer,
    # say — receives zero once the budget is small enough, which happens naturally deep in an
    # ancestry. They are owed nothing, and `LineageSplitter` rejects a zero share at
    # construction, so leaving them in turns a resolvable lineage into a launch that reverts.
    # Dust has already been assigned above, so removing zeroes cannot change the total.
    return {address: bps for address, bps in payouts.items() if bps}


def resolve_launch_splits(
    meme_id: str, store: dict[str, Meme], launcher: str
) -> dict[str, int]:
    """The COMPLETE payee list for a tokenization — the launcher plus the meme's lineage.

    `resolve_splits` answers a narrower question: who is *owed* a share of one payment. The
    launcher is the payer, so they never appear in it. A consumer that treats that owed-set as
    the whole payee list hands the launcher's entire fee stream to someone else, which makes
    launching another creator's meme pure altruism and kills the behaviour the ecosystem
    exists to produce.

    `license.royalty_bps` therefore does double duty, and both readings are needed:

      * within `resolve_splits` — what a PARENT carves from a descendant's owed pool;
      * here — what a LAUNCHER owes the meme's lineage.

    So a 2000-bps meme means the launcher keeps 8000 and the lineage divides 2000 among
    itself. Remixing compounds naturally: launch on a remix of a 2000-bps original and the
    remixer takes 1600 while the original takes 400.

    Totals are exact. `resolve_splits` already returns precisely its budget, so the launcher's
    remainder plus the lineage is always BPS_TOTAL.
    """
    canonical = store.get(canonical_id(meme_id, store))
    if canonical is None:
        raise UnknownMeme(meme_id)

    royalty = canonical.license.royalty_bps
    payouts: dict[str, int] = {}

    if royalty:
        payouts.update(resolve_splits(meme_id, store, budget_bps=royalty))

    # Merged rather than assigned, so launching your own meme collapses to a single payee
    # instead of listing the same address twice — which the splitter would reject.
    keep = BPS_TOTAL - royalty
    if keep:
        payouts[launcher] = payouts.get(launcher, 0) + keep

    return {address: bps for address, bps in payouts.items() if bps}


def canonical_id(meme_id: str, store: dict[str, Meme]) -> str:
    """Follow `duplicate_of` to the record that actually owns this work.

    Chains are permitted — a duplicate of a duplicate — but a cycle among them would make
    "which is the original" unanswerable, so it raises rather than picking arbitrarily.
    """
    seen: set[str] = set()
    current = meme_id
    while True:
        if current in seen:
            raise LineageCycle(f"duplicate cycle through {current}")
        # Bounded for the same reason as ancestry: a long chain of records each marked a
        # duplicate of the last is cheap to author and costly to follow.
        if len(seen) >= MAX_LINEAGE_DEPTH:
            raise LineageTooDeep(f"duplicate chain longer than {MAX_LINEAGE_DEPTH}")
        seen.add(current)
        try:
            meme = store[current]
        except KeyError:
            raise UnknownMeme(current) from None
        if meme.duplicate_of is None:
            return current
        current = meme.duplicate_of


def ancestry(meme_id: str, store: dict[str, Meme]) -> list[str]:
    """Ancestor ids, nearest first, breadth-first, deduplicated."""
    seen: dict[str, None] = {}
    # deque, not a list: list.pop(0) is O(n), which makes a breadth-first walk quadratic in
    # the number of ancestors.
    frontier = deque(p.id for p in store[meme_id].parents)
    while frontier:
        current = frontier.popleft()
        if current in seen:
            continue
        seen[current] = None
        frontier.extend(p.id for p in store[current].parents)
    return list(seen)
