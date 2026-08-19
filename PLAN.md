# x420 Implementation Plan

**Spec:** [`SPEC.md`](./SPEC.md) · **Last updated:** 2026-08-17

Sequenced so the first shippable milestone is a **demo**, not a framework. For the target
product loop this all serves, see [`ARCHITECTURE.md`](./ARCHITECTURE.md) §12.

> Create a meme in memecraft → remix it → launch a token on the remix in chadpad → the
> original creator's wallet receives fees.

One screen recording. No slides. Everything else in this plan is downstream of making that
video possible.

---

## The critical path touches only two repos

The natural instinct is to build chadstash into the system of record first, because that is
the correct long-term architecture. **Do not start there.** memecraft already owns the
lineage graph, so for the demo it can serve splits directly. chadstash becomes necessary
when lineage must span apps that memecraft doesn't know about — that is Phase 3, not Phase 1.

This split matters more than it first appears. Most of the chadstash catalog is **imported**
memes with unknowable authorship (`provenance: "unknown"`), and the payout policy for those
is still undecided (SPEC.md §8.1). memecraft's graph is separate and closed: its memes
descend from its own template set (`src/config/templates.ts`) and from other memecraft memes,
so every edge is `attested`. **Phase 1 therefore runs entirely through attested territory and
is not blocked by the open policy question.**

> **This closure ends at N4c.** Once chadstash memes become memecraft formats, memecraft can
> produce `unknown`-lineage memes and the policy question stops being deferrable. Phase 1 is
> unaffected — the statement above holds for everything shipping now — but do not carry the
> assumption past that point.

| Repo | Phase 1 (demo) | Later |
|---|---|---|
| `memecraft` | **2 tasks** | 2 tasks |
| `chadpad` | **2 tasks** | 2 tasks |
| `chad_stash` | — | 3 tasks |
| `chad-brain` | — | 1 task |
| `chad-smash` | — | deferred |

---

## Status

**Do not read status from this file — run it:**

```bash
python3 scripts/status.py --blockers
```

The table below is a snapshot from 2026-08-17 and will drift. The script reads the five repos
directly and cannot.

**Phase 1 is complete. The demo is unblocked — record it.**

| Task | Repo | State |
|---|---|---|
| M1 · persist `x420_id` over served bytes | memecraft | done |
| M2 · resolve splits, `GET /api/x420/{id}/splits` | memecraft | done |
| C1 · deploy splitter in launch flow | chadpad | done |
| C2 · creator resolution | chadpad | done — resolved at *index* time, better than specified |
| C3 · provenance gate | chadpad | done (`attested` only) |
| C4 · indexer columns | chadpad | done (`creator` resolved, `splitter` stored) |

chadpad resolved C2 more cleanly than this plan described. Rather than resolving
`primaryCreator()` at each read site, the indexer resolves it once at index time and stores
the human in `creator` with the splitter in a separate column. Every downstream consumer —
dashboard, creator page, metadata auth, image auth — then works unchanged.

`initialBuyWeth` is handled by disabling initial buys on lineage launches, which is the
simplest correct option.

### Mainnet blockers

**The active push is tracked in [`PUSH.md`](./PUSH.md) — read that, not this section.**

memecraft's half shipped in `6ab9806` (full `content_sha256` anchor) and `28e821e` (EIP-712
signing over the resolved payee list). **B1a, B1b, and B2a pass.**

Remaining, all in chadpad:

| | Blocker | Work order |
|---|---|---|
| **B1c** | still deploys `UNSET_ANCHOR` for `x420Content` | WO-3 |
| **B2b** | does not verify the splits signature | WO-3 |
| **B3** | no tests on `lib/x420.ts`, `lib/lineage.ts`, the splits route, or the indexer resolver — the code that decides who gets paid | WO-2 |

`x420Record` stays zero until a record API exists (Phase 3); that is accepted for this push.

memecraft's implementation corrected the proposed signing schema in two ways — no `chainId` in
the EIP-712 domain (an x420 id is chain-free per §2.2, so binding to a chain would give one
meme a different signature per chain) and a `Payee[]` struct array rather than parallel arrays.
`PUSH.md` §2 records the as-built version and is authoritative.

## Phase 1 — Make the demo possible *(complete)*

### M1 · memecraft: hash the served bytes, server-side · **S**

> **Corrected 2026-08-17.** This task originally said to persist the SHA-256 computed at
> `export-signature.ts:308`. That was wrong — see below.

Hash the **final served artifact**, server-side, in the publish path
(`src/lib/meme-publishing.ts`):

```ts
const x420Id = `x420:${sha256(servedBytes).slice(0, 32)}`;
```

