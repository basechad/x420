# x420

One identity for every meme in the CHAD ecosystem, plus a lineage record saying who made it,
what it came from, and how value owed to it should be divided.

**Read [`SPEC.md`](./SPEC.md) first.** This README covers the code; the spec covers the
design and the reasoning behind it.

---

## The idea in one paragraph

Five CHAD apps exist and each identifies memes differently — chadstash by slug, memecraft by
UUID, chadpad by token address, chad smash by filename, chad brain by Telegram file id. Only
one pair of them talks. x420 gives all five a identifier they can compute independently from
image bytes alone, so a meme created in memecraft, posted by chad brain, and tokenized on
chadpad is recognisably the same meme in all three. Lineage rides along, and becomes money
at the one place the ecosystem controls: token issuance.

## Layout

### Which document answers what

Read in this order. Each assumes the one above it.

| Document | Answers | Read it when |
|---|---|---|
| [`SPEC.md`](./SPEC.md) | *What is the standard?* Identity derivation, record schema, provenance tiers, split resolution. | Implementing anything that produces or consumes a record. |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | *How do the five apps compose?* Roles, topology, trust model, where $CHAD captures value. | Deciding how your app fits, or changing a boundary between apps. |
| [`PLAN.md`](./PLAN.md) | *What gets built, in what order?* Phased tasks with dependencies and open blockers. | Picking up work. |
| [`PUSH.md`](./PUSH.md) | *What ships next?* The active push to the first mainnet lineage launch — scope, interface contracts, dispatchable work orders. | **Start here if you are implementing right now.** |

`SPEC.md` is normative — if it disagrees with anything else, including this README, it wins.
The other two are explanatory and will drift faster.

Per-repo integration notes live in each consuming repo as `X420.md` (`docs/X420.md` in
memecraft). Those are written for a developer who can only see that one repo.

### Hooks

```bash
sh scripts/hooks/install.sh
```

`.git/hooks` is not version controlled, so re-run this after cloning. The pre-commit hook:

- **blocks** when `scripts/selfcheck.py` fails — invariants this repo controls, where a
  regression would misroute money in five downstream apps;
- **reports** cross-repo blocker status without ever failing the commit, since work
  outstanding in another repo is not a reason to refuse a docs change here.

Run the invariants directly with `python3 scripts/selfcheck.py`. Two of them are regressions
for bugs that actually shipped: non-portable dust tie-breaking, and treating `unknown`
provenance as a verified original.

### Checking what has actually landed

```bash
python3 scripts/status.py             # every phase
python3 scripts/status.py --blockers  # only what gates mainnet
```

Every check is a predicate over real files in the five repos, so the answer is observed
rather than remembered. Exit code is non-zero while any mainnet blocker is unmet.

This exists because cross-repo status kept in prose fails silently: two blockers were
believed complete while untouched in both repos. Repo paths override via `MEMECRAFT_DIR`,
`CHADPAD_DIR`, `CHADSTASH_DIR`, `CHADBRAIN_DIR`, `CHADSMASH_DIR`.

### Code

| Path | What it is |
|---|---|
| `x420/identity.py` | Canonical id derivation. Every app must match this exactly. |
| `x420/lineage.py` | Record schema, split resolution, ancestry walk. |
| `x420/store.py` | A three-deep example chain used to exercise resolution. |
| `app.py` | x402-gated reference server. Working; not part of the current scope — see below. |

A TypeScript port lives in `memecraft/src/lib/x420-lineage.ts`. **These two must not
diverge** — they already did once, over how dust is assigned when two payees tie. Publishing
both as shared packages with conformance vectors is `ARCHITECTURE.md §5`.

## Identity

```python
from x420.identity import meme_id

meme_id(rendered_bytes)   # "x420:9f86d081884c7d659a2feaa0c55ad015"
```

SHA-256 of the artifact's exact bytes, truncated to 128 bits. No chain segment — $CHAD is
deployed on three chains, so chain-scoping would give one meme three identities.

Exact bytes only. A re-encoded image is a different id by design; catching that case is a
perceptual hash's job, and its output is a suggestion for review, never a payout decision.

## Splits

```python
from x420.lineage import resolve_splits
from x420.store import MEMES, REACTION

resolve_splits(REACTION.id, MEMES)
# {'0x4444…': 8500, '0x2222…': 945, '0x3333…': 405, '0x1111…': 150}
```

Each parent carves its `royalty_bps` off the top, recursively; the remainder is split among
the current meme's attribution. Always sums to exactly 10000 basis points.

## Running it

```bash
.venv/bin/python -c "
from x420.store import MEMES, REACTION
from x420.lineage import resolve_splits, ancestry
print(resolve_splits(REACTION.id, MEMES))
print(ancestry(REACTION.id, MEMES))
"
```

## On `app.py` and x402

`app.py` is a working reference server that gates a meme behind HTTP 402 using the x402
protocol, settling in USDC on Base Sepolia. It runs, and returns valid payment requirements.

**x420 is x402-native by design, and this is deliberately sequenced after lineage payouts.**
The current effort builds identity and lineage; a paid *licensing* surface is the intended
next initiative, documented in `SPEC.md` §9.

The distinction matters: paying to **see** a meme fights the medium and is not the plan.
Paying to **use** one commercially, with the payment split across its lineage, is — and
`LineageSplitter` is revenue-source agnostic, so those payments can settle to the same
contract that receives chadpad's launch fees.

To run it anyway:

```bash
X420_PAY_TO=0xYourWallet .venv/bin/uvicorn app:app --port 8420
curl localhost:8420/catalog                    # free discovery
curl -i localhost:8420/meme/x420:9f86d081884c7d659a2feaa0c55ad015   # 402
```

Payment requirements arrive base64-encoded in the `payment-required` header, not the body.

## Status

Run `python3 scripts/status.py` for the current state — this section is a summary and will
drift.

Shipped:

- **`LineageSplitter.sol`** (chadpad) — immutable payout contract letting lineage earn from a
  launch's fee stream without redeploying any live mainnet contract. 15 tests.
- **memecraft** — `x420_id` and full `content_sha256` persisted server-side over served bytes;
  `GET /api/x420/{id}/splits` resolving lineage and signing the response (EIP-712).
- **chadpad** — splitter deployed in the launch flow, `creator` resolved to the human at index
  time, provenance gated to `attested`.

**Active push:** [`PUSH.md`](./PUSH.md) — first mainnet lineage launch. Three blockers left,
all in chadpad: consume the real anchor, verify the signature, and test the integration path.

**Two architectural decisions remain open** and block later phases: where $CHAD demand lives
once publishing is decoupled from minting, and challenge adjudication for disputed origin
claims. Both are in `ARCHITECTURE.md §11`.
