# x420 — Cross-App Meme Identity and Lineage

**Status:** draft · **Version:** 0.1 · **Last updated:** 2026-08-17

x420 gives every meme in the CHAD ecosystem one identity that all five apps can compute
independently, plus a lineage record that says who made it, what it came from, and how
value owed to it should be divided.

This document is written for a developer working inside a single repo who cannot see the
other four. Where a decision was made against an existing constraint, the constraint is
stated so the decision can be re-evaluated when the constraint changes.

---

## 1. The problem, stated precisely

Five apps exist. Each one identifies a meme differently, and only one pair of them talks.

| App | Repo | Meme identity today | Content hash | Lineage |
|---|---|---|---|---|
| chadstash | `chad_stash` | `slug` (unique kebab string) + int PK | BLAKE2b-256 (`file_hash`) | none |
| memecraft | `memecraft` | UUID | three different hashes — see §2.3 | `parent_meme_id`, one generation |
| chadpad | `chadpad` | ERC-20 token address | none (`ipfsMetadata` CID only) | none |
| chad smash | `chad-smash` | hardcoded filename string | none | none |
| chad brain | `chad-brain` | Telegram `file_id` | none | none |

**The only existing link** is chad brain → chadstash: `GET {CHADSTASH_API_BASE}/api/search`
authenticated with `X-API-Key`, returning memes keyed by **slug**. Slug is therefore the
incumbent cross-app identifier, and it is the thing x420 has to either adopt or supersede.

Everything else is disconnected. chadpad has no idea a meme it tokenizes came from
memecraft. memecraft's remix graph stops at the app boundary. chad smash's sprites have no
provenance at all — and the repo already carries comments flagging sprite provenance as a
blocker to publishing the game.

---

## 2. Identity

### 2.1 Derivation

```
digest = sha256(rendered_bytes)
id     = "x420:" + hex(digest)[:32]
```

`rendered_bytes` is the exact byte sequence of the published artifact — the PNG/JPEG/GIF as
served, not the source project, not the layer data, not a re-encode.

Any app can compute this from bytes alone with no network call and no shared database. That
independence is the entire point: it is what lets five apps agree without trusting each
other.

**Hash last, and hash server-side.** Two rules follow from "as served", and both have already
been violated once in this ecosystem:

1. **Hash after every mutation of the file.** If a pipeline injects metadata after hashing —
   memecraft appends a `memecraft` tEXt chunk post-export — the recorded digest describes
   bytes nobody will ever download. An artifact cannot contain its own hash, so the hash must
   be taken at the end of the pipeline, over exactly what gets pinned or served.
2. **Never trust a client-supplied digest.** Identity routes payouts, so a forgeable id is a
   forgeable cap table. Hash bytes the server already holds.

**Corollary: the id is not a dedupe key.** Pipelines that embed nonces or timestamps (again,
memecraft: `exportId` and `exportedAt` in its injected chunk) produce different bytes on every
export of the same meme, and therefore different ids. That is correct — they genuinely are
different artifacts — but it means byte-identity can never answer "is this the same meme?"
That question belongs to `phash` and to app-local structural hashes (§2.3).

### 2.2 Three decisions, and why

**Hash the rendered output, not the source layers.** memecraft knows a meme as Konva layers
plus a template; every other app knows it as an image file. Identity must live at the layer
all five apps can observe. memecraft's richer structural data stays valuable — it is what
makes remixing possible — but it cannot be the identity.

**No chain segment in the ID.** An earlier draft used `x420:base:<hash>`. That is wrong.
$CHAD is deployed on three chains:

| Chain | $CHAD address |
|---|---|
| Base | `0xecaF81Eb42cd30014EB44130b89Bcd6d4Ad98B92` |
| Ethereum | `0x2efa572467c50c04a6eed6742196c0d0d287c1bb` |
| Robinhood Chain | `0x4be210cb69afcec533ed6663ced917a1ab59cc87` |

and chadpad is live on both Base (8453) and Robinhood Chain (4663). Chain-scoping the ID
would give one meme three identities. A chain is a property of a *launch*, not of a meme.

**128 bits, not 64.** A truncated hash collision means two unrelated memes sharing a
payout graph. ID width is a one-way door; 32 hex characters costs nothing now and removes
the question permanently.

### 2.3 Exact identity is not similarity — memecraft already proves this

memecraft currently computes **three** different hashes, two of which share a name. This is
the clearest evidence that the ecosystem needs one defined identity.

