# Production Push — first mainnet lineage launch

**Opened:** 2026-08-17 · **Gate:** `python3 scripts/status.py --blockers` exits 0

Both memecraft and chadpad are already live on mainnet. "Production" for x420 therefore means
one specific event: **a token launched on chadpad mainnet whose creator fee stream is paid to
a `LineageSplitter` carrying real anchors.**

Everything in this document exists to make that event safe. Anything not required for it is
explicitly deferred below, because scope creep is the main risk to a push like this.

---

## What does NOT block production

Deciding this first is what keeps the push small. With the provenance gate set to
**`attested` only**, every open policy question falls out of scope:

| Deferred | Why it does not block |
|---|---|
| `unknown`-meme payout policy (curator / commons / split) | attested-only launches never encounter `unknown` |
| Bond size and challenge adjudication | those gate *widening* past attested, not attested itself |
| $CHAD demand replacement | gates decoupling publish from mint, a separate initiative |
| Publish/mint decoupling | not on this path |
| Phase 3 — chadstash registry | the memecraft → chadpad link works without it |
| Phase 4 — chad brain, chad smash | consumers, not prerequisites |
| Shared packages + conformance vectors | important, but a correctness-hygiene project |
| Robinhood Chain | **out of scope entirely** — see below |
| `x420Record` anchor | no record API yet; ship with `x420Content` only |

**The gate stays `attested`-only for this push.** Widening it is a separate decision with its
own blockers.

### Base only — Robinhood Chain is not part of this effort

x420 targets **Base**, alongside x402. chadpad is also deployed on Robinhood Chain (4663), and
that fact still constrains the design — its contracts are live there too, which is part of why
they are treated as immovable — but **no x420 work targets Robinhood Chain.**

Concretely: do not deploy splitters there, do not add RH-specific paths, and do not treat RH
coverage as a gap to close. A lineage launch on Robinhood Chain is out of scope, not pending.

This is a deliberate narrowing. Earlier drafts carried "Robinhood Chain splitter deployment"
as an open decision; it has been removed rather than deferred.

---

## Interface contracts

Agree these before either repo writes code. Both were the source of prior churn.

### 1. `content_sha256` — settled

| | |
|---|---|
| Value | full SHA-256 of the **served** artifact |
| Encoding | 64 lowercase hex chars, **no `0x` prefix** |
| Consumer | chadpad prepends `0x`, passes as `bytes32 x420Content` |

`x420_id` remains `"x420:" + content_sha256[:32]`, which gives a free cross-check.

### 2. Splits response signature — **as built** (memecraft `28e821e`)

This section previously carried a proposed schema. memecraft implemented a different one and
**the implementation is authoritative** — it corrected two real errors in the proposal. Do not
resurrect the earlier version.

```ts
// No chainId, no verifyingContract.
const domain = { name: "x420", version: "1" };

const types = {
  Payee: [
    { name: "recipient",     type: "address" },
    { name: "bps",           type: "uint256" },
  ],
  X420Splits: [
    { name: "x420Id",        type: "string"  },
    { name: "contentSha256", type: "bytes32" },
    { name: "totalBps",      type: "uint256" },
    { name: "provenance",    type: "string"  },
    { name: "payees",        type: "Payee[]" },
    { name: "deadline",      type: "uint256" },
  ],
};
// primaryType: "X420Splits"   ·   TTL: 15 minutes
```

**Two corrections the implementation made:**

1. **No `chainId` in the domain.** The proposal bound signatures to the launch chain, which
   contradicts `SPEC.md §2.2` — an x420 id is deliberately chain-free so one meme has one
   identity across every chain $CHAD launches on. Binding to a chain would have produced a
   different signature per chain for the same meme.
2. **A `Payee[]` struct array rather than parallel `address[]` / `uint16[]` arrays.** This
   eliminates the length-mismatch and misalignment failure modes entirely, rather than
   defending against them by convention.

**Response fields added** (nothing removed):

| Field | Notes |
|---|---|
| `content_sha256` | 64 lowercase hex, no `0x` |
| `payees` | **canonical order — ascending by address.** Verify against this array, not the `splits` map, whose key order is not guaranteed |
| `deadline` | unix seconds |
| `signer_address` | the pinned signer |
| `signature` | null when unsigned |

**A response is unsigned when no content anchor exists**, rather than signing over a zero
anchor. A null signature must therefore be treated as "not launchable," not as "skip
verification."

The signer key is separate from the mint-authorisation key, so an x420 key leak is not a mint
leak. It is configuration (`MEMECRAFT_X420_SIGNER_PRIVATE_KEY`) and rotatable without a
redeploy.

