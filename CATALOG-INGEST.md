# Paired work order — memecraft publishes into the chadstash catalog

**Goal:** a meme published in memecraft becomes findable in chadstash search, carrying its x420
record intact so both registries answer identically for the same id.

Two repos have to agree on one payload. **Read §2 before writing code on either side** — the
last time an interface was left implicit, memecraft and chadpad ran on schema v3 while chadstash
signed v1, and every signature failed with an error that looked like a key mismatch.

---

## 1. Why this is not just an endpoint

memecraft captures a **title and nothing else**. `description` is explicitly set to `null` at
publish (`meme-publishing.ts:874`), there are no tags, and there is no "use case" field. The
only other text is `project_data`, which is layer geometry.

chadstash's search is built on exactly the thing memecraft does not have. From its CLAUDE.md:

> `use_cases` is the differentiator. A meme with a great image and no use cases is close to
> unfindable by intent.

So a meme forwarded as-is would be **invisible to the search it was sent to join**, and would not
publish anyway — ingest already refuses anything with fewer than two use cases
(`app/api/routes/admin.py:254`).

**chadstash enriches on receipt.** `enrich_to_draft` (`app/services.py:326`) already takes image
bytes and produces title, description, OCR text, use cases and tags from the vision model, saves
a draft, runs duplicate detection and stamps x420 identity. It is the admin upload path. Ingest
joins it rather than going around it.

The consequence is deliberate: **ingested memes land as drafts.** Curation stays the moat, the
two-use-case bar still gates publication, and a bulk feed cannot fill the catalog with entries
nobody can find. memecraft's `status: "published"` means published *in memecraft*; it is not a
claim on chadstash's catalog.

---

## 2. The payload — pinned

`POST /api/x420/records`, `multipart/form-data`, two parts:

| part | type | contents |
|---|---|---|
| `file` | binary | the exact served artifact, post-tEXt-injection |
| `record` | JSON | the x420 record below |

```jsonc
{
  "x420": "0.1",
  "id": "x420:9e4e1a4513029d8e43d85816198d6e6f",
  "content": {
    "uri": "ipfs://bafy…",
    "sha256": "9e4e1a4513029d8e43d85816198d6e6f…",   // full 64 hex, no 0x
    "media_type": "image/png"
  },
  "parents": [{ "id": "x420:…", "relation": "remix" }],
  "attribution": [
    { "address": "0x…creator…", "role": "creator", "share_bps": 10000 }
  ],
  "license": { "id": "x420-remix-1", "derivatives": true, "royalty_bps": 1500 },
  "provenance": "attested",
  "origin": { "app": "memecraft", "ref": "<memecraft meme uuid>" }
}
```

This is the `Meme` model from the `x420` package — **both sides import it, neither redefines
it.** chadstash already depends on the package (`x420 @ git+…@b308498`); memecraft should
validate against the same shape rather than hand-rolling the JSON.

`royalty_bps` is `1500` on both sides today (`memecraft/src/config/publishing.ts:25`,
`chadstash x420_royalty_bps`). It travels in the payload rather than being assumed, so a future
divergence is visible instead of silent.

---

## 3. chadstash — receive

**Verify the digest; never trust it.** Compute `sha256` over the bytes received and compare to
`content.sha256`. Mismatch is a 400. `x420/identity.py` is explicit about why:

> A client-supplied digest is unverifiable, and because identity routes payouts a forgeable id
> is a forgeable cap table.

**Store the record verbatim** — `provenance`, `attribution`, `parents`, `royalty_bps`, `origin`.
Do **not** let chadstash's own defaults touch it. This is a live trap in existing code:
`apply_x420_fields` fills attribution from config when it is empty, which would silently replace
memecraft's creator with the commons address and misroute every payout. Ingest sets the x420
columns from the record and calls only the identity/hash part of that helper.

**`attested` is accepted only from memecraft.** SPEC §3.1 defines the tier as *lineage observed
by the tool at creation time* — it is not earned by knowing a wallet, which is the `asserted`
tier. chadstash cannot observe memecraft's editor, so it is trusting the caller. That trust must
be bound to the authenticated origin: a generic write key that can claim `attested` is a way to
mint top-tier provenance for anything, and chadpad launches against that tier.