| Where | Name | What it actually is |
|---|---|---|
| `src/features/editor/lib/export-signature.ts:308` | `sha256` | SHA-256 of the PNG **before** metadata injection — not the served artifact, and not the x420 id |
| `src/features/editor/lib/export-signature.ts:224` | `visualHash` | **dHash** — a 64-bit perceptual hash from a 9×8 grayscale downsample |
| `src/lib/meme-publishing.ts:801` | `visualHash` | SHA-256 of canonicalized `project_data` JSON |

`visualHash` therefore means a perceptual fingerprint in the editor and a structural hash in
the publishing pipeline. They are different value spaces with the same name, and the
publishing pipeline's version is what reaches the `visual_hash` database column and drives
duplicate rejection. Anything that compares the two will be silently wrong.

Note that **none of these three is the x420 id.** The first is the closest, but it is taken
before the `memecraft` tEXt chunk is injected, so it describes bytes that are never served
(§2.1). memecraft must hash the final artifact server-side instead.

**The naming rule this implies:**

- `x420_id` — SHA-256 of rendered bytes. Decides *identity*. Never fuzzy.
- `phash` — perceptual hash. Decides *similarity*. Never identity, never payouts.
- `structure_hash` — memecraft's canonicalized `project_data` hash. Editor-local dedupe only.

A re-encoded JPEG produces a different `x420_id` for a visually identical meme. That is
correct and intended. Detecting that case is `phash`'s job, and its output is a *suggestion
for review*, never an automatic payout decision.

### 2.4 chadstash uses BLAKE2b, not SHA-256

`chad_stash` stores `file_hash` as BLAKE2b-256 and already rejects byte-identical uploads
with a 409. This is a good dedupe mechanism and should not be removed. Add `x420_id` as a
**second, additive column** — do not migrate `file_hash`. Two hashes over the same bytes is
cheap; a migration of a live dedupe path is not.

---

## 3. The record

```jsonc
{
  "x420": "0.1",
  "id": "x420:9f86d081884c7d659a2feaa0c55ad015",
  "content": {
    "uri": "ipfs://…",
    "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "media_type": "image/png",
    "phash": "b2c3d4e5f6071829"
  },
  "parents": [
    { "id": "x420:2c624232cdd221771294dfbb310aca00", "relation": "remix" }
  ],
  "attribution": [
    { "address": "0x…", "role": "creator", "share_bps": 7000 },
    { "address": "0x…", "role": "editor",  "share_bps": 3000 }
  ],
  "license": { "id": "x420-remix-1", "derivatives": true, "royalty_bps": 1500 },
  "provenance": "attested",
  "origin": { "app": "memecraft", "ref": "<uuid>" }
}
```

`attribution` shares are basis points and must sum to 10000 **when the list is non-empty**;
an empty list means nobody is owed (§3.3). `relation` is one of:

| `relation` | Meaning |
|---|---|
| `remix` | built from a specific meme's content |
| `derivative` | a variant of the parent |
| `reaction` | a response referencing the parent |
| `translation` | the parent, restated in another language |
| `template` | the parent used as a **structural format** — taken as a starting layout, then re-captioned or re-assembled |

`template` is deliberately distinct from `remix`. Using a meme as a format is weaker derivation
than remixing a particular meme, and separating them allows a different royalty rate later
without re-deriving any lineage.

**`parents` means derivation, never subject matter.** A meme made *about* something — a token,
a person, an event — is not descended from it. Only put an id in `parents` when the artifact
was actually built from that artifact's content.

This matters because `parents` drives payouts. Recording a subject as a parent inserts it into
the ancestry as a royalty-earning contributor, quietly diverting money to something that
contributed nothing creatively. Associations of the "this meme is about X" kind belong to the
consuming app, keyed on the x420 id — not in the record.

`origin.ref` keeps the originating app's native key (chadstash slug, memecraft UUID,
Telegram `file_id`) so the mapping is reversible without a separate join table.

### 3.1 Provenance tiers

`provenance` is the field that stops backfilled data from lying.

| Value | Meaning | Who can produce it |
|---|---|---|
| `attested` | Lineage observed by the tool at creation time | memecraft (editor knows the parent) |
| `asserted` | Self-declared and wallet-signed, unverified | any app with a connected wallet |
| `unknown` | Provenance genuinely not known | imported memes; backfill of pre-x420 records |

**`unknown` is the majority state of the catalog, not an edge case.** Most memes in chadstash
are imported — classic internet memes whose authors are anonymous and unknowable. Any design
that treats `unknown` as a migration artifact to be cleaned up is wrong about the shape of
the data.