- Add the `x420_id` column (indexed, **not unique** — see below) to `memes`.
- No chain segment — $CHAD is on three chains; chain-scoping would give one meme three ids.

**Why not line 308.** That hash is taken *before* the `memecraft` tEXt chunk is injected, and
the injected artifact is what ships. A published file can therefore never contain its own
digest, and anyone downloading the pinned image computes a different id than memecraft
recorded — breaking the one property the standard exists to provide (SPEC.md §2.1: identity
is recomputable from the file alone). Hashing server-side also removes any need to trust a
client-supplied hash, which matters because identity routes payouts.

**Consequence — `x420_id` is not a dedupe key.** The injected payload carries
`exportId: crypto.randomUUID()` and `exportedAt`, so the served bytes are non-deterministic:
the same meme exported twice yields different ids. Visual dedupe belongs to `structure_hash`
and `phash` (M3). Do not put a uniqueness constraint on `x420_id`.

**Done when:** downloading the published artifact and hashing it independently reproduces the
stored `x420_id` exactly.

### M2 · memecraft: expose resolved splits · **M**

Port `resolve_splits` from `x420/lineage.py` to TypeScript and serve it:

```
GET /api/x420/{x420_id}/splits
→ { splits: { "0x…": 8500, "0x…": 945, … }, provenance: "attested", total_bps: 10000 }
```

Walk `parent_meme_id` recursively, each parent carving its `royalty_bps` off the top. Three
details are load-bearing and all three are already solved in the Python reference:

- **Cycle guard** — the graph can contain loops; raise rather than recurse forever.
- **Dust** — basis-point integer division sheds remainder; the largest payee absorbs it so
  the total is exactly 10000.
- **Provenance** — return it. chadpad refuses to deploy against `unknown`.

**Schema prerequisites — decided 2026-08-17, see `memecraft/docs/X420.md` Task 2b:**

| Gap | Decision |
|---|---|
| No per-meme `royalty_bps` | Add the column; populate at publish from a config constant. Denormalized so tuning the default never retroactively rewrites historical payout bases. Not user-editable yet. |
| No `provenance` column | Add it, default `attested` for editor-published memes. Describes the *lineage claim*, not artwork originality. |
| Creator vs. owner mismatch | x420 attribution is **creator-based** (`creator_wallet_address`), fixed at publish. memecraft's owner-based `parentPayoutAmount` stays as-is. They are different rights — do not unify. See SPEC.md §3.1.2. |

The creator/owner decision is forced by the contract: `LineageSplitter` holds a fixed payee
array and cannot re-resolve a changing NFT owner. Owner-based payouts would need a different
contract that calls `ownerOf()` at release time, with a cross-chain trust dependency.

**Done when:** a three-deep chain returns splits summing to exactly 10000.

### C1 · chadpad: deploy a splitter in the launch flow · **M**

`src/LineageSplitter.sol` is written and tested (15 tests, `forge test --match-contract
LineageSplitterTest`). What's missing is the flow that uses it.

Before calling `launchToken`:

1. Fetch splits from memecraft (M2).
2. Refuse if `provenance === "unknown"` — the splitter is immutable and cannot be corrected.
3. Deploy `LineageSplitter(primaryCreator, x420Content, x420Record, payees)`.
4. Pass **the splitter address** as `creator` to `launchToken`.

For a meme with no ancestors, deploy a single-payee splitter rather than branching to the
plain-EOA path. One code path means C2 doesn't need to handle two shapes.

**Done when:** a launch on Base Sepolia has `FeeRouter`'s stored `creator` equal to the
splitter, and `release()` pays the ancestry.

### C2 · chadpad: fix the three creator assumptions · **M**

`token.creator` is now a contract. Nothing on-chain breaks; three places in `packages/web`
read it as a human:

| What | Where | Fix |
|---|---|---|
| "My launches" views | token queries | resolve via `LineageSplitter.primaryCreator()` |
| Metadata / image edit auth | `packages/web/lib/sig.ts` → `app/api/metadata/route.ts`, `app/api/token-image/[address]/route.ts` | verify signature against `primaryCreator()` |
| `initialBuyWeth` | launch flow | set to zero for lineage launches, or let `release()` distribute the token side |

**Done when:** a creator can still edit metadata on a lineage launch, and it appears in their
launches list.

### Milestone: record the demo

Everything above exists → make the video. If it can't be made, the gap tells you exactly
what's left.

---

## Phase 2 — De-risk before mainnet

### M3 · memecraft: fix the `visualHash` collision · **S**

A live correctness hazard, independent of x420. Three hashes, two names:

