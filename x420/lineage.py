from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

BPS_TOTAL = 10_000

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
    sha256: Sha256
    media_type: str
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

    def model_post_init(self, _context: object) -> None:
        total = sum(p.share_bps for p in self.attribution)
        if total != BPS_TOTAL:
            raise ValueError(f"attribution must sum to {BPS_TOTAL} bps, got {total}")

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
    try:
        meme = store[meme_id]
    except KeyError:
        raise UnknownMeme(meme_id) from None

    seen = _seen | {meme_id}
    payouts: defaultdict[str, int] = defaultdict(int)
    remaining = budget_bps

    for parent in meme.parents:
        ancestor = store.get(parent.id)
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

    return dict(payouts)


def ancestry(meme_id: str, store: dict[str, Meme]) -> list[str]:
    """Ancestor ids, nearest first, breadth-first, deduplicated."""
    seen: dict[str, None] = {}
    frontier = [p.id for p in store[meme_id].parents]
    while frontier:
        current = frontier.pop(0)
        if current in seen:
            continue
        seen[current] = None
        frontier.extend(p.id for p in store[current].parents)
    return list(seen)