The two graphs are separate, which is what keeps this tractable:

- **memecraft's graph is closed and fully attested.** Its memes descend from its own
  character/template set (`src/config/templates.ts`) and from other memecraft memes. Imported
  memes never enter it.
- **chadstash's catalog is mostly `unknown`.** Imported works with no recoverable authorship.

### 3.1.1 Curation is attributable even when authorship is not

Nobody knows who drew a 2011 wojak. But somebody imported it, tagged it, wrote its use-cases,
ran OCR over it, and rated its quality — and chadstash already records who, as wallet
addresses in `created_by` and `updated_by`.

Imported memes therefore carry attribution with a different role:

```jsonc
{
  "provenance": "unknown",
  "attribution": [{ "address": "0x…", "role": "curator", "share_bps": 10000 }]
}
```

`curator` rather than `creator` is load-bearing. It is honest about what is being
compensated, and it means the record never asserts authorship it cannot support.

**Provenance resolves as the weakest link in the chain.** An `attested` remix of an `unknown`
ancestor has `unknown` lineage overall, because the payout graph is only as trustworthy as
its least-verified edge. Rank `unknown < asserted < attested` and take the minimum across the
ancestry. Consumers gate on the *resolved* value, never on the record's own field.

**`unknown` must never be treated as "original."** This is the single most dangerous
failure mode in the whole migration: if backfilled records get empty `parents`, every legacy
meme silently claims origin status and captures a full share of any downstream allocation.
An empty `parents` array on an `attested` record means "verified original." The same empty
array on an `unknown` record means "we have no idea." Consumers must branch on
`provenance`, not on `parents.length`.

### 3.1.2 Attribution is creator-based, not owner-based

`attribution` addresses are **fixed at publish and never re-resolved**. They record who did
the work, not who currently holds an asset representing it.

This is a deliberate divergence from memecraft's existing NFT royalty, which is owner-based:
`MemeCraftNFT` resolves `parentOwner = _ownerOf(parentTokenId)` at mint time and pays
whoever holds the parent NFT right now. Both mechanisms are correct for what they do, and
they should stay separate:

| | x420 `attribution` | memecraft `parentPayoutAmount` |
|---|---|---|
| Basis | creator — who made it | owner — who holds the NFT |
| Resolved | once, at publish | every mint, via `_ownerOf` |
| Transferable | no | yes, with the NFT |
| Source column | `creator_wallet_address` | `owner_wallet_address` |

Three reasons x420 takes the creator side:

1. **The splitter cannot do otherwise.** `LineageSplitter` is immutable and holds a fixed
   payee array. Owner-based payouts would require resolving `ownerOf()` at release time —
   a different contract with a live trust dependency on an NFT contract that may live on
   another chain from the launch.
2. **Tradeable royalties are the failure mode being avoided.** If lineage income follows the
   NFT, someone can buy into an ancestry's revenue and the creator loses it on sale. That is
   the dynamic that collapsed NFT royalties, reintroduced one layer up.
3. **It is what the claim says.** "The original creator gets paid" has to mean the creator.

memecraft's owner-based mechanism should **not** change. It makes its NFTs carry an income
stream, which is a coherent product decision. The two systems answer different questions and
the ecosystem is better off with both than with a forced merge.

### 3.1.3 What this does not do

**x420 cannot establish first-authorship for content that originated outside the system.** It
records a claim, signed by a wallet, at a timestamp. That is not proof of authorship, and no
mechanism in this document makes it one.

Concretely: take a meme from anywhere on the internet, publish it as an origin claim, and the
record will say you made it. The `phash` check in §3.2 only compares against records already
in the registry, so imported work with no prior record passes cleanly. A holding requirement
does not deter this either — the holder keeps their tokens, so for a meme believed to be
valuable the gate costs nothing but opportunity.

The two guarantees are therefore very different, and must not be described as one:

| Origin | Guarantee | Strength |
|---|---|---|
| Created in memecraft | the editor **observed** the remix edge | strong — cannot be forged after the fact |
| Imported from anywhere | a wallet signed a claim at a time | weak — a timestamped assertion |

This is what the provenance tiers encode, and why resolution takes the weakest link. No
mechanism promotes an import into an attestation.

**The mitigation that would actually bite** is a *slashable bond* on origin claims rather than
a holding requirement, paired with a challenge window before splitter deployment (which is
needed regardless, since the contract cannot be corrected once deployed). A bond has real
expected cost to a thief; a holding gate does not. It requires an adjudicator, which is an
unsolved governance question — chadstash's existing curator roles are the obvious starting
point.