| Location | Current name | Rename to |
|---|---|---|
| `export-signature.ts:308` | `sha256` | `preinjection_sha256` — **not** the x420 id (M1) |
| `export-signature.ts:224` | `visualHash` (dHash, 64-bit perceptual) | `phash` |
| `meme-publishing.ts:801` | `visualHash` (canonicalized JSON SHA-256) | `structure_hash` |

The publishing pipeline's version drives duplicate rejection. Anything comparing the two is
silently wrong. Rule: perceptual hashes *suggest*, they never decide identity or payouts.

### C3 · chadpad: implement the provenance policy · **S–M** · *blocked on a decision*

Originally written as "refuse `unknown`." That was wrong: it assumed `unknown` was a rare
backfill artifact, when in fact most of the chadstash catalog is imported memes with
genuinely unknowable authorship. Refusing them would reject most of the library.

The gate needs a *policy*, not a refusal — see SPEC.md §8.1 for the options (curator share,
commons pool, or a split). **This is an economic decision that has to be made before the
first mainnet lineage launch.** `LineageSplitter` accepts any payee list, so the contract
does not constrain the answer, and Phase 1 is not blocked: memecraft-native memes are all
`attested`.

Whatever the policy, enforce it server-side rather than in the UI. An immutable splitter
deployed against wrong lineage is unrecoverable.

### C4 · chadpad: indexer columns · **M** · *optional*

`splitter` and `x420Id` on the `token` table lets the UI show lineage without an RPC call per
token. Forces a full reindex — weigh it.

---

## Re-sequenced 2026-08-18 — the product loop drives the order

`ARCHITECTURE.md` §12 sets the target: **create → publish → discover → launch**, one identity
throughout. That changes what is urgent.

Phases 3 and 4 below were written when chadstash-as-registry was a later nicety. Under the
product loop, **auto-population into chadstash is core**, not deferred — it is the "discover"
step, and without it memecraft memes are invisible to everyone except chadpad.

Revised order after the current push (WO-3 → testnet demo → mainnet lineage launch):

| # | Work | Why here |
|---|---|---|
| **N1** | chadstash registry — `x420_id`/`phash` columns, record API, `unknown`+`curator` backfill *(was Phase 3: S1–S3)* | the "discover" step; everything else waits on it |
| **N2** | memecraft auto-publishes records to chadstash *(was M4)* | closes create → publish → discover |
| **N3** | **Catalog tiering — indexed vs canonical** *(new, ARCHITECTURE §12.3)* | ships **with** N2, not after |
| **N4** | **memecraft → chadpad launch handoff** *(new, ARCHITECTURE §12.5)* | the highest-value unbuilt feature |
| **N4b** | **chadpad → memecraft: memes for a launched token** *(new, see below)* | reverse of N4, shares its plumbing |
| **N4c** | **chadstash memes as memecraft formats** *(new, see below)* | best entry point to the loop; **forces the `unknown` policy decision** |
| **N5** | Publish/mint decoupling + NFT wind-down *(ARCHITECTURE §7, §12.2)* | gated on the $CHAD sink decision |
| **N6** | chad brain registers generated images *(was Phase 4)* | additive |
| — | chad smash | still deferred |

**N3 is not optional and must not lag N2.** chadstash's search quality comes from curation;
piping every free publish into the canonical set dilutes exactly the signal the
search-to-tweet use case depends on. Shipping auto-population without tiering degrades a
working product.

**N4 has a known gap:** the splits response carries `content_sha256` but no image URI, so
chadpad cannot retrieve the logo. Add `content_uri` to the response or serve it from the
record endpoint (N1). See ARCHITECTURE §12.5.

**N5 is blocked** on where $CHAD demand moves once mint fees stop — the leading candidate is
chadpad's creation fee, which needs a launcher redeploy and so is not free.

### N4b · Memes for a launched token

A token page links out to memecraft; memes created there come back and display on that token's
page. The reverse of N4, and it reuses the same handoff plumbing.

**x420 is not strictly required here** — you could tag images to tokens without it. It earns
its place by supplying stable ids across both apps, free dedupe when two people submit the
same meme, and the lineage property below.

**Model the association in chadpad, not in the record.** It is `(token_address, x420_id)` — a
chadpad table. Do **not** add a token field to the x420 record: it is chain-specific,
launchpad-specific, and says nothing about provenance.

**Never put the token in `parents`.** A meme made *for* a token is not *derived from* it.
Recording it as a parent inserts the token into the ancestry as a royalty-earning contributor
and quietly misroutes money. See SPEC §3.