**Auth is a new credential.** `CHAD_API_KEYS` cannot be reused — it is documented as granting no
access, because everything it gates is public, and "a leaked key costs only quota". This is a
write. The admin break-glass token is too broad to hand to another service.

**Then enrich** through the existing path, landing a draft.

### Responses

| code | meaning | memecraft does |
|---|---|---|
| 201 | registered, draft created | record `chadstash_registered_at` |
| 200 | already registered, body is the existing record | same — this is a retry, not a failure |
| 400 | digest mismatch, malformed record, or unverifiable claim | do not retry; alert |
| 401/403 | bad or unscoped credential | do not retry; alert |
| 5xx | chadstash trouble | retry with backoff |

**200 rather than a bare 409 is deliberate.** memecraft's worker retries, so "already there" has
to be distinguishable from "rejected" by status alone, without parsing prose.

---

## 4. memecraft — send

Fire on publish finalize, **asynchronously**, using the existing queue-and-retry pattern from
`enqueueTelegramNotification` (`src/lib/telegram.ts:141-179`). A chadstash outage must never fail
a publish — the meme is published in memecraft either way.

Track `chadstash_registered_at`. Re-POST when a record changes: memecraft stays authoritative,
and chadstash's copy is a fallback that goes stale otherwise.

**Send the ancestry.** A remix carries parents, and chadstash's `load_store` walks them —
an ancestor it does not hold makes `/splits` return 409, which chadpad treats as *permanent*.
It rarely shows because chadpad asks memecraft first, but during a memecraft outage the fallback
would turn a transient failure into a launch refused forever. Either post ancestors first, or
accept that chadstash serves splits only for records whose whole chain it holds.

---

## 5. Duplicates

Three layers, and they behave differently for editor output than for imported memes.

**Byte-identity will not catch a re-export.** memecraft injects `exportId: randomUUID()` and a
timestamp after rendering, so the same meme exported twice has different bytes and a different
id — by design, as its own `docs/X420.md` warns. What `file_hash` *does* catch is a retried POST
of one export, which is the idempotency signal above. Return the existing record.

**`pixel_hash` is the layer that works.** Metadata injection does not touch pixels, so two
exports of one meme share a raster digest.

**But do not auto-link across creators.** `canonical_id` short-circuits everything — *"it is the
same work, so its payouts and its ancestry are the canonical record's."* Within chadstash's
imported catalog that is harmless, since everything resolves to commons. Across editor output,
where each meme names a different creator wallet, auto-linking pays the first person for the
second person's work.

> **Rule:** auto-link a pixel match only when both sides resolve to the same attribution.
> Otherwise flag it for review.

memecraft blunts this at source by rejecting a publish whose `visual_hash` already exists
(`meme-publishing.ts:544-550`), so a collision needs *different* project data rendering
identically — a layer nudged zero pixels, an equivalent font spec. Rare, and money-moving.

**A remix is not a duplicate.** memecraft remixes descend from existing memes and look similar by
construction. The embedding layer would flag every one. The record *declares* its parents, so
suppress duplicate flags against declared ancestors — otherwise the queue fills with legitimate
derivatives, and chadstash's own note applies: a queue that refills with rejected pairs
"becomes noise people ignore", after which real duplicates get dismissed alongside them.

---

## 6. Out of scope

- **chadstash does not become the payout authority for memecraft memes.** Both registries hold
  the same record and answer identically; chadpad asks memecraft first. The mirror exists so
  search works and so a lookup survives an outage.
- Publishing ingested memes automatically. They are drafts; a curator decides.
- Backfilling memecraft's existing catalog. Get the live path right first, then decide.

---

## 7. Done when

- Publishing in memecraft produces a chadstash draft with use cases, tags and OCR text, findable
  by intent rather than by title alone.
- The stored record matches what memecraft sent, field for field — attribution especially.
- Re-POSTing the same export returns 200 and creates nothing.
- A digest that disagrees with the bytes is refused.
- `attested` cannot be claimed by a credential that is not memecraft's.
- A remix does not raise a duplicate flag against its own parent.
- `GET /api/x420/{id}` on chadstash and on memecraft return the same attribution, provenance and
  royalty for the same id.