That reframes the problem from "can theft be detected?" (no) to "is theft worth it?" — the
only version that is answerable. The payoff chain is long: someone else must remix the stolen
meme, that remix must be tokenized, and the token must generate fee volume. For most memes
every link fails, while the thief has permanently and publicly claimed authorship of
recognizable work.

**Do not describe x420 as proving provenance.** It provides attested lineage for memes born
inside the ecosystem, and signed, timestamped claims for everything else.

### 3.4 Duplicates: same work, different bytes

`x420_id` deduplicates byte-identical files automatically — same bytes, same id. It does
nothing for the case that matters: **a re-encode, resize, or re-upload of the same work**,
which produces a completely different id (§2.1) and therefore a second, competing record.

Left unhandled, that fragments the lineage graph. A meme that should be one node with many
descendants becomes several nodes each with a few, and the original creator's share is diluted
by the existence of copies they did not make. It is also the mechanism behind the
under-claiming attack in §3.2.

#### `duplicate_of` is equivalence, not derivation

```jsonc
{ "id": "x420:…copy…", "duplicate_of": "x420:…original…" }
```

**A duplicate is not a child**, and the distinction decides who gets paid:

| Modelled as | Result |
|---|---|
| `parents` (derivation) | the re-uploader takes a creator's share; the original keeps only a royalty carve — **copying is rewarded** |
| `duplicate_of` (equivalence) | splits resolve to the canonical record — **launching a copy pays exactly who the original would** |

The second removes the incentive rather than policing the behaviour, which is the same
principle as taxing issuance rather than copying (§1).

Resolution short-circuits: a duplicate's own `parents` and `attribution` are **ignored**.
Otherwise re-uploading with invented lineage would be a way to rewrite who gets paid.

#### The carve rate comes from the canonical record

Subtle and load-bearing. When a parent is itself a duplicate, the royalty rate must be read
from the record it resolves to, never from the duplicate.

Reading it from the duplicate opens a laundering path: re-upload a meme as a duplicate with
`royalty_bps: 0`, remix your own copy, and the original's royalty vanishes while the lineage
still looks well-formed. Resolving the rate canonically closes it — remixing a copy and
remixing the original produce identical splits.

Chains are permitted; cycles among duplicates raise `LineageCycle`, since "which is the
original" would otherwise be unanswerable.

#### Detection stays human

`phash` proposes duplicates; a curator disposes. Perceptual hashes have real false positives —
two different captions over the same template are near-identical by construction — and an
automatic link would misroute payouts on exactly the memes that matter most.

One case is safe to collapse automatically: **same-creator duplicates.** memecraft's exports
are non-deterministic (§2.1), so one user exporting twice yields two ids with identical
attribution. Nothing is at stake in the payout, only catalog tidiness.

Different-claimed-creator duplicates are the adversarial case and always need review.

### 3.3 "Nobody knows who" and "nobody is owed" are different states

Two independent axes, and conflating them misroutes money:

| Axis | Field | Question it answers |
|---|---|---|
| **Provenance** | `provenance` | How confident are we in the *lineage*? |
| **Obligation** | `attribution` + `license.royalty_bps` | Who, if anyone, is *owed*? |

They vary independently:

| State | `provenance` | `attribution` | Meaning |
|---|---|---|---|
| Attributed | `attested` | creator + editors | normal |
| **Unknown creator** | `unknown` | `[{ role: "commons", … }]` | someone is owed; identity unrecovered, share held (§8.1) |
| **Free to use** | any | **`[]` (empty)** | nobody is owed — public domain, waived, or self-dedicated |
| Unknown *and* free | `unknown` | `[]` | provenance unrecoverable *and* no obligation |

**An empty `attribution` list is meaningful, not malformed.** It is the only way to express
"nobody is owed", and the sum-to-10000 rule applies only to non-empty lists. Paired with
`royalty_bps: 0` it means descendants carve nothing either — that combination is
`Meme.is_free_to_use`.

Without this, public domain has no representation. The nearest available encoding — a commons
payee at 10000 bps — routes **the entire creator fee stream to the commons pool for work
nobody was ever owed for**, which is worse than doing nothing: it manufactures an obligation
and then holds funds against a claim that can never legitimately arrive.

#### Consumer rule