**The emergent property that makes this worth building:** community memes for a token are
frequently remixes of that token's logo, which is itself a memecraft meme with a real record.
So a token page is not a flat gallery — it is a **lineage tree rooted at the logo**. And if a
community meme is later tokenized, the logo's creator is in its ancestry and gets paid, with
no new mechanism. The loop closes in both directions.

**Risk:** token pages become a spam surface, since anyone can make a meme "for" any token.
Needs token-creator curation or signal-based promotion — the same indexed-vs-canonical tiering
as N3, applied per token.

### N4c · chadstash memes as memecraft formats

*Proposed by CryptoSeanPrice, 2026-08-18.*

Use an existing chadstash meme as a **structural format** inside memecraft — take it as a
starting layout, then add or delete assets and change the text. Format remixing is how memes
actually work; impact text over a known image *is* the medium.

chadstash's corpus is curated, tagged, and searchable, which makes it a far better template
library than 85 hardcoded layouts, and it gives the product loop its best entry point:

```
  search chadstash  →  remix in memecraft  →  publish  →  maybe launch
```

It is also the strongest reason for chadstash and memecraft to be connected at all, beyond
sharing identifiers.

**Depends on N1** — chadstash memes need x420 ids before they can be parents.

#### This ends memecraft's attested closure

Using an imported meme as a format is a **genuine derivation** — unlike the token association
in N4b, the artifact really was built from that content, so it belongs in `parents` with
`relation: "template"`.

Weakest-link provenance then does its job: the new meme resolves to `unknown`, because nobody
knows who made the base. That is correct, and it means **memes made this way are not launchable
under the `attested`-only gate.**

So this feature is the first thing that makes the `unknown` payout policy *matter*. It was
ignorable only because attested-only launches never encountered `unknown`.

**Corrected 2026-08-18 — N4c is degraded by this, not blocked by it.** The feature ships fine
under the current `attested`-only gate: chadstash formats, creation, publishing, and discovery
all work. What does not work is **launching a token on a format-derived meme**. That is a real
limitation and may still be an acceptable v1, so treat the policy as a prerequisite for the
*tokenization path*, not for the feature.

#### It also strengthens the answer

Curator attribution becomes more defensible here, not less. Nobody knows who drew the original —
but somebody imported it, tagged it, wrote its use-cases, and made it usable *as a format*. If
that curation is what enabled the new meme, a share of the ancestral cut is a real claim rather
than a consolation prize. Against a concrete feature it is the strongest of the four options in
SPEC §8.1.

#### Exclude known-author memes before shipping

The framing behind this idea was "existing memes that we stole." That is accurate, and a tool
that takes others' work as a base while paying **curators** rather than **creators** is exactly
the uncomfortable case: defensible for anonymous folk art, not for a living, identifiable
author. (Matt Furie litigated over Pepe.)

`source_url` and `attribution` already exist on the chadstash model. Flagging known-author memes
as **ineligible for template use** is cheap insurance and belongs in this work item, not in a
follow-up.

#### Charging in the token itself — anti-spam that doubles as token utility

Require payment or a burn **denominated in the token being memed**. It prices out spam, and it
turns the meme surface into a *utility for the launched token* — a reason to launch on chadpad
rather than a generic launchpad:

> Launch here and your token gets a meme surface where every meme burns supply and pays your
> artists.

**The routing is already built.** That token already has a `LineageSplitter`, deployed at
launch, holding its logo's lineage. `LineageSplitter` is revenue-source agnostic — it fans out
any ERC-20 balance, and `releaseMany` handles several — so it accepts $TOKEN as readily as
WETH. No new contract:

```
  chadpad launch fees      (WETH)   ──┐
  meme creation fees       ($TOKEN) ──┼──▶  LineageSplitter  ──▶  lineage
  x402 licensing (future)  (USDC)   ──┘
```

The creator whose meme became a token's logo then earns whenever someone makes a meme for that
token — a creator income stream that costs nothing to build.

**Burn vs. lineage is a genuine fork**, since burned units cannot also be paid out:

| | Effect |
|---|---|
| Burn | deflationary, benefits all holders equally, stronger memecoin narrative, no recipient needed |
| Lineage | creator income, reinforces the x420 thesis, payees receive the token they helped create |

A split (e.g. 50/50) makes it a tunable rather than a commitment. Lineage-weighted is the more
differentiated choice — every memecoin can burn.

**Three risks to price before building:**

- **Token-denominated fees are price-volatile.** A fixed 1,000 $TOKEN may be worth $0.01 or
  $100 a week later. Survivable for anti-spam, which only needs the cost non-zero and annoying,
  but it will feel arbitrary. USD-denominated with spot conversion is the alternative, at the
  cost of an oracle dependency.
