# x420 Architecture

**Status:** draft · **Last updated:** 2026-08-17 · **Spec:** [`SPEC.md`](./SPEC.md)

How five independently-built apps become one system, and what x420 has to be for that to
work.

**For what the system is ultimately *for*, read [§12](#12-target-end-state--the-product-loop)
first.** Sections 1–11 describe mechanism; §12 describes the product loop that mechanism
serves, and is the thing every sequencing decision should be checked against.

---

## 1. What x420 actually is

"A standard" is too vague to build against. x420 is three things, and conflating them is what
makes the design feel like fluff:

| Layer | What it is | Where it lives |
|---|---|---|
| **Identity** | `sha256(served_bytes)` → `x420:<32 hex>` | a pure function, duplicated in every app |
| **Record** | identity + lineage + attribution + license + provenance | JSON, pinned to IPFS, indexed by chadstash |
| **Settlement** | lineage resolved into addresses that receive money | `LineageSplitter` on Base |

Identity is worthless alone — plenty of things hash files. Settlement is the payoff. The
record is what carries meaning between them.

## 2. Roles

Each app has exactly one primary role. Where an app has two, the second is explicitly
secondary so it never becomes a second source of truth.

| App | Role | Produces | Consumes |
|---|---|---|---|
| **memecraft** | Producer | `attested` records | records (as remix parents) |
| **chad brain** | Producer + surface | `asserted` records | records (search, posting) |
| **chadstash** | Registry | index, resolution | records from all producers |
| **chadpad** | Settlement | launches, splitters | resolved splits |
| **chad smash** | Consumer | usage signal *(v2)* | records (as assets) |
| **$CHAD** | Reserve asset | — | — |

**memecraft is the only source of `attested` lineage.** The editor observes the parent edge
at creation time; nothing else in the ecosystem can produce that, and no amount of after-the-
fact analysis reconstructs it.

## 3. Topology: star, not mesh

Today's integrations are ad hoc point-to-point — chad brain calls chadstash by slug, chadpad
is being wired to call memecraft directly. Five apps integrating pairwise is twenty edges and
no single source of truth.

**Every app integrates with chadstash. No app integrates with another app.**

```
   memecraft ──┐                    ┌── chadpad
               ├──▶  chadstash  ◀───┤
  chad brain ──┘    (registry)      └── chad smash
```

The direct memecraft → chadpad coupling being built for the demo is **transitional**. It is
the right shortcut to get the video made; it is not the architecture. Once chadstash resolves
records, chadpad reads from chadstash and memecraft's `/api/x420/{id}/splits` becomes an
internal detail or goes away.

### Why chadstash is not a single point of failure

A central registry is normally a liability. Three properties keep it from being one:

1. **Records are content-addressed.** The record JSON is pinned to IPFS alongside the image.
   chadstash indexes it; it does not own it. If chadstash disappears, every record still
   exists and the index can be rebuilt.
2. **Records are signed.** Consumers verify producer signatures directly, so chadstash is a
   *directory*, not an *authority*. A compromised registry cannot forge a payout graph.
3. **Money is anchored on-chain.** At tokenization the splitter commits to the record hash.
   Disputes about a live launch never depend on the registry being available or honest.

This is what resolves the trust-boundary problem currently sitting in the chadpad
integration: chadpad does not trust an HTTP response, it verifies a signature.

## 4. Layers

```
  Settlement    LineageSplitter · FeeRouter · (MemeCraftNFT)      ← money
  ─────────────────────────────────────────────────────────────
  Registry      chadstash index · IPFS record pins               ← resolution
  ─────────────────────────────────────────────────────────────
  Record        x420 JSON: lineage, attribution, license          ← meaning
  ─────────────────────────────────────────────────────────────
  Identity      sha256(served_bytes)                              ← agreement
```

Each layer depends only on the one below. Identity needs no network. The record needs no
chain. Settlement needs no registry at claim time.

## 5. The shared library is the actual glue

Split resolution must produce **byte-identical results** in Python (chadstash, chad brain) and
TypeScript (memecraft, chadpad, chad smash). It currently exists twice, and the two copies
have already diverged once: the reference used `max()` for dust assignment, which resolves
ties by insertion order, while the TS port sorted by address. Same input, different payee.

That bug is the argument. Two implementations of a payout rule is a liability, not redundancy.

**Publish two packages from this repo:**

- `x420` (Python) — chadstash, chad brain
- `@chad/x420` (TypeScript) — memecraft, chadpad, chad smash

Both exporting exactly: `memeId()`, `resolveSplits()`, `resolveProvenance()`, `ancestry()`,
and the record types. Shared conformance vectors — a fixture file of inputs and expected
outputs that both test suites run — so divergence fails CI rather than misrouting money.

## 6. Flows

### 6.1 Create — memecraft

```
edit/remix → publish
  1. server renders final artifact, pins image to IPFS
  2. x420_id = sha256(served bytes)              ← after all mutation (SPEC §2.1)
  3. build record: parents from editor, attribution = creator,
     license = config default, provenance = attested
  4. creator signs record (EIP-712); memecraft co-signs as attestor
  5. pin record to IPFS
  6. POST record to chadstash
  7. (optional) mint NFT — see §7
```

### 6.2 Ingest — chad brain

Generated (`/image`, `/chad`, `/wojak`) and uploaded images: hash bytes, record with
`provenance: "asserted"`, prompt retained in `origin`, bot key attests, register.

### 6.3 Import — chadstash

Enrichment pipeline: hash bytes, `provenance: "unknown"`, attribution `role: "curator"` from
`created_by`. Never `creator`, never empty-parents-as-original.

### 6.4 Tokenize — chadpad

```
  1. fetch record + resolved splits from chadstash
  2. verify producer signature      ← does not trust the registry
  3. gate on resolved provenance    ← weakest link across the ancestry
  4. deploy LineageSplitter(primaryCreator, x420Content, x420Record, payees)
  5. launchToken(..., creator = splitter, ...)
```

### 6.5 Distribute — permissionless

```
  swaps → LPLocker → FeeRouter.claim(positionId) → splitter
                   → splitter.release(token)     → ancestry
```

Both calls are callable by anyone. Nobody can withhold a payout by declining to act.

## 7. Publishing and minting must decouple

**Today publishing requires minting.** `isMinted` is hardcoded `true` at
`meme-publishing.ts:1204`, and the only path to `status: "published"` runs through
`verifiedMint`. Every meme that exists in memecraft cost $CHAD plus gas.

That throttles the one thing x420 needs. Lineage is valuable in proportion to graph density —
one remix chain is a curiosity, ten thousand is infrastructure. Gating every node behind a
paid transaction guarantees sparseness, and parent-must-be-minted applies the same tax to
every edge.

**Target:**

| | Publishing | Minting |
|---|---|---|
| Cost | free | $CHAD + gas |
| Requires wallet | for attribution only, no transaction | yes |
| Produces | x420 record | ERC-721 + on-chain `parentOf` |
| Optional | no — every publish emits a record | yes |

The schema already anticipates this: `mint_status` supports `"not_minted"`, it is simply
unreachable. Drop parent-must-be-minted as a gate on *record* lineage; keep it for NFT
lineage if desired.

> **Superseded by §12.2 (2026-08-18).** The paragraph below preserved the NFT as an optional
> collectible tier. The current direction is to **wind new minting down** — it has not found
> traction, and retiring it dissolves the two-payout-systems problem rather than maintaining
> it. Existing holders and their tokens are unaffected; see §12.2 for what that obliges.

**The NFT is not deleted.** It remains the collectible tier, it keeps tamper-proof on-chain
lineage via `parentOf`, and its owner-based `parentPayoutAmount` stays as-is (SPEC §3.1.2).
It stops being the toll booth on publishing.

## 7.1 Free publishing needs an abuse model

"Free" without qualification invites bulk spam, unbounded IPFS pinning cost, and Sybil'd
records. But a per-publish fee is the wrong instrument, because **the friction of a
transaction is not its price** — even a trivial fee costs a wallet connection, a signature
prompt, a pending state, and a failure mode. You would pay the full friction penalty, collect
almost nothing, and tax the graph density the whole design depends on.

### Gate the originality claim, not the publish

The design already contains the relevant asymmetry (SPEC §3.2):

- **Publishing a remix is self-limiting.** Naming a parent carves down your own share. Nobody
  spams a mechanism that pays other people at their expense.
- **Publishing with no parents is an origin claim** — "I am the root of any lineage that
  follows." That is the claim that pays, so that is the one worth attacking. Bulk-import ten
  thousand existing memes as originals and you are positioned as the ancestor of everything
  derived from them.

| Publish type | Treatment |
|---|---|
| Remix (has a parent) | free, unlimited |
| Origin (no parents) | gated |

The cheap path is the one that credits other people.

### The gate: a slashable bond, not a holding requirement

Require $CHAD to be **staked against the claim**, not merely held.

The distinction is the whole point. A holding requirement costs a thief nothing — they hold,
they claim, they keep holding, and if the meme is valuable the gate is pure upside. A bond
that can be slashed on a successful challenge has real expected cost, scaling with how
brazen the theft is.

- Zero transaction friction on the honest path beyond the stake itself.
- Sybil resistance scales with the threshold; every wallet needs its own bond.
- Creates **persistent demand** rather than a one-time sink — bonded supply is locked for as
  long as claims stand.
- Unlike a holding gate, it actually deters the attack in SPEC §3.1.3.

Pair it with a **challenge window before splitter deployment**, which chadpad needs
regardless: the splitter is immutable, so a disputed lineage has to be resolved before
deployment or not at all.

**This requires an adjudicator, which is unsolved.** Who rules on a challenge, and on what
evidence? chadstash's existing curator roles are the obvious seed, but it is a governance
design problem, not a technical one. Until it is answered, the bond degrades to a holding
gate — real Sybil resistance, no theft deterrence.

**What none of this achieves:** x420 cannot establish first-authorship for content originating
outside the ecosystem. See SPEC §3.1.3 — that limit is structural, and the honest claim is
attested lineage for memes born in memecraft plus signed, timestamped claims for everything
else.

### Layered defence

| Layer | Handles | Cost to honest users |
|---|---|---|
| Rate limits per wallet + IP | volume spam | none (memecraft already has `enforceIpRateLimit`) |
| $CHAD holding gate on origin claims | Sybil, bulk import | must hold, not spend |
| `phash` near-duplicate check at publish | plagiarism / bulk re-upload | none |
| Published ≠ canonical | pinning cost, registry quality | none |

The last one bounds infrastructure cost: chadstash already has draft/published status,
quality ratings, and curator review. Publishing to memecraft's gallery need not mean automatic
entry into the canonical registry, so permanent pinning is only paid for records that survive
promotion.

## 8. Where $CHAD captures value

Decoupling removes a real $CHAD sink — mint fees. **This must be replaced deliberately, and
it is the decision that gates §7.**

| Surface | Mechanism | Type | Status |
|---|---|---|---|
| **memecraft publish** | **$CHAD holding gate on origin claims (§7.1)** | **demand — persistent** | **proposed** |
| chadpad launches | creation fee payable in $CHAD | sink — one-time | designed, unbuilt, needs launcher redeploy |
| chadpad launches | $CHAD as pairing/reserve asset | demand — persistent | not designed |
| memecraft mint | $CHAD mint fee | sink — one-time | live today |
| chadstash | holder tier / API access | demand — persistent | not designed |

Two principles:

**Charge where value is realized, not where it is created.** A meme has no known value at
publish time; that is precisely why creation must be cheap. A launch obviously does. Issuance
is the right toll booth.

**Prefer holding requirements over fees.** A fee is spent once and its demand evaporates. A
holding requirement locks supply for as long as the holder wants access, and costs the user
nothing they do not get back. The §7.1 gate is therefore doing double duty — it is the
anti-abuse mechanism *and* the strongest $CHAD demand surface available without a redeploy.

**Do not decouple publishing from minting until this is answered.**

## 9. Per-repo change surface

| Repo | Change | Depends on |
|---|---|---|
| **x420** | publish `x420` + `@chad/x420` packages, conformance vectors | — |
| **memecraft** | adopt shared package; sign records; register with chadstash; decouple publish from mint | §8 decision |
| **chadstash** | `x420_id`/`phash` columns; record API; IPFS pinning; backfill as `unknown`+`curator` | shared package |
| **chadpad** | splitter deploy in launch flow; read chadstash not memecraft; verify signatures; creator→`primaryCreator()` | registry live |
| **chad brain** | register generated/uploaded images | shared package |
| **chad smash** | build-time sprite manifest *(v2)* | — |

## 10. Migration

memecraft is **live on mainnet** with real minted memes, though usage is low. Two distinct
backfills, and conflating them would be the expensive mistake:

- **memecraft memes → `attested`.** `parent_meme_id` was captured by the editor at creation,
  so the lineage genuinely was observed. These are first-class records.
- **chadstash imports → `unknown`.** No recoverable authorship. Curator attribution from
  `created_by`.

Existing minted memes keep their NFTs and their owner-based payouts. Nothing is revoked.

## 11. Open decisions

| # | Decision | Blocks |
|---|---|---|
| 1 | **$CHAD demand replacement** (§8) — leading candidate is the §7.1 holding gate, which also serves as anti-abuse | decoupling publish from mint |
| 1b | **Bond size** — how much $CHAD to stake on an origin claim. Too low is no barrier; too high blocks new creators entirely | §7.1 |
| 1c | **Challenge adjudication** — who rules on a disputed origin claim, on what evidence, in what window. Without this the bond cannot be slashed and degrades to a holding gate | §7.1, chadpad mainnet |
| 2 | **Payout policy for `unknown` memes** — curator, commons, or split (SPEC §8.1) | chadpad mainnet |
| 3 | **Record signing scheme** — creator EIP-712, app attestation, or both | star topology |
| 4 | Cap on compounding ancestral carve | deep chains |
| 5 | Splitter challenge window before deploy | chadpad mainnet |

Decisions 1 and 3 are architectural. The rest are policy and can be settled later without
rework.

**Base only.** x420 targets Base, alongside x402. chadpad is also deployed on Robinhood Chain
(4663) and that constrains the design — its contracts are live there too, which is part of why
they are immovable — but no x420 work targets Robinhood Chain. Splitter deployment there is
out of scope, not deferred.

---

## 12. Target end state — the product loop

Sections 1–11 describe the mechanism. This describes what it is *for*, and it is the shape
every sequencing decision should be checked against.

```
  memecraft            chadstash              chadpad
  ─────────            ─────────              ───────
  create  ──publish──▶ index ──search──▶ people plug memes
  remix               (free)             into tweets, replies
     │                                          │
     └────────────── launch a token ────────────┘
                            │
                     LineageSplitter
                            │
                    everyone in the lineage
```

Four steps, one identity throughout: **create → publish → discover → launch.**

The loop also runs backwards, and both directions are load-bearing:

- **chadstash → memecraft** — imported memes serve as structural *formats* to build from
  (PLAN N4c). This is the best entry point to the loop, and the point at which memecraft stops
  producing only `attested` lineage.
- **chadpad → memecraft** — a launched token's page links out to create memes for it, which
  return and display on that page (PLAN N4b).

### 12.1 The token logo is the provenance anchor

The strongest single integration, and the one that most justifies the whole standard.

chadpad today generates token art with `gpt-image-1` (~$0.01/image), style-anchored to a Wojak
reference, with a deterministic SVG avatar as fallback and an on-brand retry when the model
refuses a prompt. It is real engineering spent approximating the house style.

memecraft produces the genuine article from the real character library. But quality is not the
argument. **An AI-generated logo has no creator, no lineage, and nobody to pay. A memecraft
meme has all three.**

So under this loop, the picture on the token *is* what determines the splitter's payee set.
The logo stops being decoration and becomes the economic anchor.

It is also **verifiable**. `x420Content` on the splitter is `sha256(served bytes)`, and the
served bytes are exactly what the logo displays — so anyone can check that a token's logo is
the meme whose lineage is being paid. The loop closes on-chain.

Secondary benefit: chadpad gains a top-of-funnel it does not have. Today a launch begins with
a name and a ticker and nothing else.

### 12.2 memecraft's NFT minting winds down

Consistent with §7: publishing goes free, monetisation moves to issuance, and the
two-payout-systems problem (owner-based `parentPayoutAmount` vs creator-based x420
attribution, §3.1.2 in SPEC) dissolves rather than needing reconciliation. The $CHAD sink
moves to chadpad's creation fee, which is already designed.

**This is a wind-down, not a deletion.** `MemeCraftNFT` is live on mainnet with real holders.
Those ERC-721s persist no matter what — only *new* minting can stop. Two obligations follow:

- Existing holders keep their tokens and their on-chain `parentOf` lineage.
- Halting new mints stops future `parentPayoutAmount` flows, which quietly changes the deal
  for anyone holding a parent NFT in expectation of remix income. That needs an explicit
  decision about what those holders are told, not a silent switch-off.

### 12.3 Auto-population fights search quality — tier the catalog

chadstash's search is good *because the catalog is curated*: reciprocal rank fusion across
lexical, trigram, semantic, and CLIP channels, over quality-rated, human-reviewed entries.

Piping every free memecraft publish straight into it dilutes exactly the signal the
search-to-tweet use case depends on. **Cheap publishing and high-quality search pull against
each other**, and this is the tension most likely to be discovered too late.

The resolution is already specified in §7.1: **published ≠ canonical.**

| Tier | Contents | Purpose |
|---|---|---|
| Indexed | every memecraft publish | lineage resolution, dedupe, identity |
| Canonical | curated or signal-promoted | search results, chad brain, recommendations |

Promotion comes from curation or earned signal — usage, launches, engagement. Breadth serves
lineage; quality serves search. Conflating the two damages both.

### 12.4 Search-to-tweet is free, and stays free

Retrieval does not monetise — the same distinction drawn for x402 in SPEC §9. Paying to *see*
a meme fights the medium. This surface is distribution and top-of-funnel, and it is valuable
as such, but it must not be counted as revenue. **Revenue is launches.**

### 12.5 The handoff: launching a token from memecraft

Currently unspecified, and it should not be built ad hoc.

```
memecraft "launch this"  ──▶  chadpad /create?x420=x420:<hash>
```

Passing only the id is deliberate — chadpad already resolves everything else from it, and a
signed splits response is more trustworthy than anything carried in a query string.

chadpad then:

1. `GET /api/x420/{id}/splits` — payees, provenance, `content_sha256`, signature *(exists)*
2. Verify the signature and gate on provenance *(WO-3)*
3. Fetch the meme's image and pre-fill it as the token logo *(**gap** — see below)*
4. On launch, deploy the splitter and pass it as `creator` *(exists)*

**Known gap: the splits response carries no image URI.** It returns `content_sha256` but no
pointer to the bytes, so chadpad cannot retrieve the logo. Add `content_uri` to the response,
or serve it from the record endpoint when that lands.

**Reference the existing pin; do not re-pin.** The artifact is already content-addressed on
IPFS, and the `x420Content` anchor commits to those exact bytes. Copying them elsewhere
introduces drift and breaks the verifiability in §12.1. chadpad should also fetch server-side
rather than routing through its creator-signed image-upload path, which exists for a different
purpose.