`resolve_splits` returns `{}` for a free-to-use meme with no paying ancestors. Consumers must
read empty as **"no lineage obligation"**, not as an error or an empty payout:

- **chadpad:** deploy no splitter and launch normally, so the launcher keeps their own fee
  stream. Deploying a splitter with no payees would revert at construction anyway.
- Resolution stays exact everywhere else — a free-to-use *parent* simply carves nothing, and
  the remaining ancestry still totals 10000.

#### Not yet supported: relation-dependent rates

`relation` (`remix`, `template`, `reaction`, …) is **metadata only** — it does not affect the
carve. A `template` parent and a `remix` parent at the same `royalty_bps` take an identical
share.

§3's note that `template` is "kept distinct so it can carry its own royalty rate" describes an
intended future capability, not current behaviour. Varying rates *per parent* work today, since
each parent carves its own `royalty_bps`; varying them *per relation* does not.

### 3.2 The incentive asymmetry

Self-declared lineage is only half-exploitable, which makes it far more defensible than it
first appears:

- **Over-claiming parents is self-punishing.** Every parent you name carves its
  `royalty_bps` off your own take. Nobody farms fake ancestors.
- **Under-claiming is the real attack.** Reposting someone's meme as your own original
  captures the full 10000 bps.

So only one direction needs defending, and `phash` near-duplicate detection at publish time
is the defense — flag collisions for review rather than auto-linking.

---

## 4. Splits

`resolve_splits()` (see `x420/lineage.py`) walks the ancestry graph and returns
`{address: bps}` summing to exactly 10000. Each parent carves its own `royalty_bps` off the
top, recursively; the remainder is divided among the current meme's `attribution`.

Worked example from the reference store, a three-deep chain:

| Payee | Role | bps |
|---|---|---|
| `0x4444…` | reaction creator | 8500 |
| `0x2222…` | remix creator | 945 |
| `0x3333…` | remix editor | 405 |
| `0x1111…` | original creator | 150 |

Implementation notes that are load-bearing:

- **Cycle guard is required.** Any registry that lets a record name its parent is a graph,
  not a tree. `resolve_splits` raises `LineageCycle` on revisit.
- **Integer division sheds dust.** Basis-point math loses remainder; the largest payee
  absorbs it so the sum is exact at every depth.
- **Deep chains compound.** Each generation carves from gross, so a long lineage can starve
  the newest creator. Capping cumulative ancestral carve is an open question — see §8.

---

## 5. Per-app integration

### 5.1 memecraft — the keystone

memecraft matters more than the other four combined, because **it is the only app that can
produce `attested` lineage.** When a user remixes inside the editor, the tool already knows
the parent; provenance is a byproduct of editing rather than a claim to be verified later.
That is a structural advantage no standalone registry can reproduce.

It is also far further along than expected. Already present:

- `parent_meme_id`, `parent_wallet_address`, `is_remix` on the `memes` table
- EIP-712 signing (`MintAuthorization`) in `contracts/MemeCraftNFT.sol`
- **`parentPayoutAmount`** — it already pays the direct parent owner on mint
- A rule that a parent must be minted before a child remix can mint