- **Worthless tokens get spammed anyway.** Near-zero price means a meaningless fee, exactly
  when the page is least worth defending. Curation still has to exist underneath.
- **Dust accumulation.** Splitters collect many small $TOKEN balances and `release()` costs
  gas; for a low-value token, claiming can cost more than it pays. Release is permissionless so
  someone will call it when worthwhile, but expect long-tail balances that never get claimed.

The phase sections below retain the original task detail; read them through this ordering.

## Phase 3 — Ecosystem-wide identity

Only now does chadstash become the system of record.

### S1 · chadstash: add `x420_id` and `phash` · **S**

**Additive.** Do not migrate `file_hash` — it's BLAKE2b-256, it drives a working 409 dedupe
path, and it should stay. Two hashes over the same bytes is cheap; migrating a live dedupe
path is not.

### S2 · chadstash: backfill as `unknown` · **M**

The most dangerous step in the plan. Every existing meme predates provenance capture.

Backfill as `provenance: "unknown"`, **never** as originals with empty `parents`. An empty
`parents` on an `attested` record means "verified original"; on an `unknown` record it means
"we have no idea." Conflating them lets every legacy meme silently claim origin status and
capture full allocation. Consumers branch on `provenance`, not `parents.length`.

Promotion from `unknown` to `asserted` is a curator action, logged to `admin_events`.

### S3 · chadstash: record API · **M**

```
GET  /api/x420/{x420_id}          → record
GET  /api/x420/{x420_id}/splits   → resolved splits
POST /api/x420/records            → register (API key)
```

Keep slug working permanently — chad-brain depends on it and it's the only cross-app
integration that predates this work.

### M4 · memecraft: register records with chadstash · **S**

Emit full records with `provenance: "attested"` and `origin: { app: "memecraft", ref: <uuid> }`.
chadpad's split lookup then moves from memecraft to chadstash, and lineage can span apps.

---

## Phase 4 — Remaining surfaces

### B1 · chad-brain: register generated images · **S**

`/image`, `/chad`, `/wojak` produce real memes that currently have no identity beyond an
ephemeral Telegram `file_id`. Hash at generation, register as `asserted` with the prompt as
evidence. Every one is a lineage root the ecosystem is otherwise losing.

### chad-smash · deferred

Not a meme consumer — it's a fixed cast of 8 archetypes across 17 hand-made sprites. The real
hook is the reverse of the assumed one: the repo already flags **sprite provenance as a
blocker to publishing**. x420 can produce that provenance manifest. Worth doing for shipping
reasons, not telemetry reasons.

---

## Decisions still open

| Question | Blocks | Notes |
|---|---|---|
| **Payout policy for imported (`unknown`) memes** | tokenizing `unknown` lineage | Curator share, commons pool, or a split. See SPEC.md §8.1. **Applied once, at `LineageSplitter` construction**, and governs every revenue stream into that contract — launch fees, meme fees, future licensing. Two separable questions: the *gate* (can it launch?) and the *allocation* (who gets the ancestral share?). Forward-only: changing it later affects new launches only, so it is safe to start restrictive. Does not block Phase 1 or N4c — it gates the tokenization path for format-derived memes. |
| Known-author memes | C3 | Paying curators is fine for anonymous folk art, fraught for living authors. `source_url`/`attribution` can flag them. |
| Cap on compounding ancestral carve? | deep chains | Each generation carves from gross; long lineages starve the newest creator. |
| Challenge window before splitter deploy? | C1 | Immutable splitters can't fix bad lineage. |
| Converge memecraft `parentPayoutAmount` with the fee splitter? | — | Two lineage payout mechanisms now exist. |
| ~~Robinhood Chain splitter deployment~~ | — | **Out of scope.** x420 targets Base only. Removed, not deferred. |
| Where do `royalty_bps` and multi-payee attribution get authored? | M2 | Currently implicit; needs a UI or a default policy. |

## Deliberately out of scope

**x402 payment surfaces — sequenced, not rejected.** *(Decided 2026-08-18.)* x420 is
x402-native and ships on Base; the current effort builds identity and lineage only. A paid
**licensing** surface is the intended next initiative and is documented in `SPEC.md` §9.

Paid *retrieval* stays off the table — memes spread because they are free, and gating that is
self-defeating. Paid *licensing* is a different product and a good fit, because
`LineageSplitter` is revenue-source agnostic: licence payments in USDC can settle to the same
contract that receives chadpad's WETH fee stream. `app.py` is a working reference for when
that starts.

**Calling x420 a "standard" externally.** A standard is something third parties implement.
Today it's a shared schema with one ecosystem behind it, which is respectable but not that
word. Let it earn the title.
