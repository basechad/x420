# Work order — open a chadstash meme in memecraft's canvas

**Goal:** clicking *Remix on Memecraft* on a chadstash meme opens the editor with that
meme as the canvas background and its captions pre-filled as editable text.

**chadstash's half is already live.** The button ships today and links to a route memecraft
does not serve yet, so it currently lands on an empty studio.

---

## 1. What it does, and what it deliberately does not

This **composites**. The meme arrives as a background image with its original text still in
the pixels, and the user builds on top.

It does **not** hand over a blank template, because a flat render cannot be turned back into
layers. Three approaches were weighed:

| | Result | Coverage |
|---|---|---|
| match to a memecraft template | genuinely editable | **poor** — 85 templates against a long tail of formats |
| inpaint the text out | variable, artefacts where text sits on artwork | universal, real cost per image |
| **composite on top** | original text remains visible | **all 1184 memes, today** |

Template matching was considered and rejected: most memes fit no template, and a confident
wrong match is worse than no button. Do not quietly reintroduce it as "we'll just detect the
format" — the coverage problem is the whole objection.

**Say this in the UI.** A user who expects a blank template and gets their own text layered
over someone else's will read it as broken. "Build on this meme" sets the right expectation.

---

## 2. The link memecraft receives

```
https://memecraft.basedchad.com/studio?x420=x420:a393434574a137a3b21f3d77cd9bb7b4
```

Keyed by x420 id rather than an image URL on purpose: the id resolves to a record carrying
the artifact's URI **and** its digest, so the editor can verify what it loaded rather than
trusting a link someone pasted.

### Resolve it in two hops

**1. The record** — `GET https://api.chadstash.com/api/x420/{x420Id}`

```jsonc
{ "content": { "uri":    "https://api.chadstash.com/media/memes/bitcoin-only-not-your-keys.jpg",
               "sha256": "a393434574a137a3b21f3d77cd9bb7b48677a9e951952657ae5bb0c5756ba8a8",
               "media_type": "image/jpeg" },
  "origin":  { "app": "chadstash", "ref": "bitcoin-only-not-your-keys" } }
```

**2. The catalog entry** — `GET https://api.chadstash.com/api/memes/{origin.ref}`

`origin.ref` **is** the slug. That is what the field is for (SPEC §3), and it means no second
lookup table and no new endpoint:

```jsonc
{ "title": "Bitcoin Only, Not Your Keys",
  "width": 984, "height": 984,
  "text_in_image": "BITCOIN IS TOO EXPENSIVE NOW!\nI AM GOING TO BUY ALTCOINS INSTEAD.\n\nJUST BUY…",
  "launch_blocked": false }
```

`width`/`height` size the canvas before the image lands. `text_in_image` is the payoff: the
captions are already OCR'd, so the editor can pre-fill editable text layers with the original
wording and the user **edits the joke rather than retyping it**. That is most of the value of
this feature for the common case — a small variation on an existing meme.

---

## 3. Traps

**Load the image with `crossOrigin="anonymous"`.** Otherwise the canvas is *tainted* and
`toDataURL`/`toBlob` throws at export — the failure lands at the end of composing a meme,
reading as "the editor is broken" rather than as a header problem.

chadstash now serves `/media` with `Access-Control-Allow-Origin: *` specifically for this
(verified live from `memecraft.basedchad.com`), but the header only helps if the image is
requested as a CORS load. Without the attribute the browser fetches it normally and taints
the canvas anyway.

**`text_in_image` is not positioned.** It is a flat newline-separated transcript, not boxes.
Pre-fill the *content* of text layers; do not infer placement from it. Guessing coordinates and
landing them over the wrong panel is worse than putting them somewhere neutral and obvious.

**Route memecraft-origin ids to the existing remix path.** `origin.app` distinguishes them.
An id that memecraft produced should open `?remix={origin.ref}` — its own uuid, with real
`project_data` and actual layers — not come back through this lossy path.

**Respect `launch_blocked`.** chadstash hides the button for those memes, but a pasted URL
still reaches the studio. That flag is set for takedowns and rights complaints, and a reason
to stop someone tokenizing a meme is at least as good a reason to stop them deriving from it.

**Both endpoints are rate-limited per IP.** Server-side resolution is fine; a burst of
client-side calls from one address is not. An `X-API-Key` moves the caller onto its own bucket
if that ever bites.

---

## 4. Out of scope

- Removing the original text. See §1 — if this is ever wanted, it is inpainting, and it wants
  ten real memes tried before it is specified.
- Recording lineage. A meme built this way is a *new* meme; if it should carry the chadstash
  meme as an x420 parent, that is a separate decision with payout consequences and belongs in
  its own order.
- chadstash changes. Its side ships already.

---

## 5. Done when

- `/studio?x420=…` opens with the meme as canvas background, sized to `width`×`height`.
- Exporting produces a file — i.e. the canvas is not tainted.
- Text layers arrive pre-filled with the OCR'd captions and are editable.
- A memecraft-origin id opens the real `?remix=` path instead.
- A `launch_blocked` meme is refused rather than opened.