So memecraft has shipped a working *one-generation* royalty system. x420 extends it in two
ways: **multi-generational** (the direct parent's ancestors currently get nothing) and
**cross-app** (the graph currently dies at the app boundary).

Changes:
1. Hash the final served artifact server-side at publish and persist it as `x420_id`. Not the
   digest at `export-signature.ts:308` — that predates metadata injection (§2.1).
2. Rename the two colliding `visualHash` identifiers per §2.3.
3. Emit the record on publish, `provenance: "attested"`.

### 5.2 chadpad — allocate via a splitter, do not redeploy

**Constraint:** chadpad is live on Base and Robinhood Chain mainnet and is unaudited.
Redeploying `TokenLauncher` orphans existing deployments and forces a full indexer reindex.
Treat the deployed contracts as immovable.

The original plan — split token *supply* across lineage — is not merely hard here, it is
architecturally incompatible. `ChadToken` mints a fixed 69B supply and `TokenLauncher` puts
**100% of it into a single-sided Uniswap V3 position** whose NFT is minted directly to
`LPLocker` and can never be withdrawn. There is no free supply to allocate, and carving some
out would hand ancestors dumpable tokens, directly undermining the rug-proof property that
is the launchpad's main selling point.

**The fee stream is the correct injection point.** `FeeRouter` streams the creator's share
of swap fees to a single stored address. Two facts from
`packages/contracts/src/FeeRouter.sol` make this work without touching any deployed
contract:

```solidity
/// @notice Creator withdraws their vested fees. Callable by anyone; funds always go to creator.
function claim(uint256 positionId) external nonReentrant {
    if (amountToken  != 0) IERC20(p.token).safeTransfer(p.creator, amountToken);
    if (amountPaired != 0) IERC20(p.pairedToken).safeTransfer(p.creator, amountPaired);
}
```

- `claim()` is **callable by anyone** and always sends to the stored `p.creator`.
- Payouts are **ERC-20 `safeTransfer` only** — no ETH, so no `receive()` requirement.
- `TokenLauncher` only requires `creator != address(0)`; it never assumes an EOA.

Therefore: **deploy an immutable splitter contract holding the resolved x420 splits, and
pass its address as `creator` to `launchToken()`.** Fees stream to the splitter; anyone can
poke it to fan out to the lineage. No contract redeploy, no indexer schema migration, no
change to tokenomics or rug-proofing.

Two consequences to handle in the web app only:

- `token.creator` becomes the splitter address, so "my launches" views must resolve through
  it. The splitter should expose `primaryCreator()`.
- Metadata-edit auth (`metaUpdateMessage` in `packages/web/lib/sig.ts`) verifies a creator
  signature. A contract cannot sign, so verification must check against `primaryCreator()`.
- `initialBuyWeth` sends the creator's atomic buy to `creator` — i.e. the splitter. Either
  set it to zero for lineage launches or have the splitter distribute the token side too.

### 5.3 chadstash — the resolver

chadstash becomes the system of record for x420 records. It is the natural home: it already
has the search infrastructure, SIWE admin auth, and the only existing cross-app API.

1. Add `x420_id` and `phash` columns alongside the existing `file_hash` (§2.4).
2. Backfill all published memes as `provenance: "unknown"` (§3.1).
3. Serve records by `x420_id`, keeping slug as a permanent alias so the existing chad brain
   integration does not break.

### 5.4 chad brain — producer, not just distributor

chad brain generates images via DALL·E (`/image`, `/chad`, `/wojak`), which makes it a meme
*source*, not only a distribution surface. Those images currently have no identity beyond an
ephemeral, platform-specific Telegram `file_id`.

Hash the bytes at generation time and register with `provenance: "asserted"` and the prompt
recorded in `origin`. This is low effort and turns a leak into a lineage root.

### 5.5 chad smash — defer, but note the real hook

chad smash is the weakest v1 candidate: assets are 17 hand-made sprites referenced by
hardcoded filename strings in `src/entities.ts`, with no manifest and no ID field. It is a
fixed cast of wojak archetypes, not a consumer of user-generated memes.

The genuine hook is the reverse of the assumed one. The repo carries comments identifying
**sprite provenance as a blocker to publishing the game** — chad smash needs to prove it has
rights to its art. That is an attribution problem x420 solves directly, and it is a better
reason to integrate than telemetry. Defer to v2, but generate a build-time
`x420-manifest.json` for the sprites when convenient.

---

## 6. Topology

chadstash is the system of record. Base is the notary.

Do **not** put every meme on-chain — most are never tokenized and do not justify the gas.
But once chadpad launches a token against a meme, the record becomes economically
load-bearing and disputes become possible.

**Anchor the record hash on-chain at tokenization, not at creation.** The splitter
constructor is the natural place: it is deployed per-launch and already commits to the
resolved splits. Cheap identity for millions of memes; on-chain guarantees exactly where
money is.

---

## 7. Build order

1. **Shared ID derivation** — one canonical implementation, ported to TS and Python. Nothing
   else works until all five apps compute byte-identical IDs.
2. **chadstash columns + backfill** — everything marked `unknown`.
3. **memecraft persists `x420_id`** — hashed server-side over the served artifact.
4. **Splitter contract + chadpad web integration** — the first point where lineage becomes
   money.
5. **memecraft emits `attested` records** — the graph starts getting richer.
6. **chad brain registers generated images.**
7. **chad smash manifest** — deferred.

Steps 1–4 deliver the value. Steps 5–7 compound it.

---

## 8. Open questions

### 8.1 Resolved: the commons holding address

*Decided 2026-08-18.*

When a token launches against an `unknown`-provenance meme, the ancestral share goes to a
**commons holding address**, split with the meme's curator. Nobody knows who made the artwork,
but the value it carries predates the launcher, so it is neither theirs nor the protocol's to
absorb.

```jsonc
{ "provenance": "unknown",
  "attribution": [
    { "address": "0x…curator…", "role": "curator", "share_bps": 3000 },
    { "address": "0x…commons…", "role": "commons", "share_bps": 7000 }
  ] }
```

The ratio is configuration, not spec.

**The role is `commons`, never `creator` or `originator`.** That address did not make the
meme, and a record must never assert authorship it cannot support — the same rule that stops
empty `parents` from meaning "verified original". `provenance` stays `unknown`.

**It is configuration, not a constant.** Applied once at `LineageSplitter` construction and
therefore forward-only: changing the address or the ratio affects new launches while existing
payee lists stay untouched. Safe to start restrictive.

#### 8.1.1 It is a holding tank, and the accounting already exists

Funds held there are **claimable**: when an admin verifies a meme's real creator, that creator
can collect what accrued against their work.

The obvious objection is that many splitters pay one address, so the balance is pooled and a
later claimant's share looks unknowable. It is not, because two things already on-chain make
per-meme accounting exact:

| Source | What it gives |
|---|---|
| `LineageSplitter.x420Content` (immutable) | which meme this splitter is for |
| `PaidOut(token, account, amount)` | how much it sent to the commons address, and when |

Joining those reconstructs, for any meme, exactly what its unknown creator is owed — per
token, over all time, from chain data alone. No new contract, no memo field, no deposit
bookkeeping. chadpad's indexer already watches splitters.

This is the payoff from anchoring `x420Content` at deployment. Without it, commons deposits
could not be attributed to memes at all, and the holding tank would be a pool with no ledger.

**Be precise about the trust model.** Entitlement is provable from chain data; *payment* is
custodial, since someone controls the address and sends the funds. That is an honest
intermediate. The non-custodial version publishes a merkle root of verified claims and lets
creators withdraw against it — and the accounting above is exactly what would generate that
root, so it is an upgrade rather than a rewrite.

#### 8.1.2 Verification is forward-looking for splitters, backward-looking for the pool

Once an admin verifies a creator, the record gains real attribution and its provenance rises
above `unknown`. But **deployed splitters are immutable and keep paying the commons address**.
So the two directions differ:

- **Future launches** of that meme, or of anything descending from it, pay the creator directly.
- **Past accruals** are claimed from the pool, computed from the events above.

Nothing needs revoking or migrating; the two mechanisms simply cover different periods.

#### 8.1.3 What keeps this defensible

Routing money from unattributed work to an address the team controls is exactly the
uncomfortable case, so the mitigations are not optional:

- **Publish the address** and what happens to the funds.
- **Flag known-author memes as ineligible** for commons treatment. Defensible for anonymous
  folk art, not for a living author — Matt Furie litigated over Pepe. `source_url` and
  `attribution` already exist on the chadstash model.
- **Adjudicating competing claims is unsolved**, and it is the same governance gap as the
  challenge window in §3.1.3. Two people claiming one meme needs a decision procedure that
  does not yet exist.

#### 8.1.4 Adjudicating claims — a direction, not a decision

**Still unsolved.** Recorded so the thinking is not lost, and explicitly not a specification.
Nothing here should be built before a real claim exists; writing the procedure now means
writing it from imagination.

**The problem is smaller than it looks.** Three cases with wildly different frequencies:

| Case | Frequency | Cost |
|---|---|---|
| Nobody ever claims | ~every meme | zero |
| One claimant, settled by research | most claims | minutes |
| Genuinely contested | rare | hard |

Designing for the third before the second has been seen is the trap.

**Filter by money first.** Claims only matter where a balance accrued, and §8.1.1's accounting
already says exactly which memes those are — almost all will be zero. The queue is therefore
"memes with a non-zero commons balance *and* a claimant", which scales with value rather than
with catalog size.

**Ask for possession, not argument.** Research settles many cases — reverse image search for
earliest appearance, KnowYourMeme, original post timestamps, archived threads. But the
strongest evidence is holding something only the creator would have: the layered source file,
a higher-resolution version, the unwatermarked original, a surrounding body of work in the
same style. That converts most disputes into a document request rather than a judgement.

**Publish pending claims on the meme's own page.** A public objection window works — it is
trademark opposition, and silence against a findable notice is meaningful. But nobody watches
a social account, and the people most likely to object are precisely those not following it.
The meme's own page is where someone searching for that meme actually arrives, and it makes
the notice permanent and linkable. Social posts amplify; the page is the record.

**Bias conservative, because the errors are asymmetric.** Approving a wrong claim pays the
wrong person permanently. Rejecting a right one is recoverable — they can return with better
evidence. Slow is cheap; wrong is not.

**Avoid a bond on claims.** It deters spurious claims, but the likely claimant is a
non-crypto artist who drew something a decade ago. A bond is a barrier to exactly the person
the mechanism exists to reach.

### 8.2 Other open questions

- **Compounding carve.** Should cumulative ancestral royalty be capped so deep chains do not
  starve the newest creator? A cap is simple; the right number is not obvious.
- **Template edges.** memecraft memes are built from memecraft's own templates. Should
  template use create a lineage edge crediting the ecosystem? Currently no — it would tax
  every meme — but it is a coherent alternative.
- **Author-set royalty rates.** `royalty_bps` is currently a config default denormalized onto
  each record. Letting creators choose introduces a real tradeoff — a high rate discourages
  others from remixing you, a low one forfeits income — which may be interesting or may just
  be a footgun.

### 8.3 Resolved

- **~~memecraft NFT vs. chadpad token payouts~~** — resolved 2026-08-17: they stay separate,
  deliberately. x420 attribution is creator-based; `parentPayoutAmount` stays owner-based.
  See §3.1.2.
- **Splitter mutability.** Immutable splitters are trustless but cannot fix a wrong lineage.
  Since `unknown`-provenance records will be wrong sometimes, a challenge window before
  deployment may be needed.
- **`x402` payment surfaces.** Sequenced after lineage payouts, not rejected — see §9.

  An earlier draft dismissed x402 wholesale on the grounds that "charging for meme retrieval
  is a weak premise." That reasoning holds for *retrieval* and was wrongly generalised.
  Retrieval and licensing are different products: paying to **see** a meme fights the medium,
  while paying to **use** one commercially, with attribution flowing to its lineage, is a
  thing that cannot exist without x420.
**Base only.** x420 targets Base, alongside x402. chadpad is also live on Robinhood Chain
(4663), and that remains a real constraint on the design — its contracts are deployed there
too, which is part of why they are treated as immovable — but **no x420 work targets Robinhood
Chain.** Splitter deployment there is out of scope rather than pending, and RH coverage is not
a gap to close.

$CHAD's deployment across three chains still matters as the reason x420 ids carry no chain
segment (§2.2). That is an argument about identity, not a commitment to multi-chain support.

---

## 9. Future: x402 licensing (deferred, not rejected)

**Decision, 2026-08-18:** x420 is x402-native by design and ships on Base, but the current
effort builds identity and lineage only. A paid licensing surface is the intended next
initiative, sequenced after lineage payouts prove out on mainnet. Nothing below is in the
current scope; it is recorded so the option stays open and informed.

### The product

Not paid retrieval — paid **licensing**. Memes stay free to see. What is sold is the right to
use one commercially, with the payment split across everyone in its lineage.

This is the only version of "pay for memes" that does not fight the medium. Memes spread
because they are free and frictionless; gating that is self-defeating. But a machine-payable
commercial licence, backed by a provenance record that says exactly who is owed what, is a
product that cannot exist without x420.

### Why the settlement side is nearly free

**`LineageSplitter` is revenue-source agnostic.** It fans out any ERC-20 balance to the
lineage and neither knows nor cares where the money came from, and `releaseMany` already
handles several tokens.

So x402 licence revenue in USDC can settle to *the same splitter* that receives chadpad's WETH
fee stream. One immutable payout contract, two revenue sources, no new settlement
infrastructure:

```
  chadpad launch fees (WETH) ──┐
                               ├──▶  LineageSplitter  ──▶  lineage
  x402 licence payments (USDC) ┘
```

That also gives a stronger answer to "what is x420 for" than launches alone: a meme earns from
tokenization *and* from licensed use, through one contract, split across everyone who
contributed to it.

### What would need building

1. **License semantics.** The record's `license` field exists but is decorative — `id`,
   `derivatives`, `royalty_bps` with no defined terms behind them. Real licence tiers would
   need actual meaning.
2. **A 402-gated endpoint**, most naturally on chadstash as the registry. `app.py` in this
   repo is a working reference: Base Sepolia, USDC, valid payment requirements returned in the
   `payment-required` header.
3. **Settlement routing** to the meme's splitter, which is where the work is smallest.

### The open question

**Who is the first paying consumer?** The mechanism is sound and mostly built; the demand is
speculative. Agents that post to social need images with clean rights, which is a plausible
buyer — but plausible is not proven. Answer this before building, not after.