### 3. `content_uri` — the launch handoff

For the memecraft → chadpad handoff (`ARCHITECTURE.md` §12.5). memecraft WO-4 adds it;
chadpad WO-5 consumes it.

| | |
|---|---|
| Field | `content_uri` |
| Value | canonical **`ipfs://` URI** (memecraft's `memes.export_url`) |
| Null when | no pinned artifact — the same condition that leaves a response unsigned |
| **Not** in the signed payload | see below |

**Deliberately unsigned.** `content_uri` is a *pointer*, and signing a pointer is weaker than
what the existing signature already permits: chadpad fetches the bytes, hashes them, and
compares against the `content_sha256` that **is** signed. Matching bytes prove the artifact is
the one the lineage was signed over, regardless of how or by whom it was served.

**Verify the bytes, not the pointer.** That is the point of content addressing, and it means
the EIP-712 struct — already implemented and verified on both sides — does not change.

An `ipfs://` URI rather than a gateway URL, so the value cannot drift and chadpad is not
coupled to memecraft's gateway choice.

---

## Work orders

Each is self-contained and can be handed to a repo-scoped agent without this conversation.

### WO-1 · memecraft — anchors and signing · *blocks WO-3*

Three changes, one batch. Reference: `docs/X420.md` Tasks 2c.

1. **Add `content_sha256`** to `memes` — 64 lowercase hex, no prefix. Populate in the publish
   path from the same served bytes that produce `x420_id`.
2. **Return it** from `GET /api/x420/{x420Id}/splits`.
3. **Sign the response** per the EIP-712 schema above.

**Do not** include backfill in this batch. Backfill repairs nothing already deployed —
splitters are immutable — so it has no deadline and a different risk profile. Script it
separately, and when you do, re-hash each fetched artifact and verify its first 32 hex chars
match the stored `x420_id`, flagging mismatches rather than writing them.

**Done when:** `python3 scripts/status.py --blockers` shows B1a, B1b, B2a passing.

### WO-2 · chadpad — test the integration path · *parallel, no dependency*

`LineageSplitter.sol` has 15 tests. The code that decides who gets paid has none.

Cover: `lib/x420.ts` validation (payee cap, duplicate rejection, `total_bps` mismatch,
provenance gating, malformed ids), `lib/lineage.ts` payee mapping, the splits route's refusal
paths, and the indexer's `primaryCreator` resolution including its non-splitter fallback.

The upstream error taxonomy matters: 400/404/409 are refusals, not retries. A test should pin
that a 409 never becomes a launch.

**Done when:** B3 passes and `forge test` still shows 54+ passing.

### WO-3 · chadpad — consume real anchors and verify signatures · *depends on WO-1*

1. Replace both `UNSET_ANCHOR` arguments at `CreateToken.tsx:311-312`. `x420Content` gets
   `0x` + `content_sha256`; `x420Record` stays zero until a record API exists.
2. Verify the EIP-712 signature in `lib/x420.ts` before any splitter deploys. Reject on bad
   signature, wrong signer, or expiry — same refusal path as bad provenance.
3. Fail closed: an unsigned or unverifiable response must refuse the launch, never fall back
   to trusting it.

**Done when:** B1c and B2b pass, and a testnet launch shows a non-zero `x420Content` on-chain.

---

## Sequence

```
  now ──┬── WO-1  memecraft (anchors + signing)  ──┐
        │                                          ├── WO-3  chadpad (consume + verify)
        └── WO-2  chadpad (tests)  ────────────────┘
                                                        │
                                              record the demo (testnet)
                                                        │
                                              first mainnet lineage launch
```

WO-1 and WO-2 are independent and should run concurrently in their own repos. WO-3 cannot
start until WO-1 ships the field and the signature.

## Exit criteria

1. `python3 scripts/status.py --blockers` exits 0.
2. A testnet lineage launch shows a non-zero `x420Content` on the deployed splitter.
3. `FeeRouter.claim` → `splitter.release` pays the ancestry, verified on testnet.
4. The demo is recorded — remix, launch, ancestor paid.
5. Provenance gate confirmed `attested`-only in the deployed build.

Only then: first mainnet lineage launch.

## Standing risks during the push

- **Every testnet launch made before WO-3 permanently carries a zero anchor.** They cannot be
  repaired. Keep testnet lineage launches to a minimum until WO-3 lands, or accept those
  splitters as disposable.
- **`x420Record` ships as zero.** Accepted for this push; revisit when the record API lands.
- **One trust assumption remains after WO-3:** chadpad trusts memecraft's signer to state
  lineage honestly. That is a same-owner assumption and acceptable now; it stops being
  acceptable if either app is ever operated by a third party.

---

## Mainnet runbook

### 1. Configuration

Both apps are Vercel. Every variable below is **server-side** — the browser calls chadpad's
own `/api/x420/splits` proxy, which reaches memecraft server-side, so nothing is bundled to
the client. **Never add a `NEXT_PUBLIC_` prefix**; on the signer key that would inline a
payout-authorising secret into client JS.

| Project | Variable | Value |
|---|---|---|
| memecraft | `MEMECRAFT_X420_SIGNER_PRIVATE_KEY` | signing key (secret) |
| chadpad | `X420_SIGNER_ADDRESS` | the address **derived from** that key |
| chadpad | `MEMECRAFT_API_BASE` | production memecraft URL |

The invariant that breaks every launch if wrong: `X420_SIGNER_ADDRESS` must be the address of
`MEMECRAFT_X420_SIGNER_PRIVATE_KEY`. **Derive it, do not type it.**

Vercel specifics:

- **Scope deliberately** — Production / Preview / Development are separate. Testnet in Preview,
  mainnet in Production, with a **different signer key per environment** so a leaked testnet key
  cannot sign mainnet splits.
- **Env changes need a redeploy**; they do not apply to existing deployments.
- **Vercel env is not a KMS.** Anyone with project access can read that key. Acceptable at this
  stage, but it now authorises real payouts — know that is the posture.

### 2. Pre-flight

One call verifies the three things that otherwise fail silently — key loaded, address matching,
anchor present:

```bash
curl -s "$MEMECRAFT_API_BASE/api/x420/<published-x420-id>/splits" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); \
    print('signer:', d.get('signer_address')); \
    print('anchor:', d.get('content_sha256') is not None); \
    print('total:', d.get('total_bps'))"
```

`signer` must equal chadpad's `X420_SIGNER_ADDRESS`, `anchor` must be `True`, `total` must be
`10000`.

Then run the full path once on testnet — publish → remix → launch → confirm non-zero
`x420Content` on the splitter → confirm `FeeRouter`'s stored `creator` is the splitter →
generate a swap → `claim` → `release` → confirm the ancestor's wallet receives. **No recording
required; this is verification, not marketing.** Splitters are immutable, so the first mainnet
launch permanently bakes in whatever is misconfigured.

### 3. Indexer deploy — expect a reindex

The x420 work changed `ponder.schema.ts` (`splitter` column, `creator` resolved at index time,
commit `faca482`). Per `SCALING.md`, **any indexer schema change triggers a full reindex**,
during which it serves incomplete data until it catches head — the closest thing to downtime
for fresh data. Use the blue-green pattern in that document rather than restarting in place.

Also check the Base notifier env, which `SCALING.md` warns fails **silently**: `APP_BASE_URL`
defaults to the Robinhood host, so leaving it unset on the Base service makes every alert link
to the wrong site.

### 4. Rollback

`MEMECRAFT_API_BASE` is the kill switch. Unset it and `apiBase()` throws
`X420UnavailableError`, so launches proceed as ordinary EOA-creator launches with no lineage.
No deploy needed beyond the env change. **Verify this degrades gracefully before you need it** —
a path that blocks launches outright instead of falling back is not a rollback.

### 5. Know it is working

Deployment success is not the metric. Two questions matter after launch:

- **Are launches actually creating splitters?** The indexer stores `splitter` per token — count
  rows where it is non-null.
- **Is money reaching the lineage?** `PaidOut` events on the splitters. A launch with a splitter
  that never emits `PaidOut` means fees are accruing but nobody has called
  `FeeRouter.claim` → `release`. Both are permissionless, so anyone can trigger them, but
  nobody will until someone does.

### 6. Accepted risks

- **`LineageSplitter` is unaudited.** Mitigating: no owner, no upgrade, no sweep, and the only
  fund-moving function pays registered payees proportionally. Funds cannot be stolen, only stuck.
- **One reverting payee blocks that token's release permanently.** `release()` loops with
  `safeTransfer`; a single revert reverts all. Causes: a USDC-blacklisted address, a payee
  contract that rejects transfers, or `ChadToken`'s per-wallet cap if a release lands inside the
  cap window. Blast radius is one token, and each token releases separately.
- **Splitter deployment is client-side**, so a modified client could deploy one with arbitrary
  payees and pass it as `creator`. Not a theft vector — the launcher would receive 100% anyway —
  but it allows a "lineage launch" that pays no ancestors. Post-hoc fix: the indexer already
  stores `splitter`, so it can read the deployed payees and compare against memecraft's splits,
  flagging mismatches.
