"""A three-deep lineage chain used to exercise split resolution.

Ids are derived from the content digests rather than written by hand, so the example
cannot drift from the derivation rule in identity.py.
"""

from __future__ import annotations

from .identity import meme_id_from_digest
from .lineage import Content, License, Meme, Origin, Parent, Provenance

ORIGINAL_SHA = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
REMIX_SHA = "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3"
REACTION_SHA = "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a"

ORIGINAL = Meme(
    id=meme_id_from_digest(ORIGINAL_SHA),
    content=Content(
        uri="ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi",
        sha256=ORIGINAL_SHA,
        media_type="image/png",
    ),
    attribution=[
        {"address": "0x1111111111111111111111111111111111111111", "role": "creator", "share_bps": 10_000}
    ],
    license=License(id="x420-remix-1", derivatives=True, royalty_bps=1_000),
    provenance=Provenance.ATTESTED,
    origin=Origin(app="memecraft", ref="6b1f9c2a-0000-4000-8000-000000000001"),
)

REMIX = Meme(
    id=meme_id_from_digest(REMIX_SHA),
    content=Content(
        uri="ipfs://bafybeihdwdcefgh4dqkjv67uzcmw7ojee6xedzdetojuzjevtenxquvyku",
        sha256=REMIX_SHA,
        media_type="image/png",
    ),
    parents=[Parent(id=ORIGINAL.id, relation="remix")],
    attribution=[
        {"address": "0x2222222222222222222222222222222222222222", "role": "creator", "share_bps": 7_000},
        {"address": "0x3333333333333333333333333333333333333333", "role": "editor", "share_bps": 3_000},
    ],
    license=License(id="x420-remix-1", derivatives=True, royalty_bps=1_500),
    provenance=Provenance.ATTESTED,
    origin=Origin(app="memecraft", ref="6b1f9c2a-0000-4000-8000-000000000002"),
)

REACTION = Meme(
    id=meme_id_from_digest(REACTION_SHA),
    content=Content(
        uri="ipfs://bafybeiczsscdsbs7ffqz55asqdf3smv6klcw3gofszvwlyarci47bgf354",
        sha256=REACTION_SHA,
        media_type="image/gif",
    ),
    parents=[Parent(id=REMIX.id, relation="reaction")],
    attribution=[
        {"address": "0x4444444444444444444444444444444444444444", "role": "creator", "share_bps": 10_000}
    ],
    license=License(id="x420-remix-1", derivatives=True, royalty_bps=2_000),
    provenance=Provenance.ASSERTED,
    origin=Origin(app="chad-brain", ref="AgACAgEAAxkBAAIB"),
)

MEMES: dict[str, Meme] = {m.id: m for m in (ORIGINAL, REMIX, REACTION)}
