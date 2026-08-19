"""Canonical x420 identity derivation.

This is the one piece every app in the ecosystem must implement identically. Any
divergence here silently splits a meme into two identities and breaks payouts, so the
derivation is deliberately trivial and dependency-free — it should be portable to
TypeScript, Python, or Solidity without interpretation.

See SPEC.md §2.
"""

from __future__ import annotations

import hashlib

PREFIX = "x420"
ID_HEX_CHARS = 32


def content_digest(rendered_bytes: bytes) -> str:
    """Full SHA-256 hex digest of the published artifact's exact bytes."""
    return hashlib.sha256(rendered_bytes).hexdigest()


def meme_id(rendered_bytes: bytes) -> str:
    """Canonical x420 id for an artifact.

    Input must be the bytes exactly as served — not the source project, not the layer
    data, and not a re-encode. A re-encoded image is a different id by design; detecting
    that case is the perceptual hash's job, never this function's.
    """
    return f"{PREFIX}:{content_digest(rendered_bytes)[:ID_HEX_CHARS]}"


def pixel_hash(width: int, height: int, rgba: bytes) -> str:
    """Digest of an image's decoded raster, ignoring its file wrapper.

    Sits between `meme_id` (file bytes — changes if a single metadata byte moves) and a
    perceptual hash (fuzzy, false positives). This one is exact but survives metadata
    injection, container changes, and lossless re-encoding — so two files whose pixels match
    can be linked as duplicates automatically, with no curator review. See SPEC.md §3.4.

    The raster must be 8-bit RGBA, row-major, top-left origin. Normalisation is not optional:
    the same PNG decoded as RGB rather than RGBA produces a different digest, so apps that
    disagree about colour mode will never match. Dimensions are folded into the payload so a
    2x1 and a 1x2 carrying the same byte run cannot collide.

    Takes a raster rather than a file so this module stays dependency-free; callers decode
    with whatever imaging library they already have.
    """
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError(
            f"expected {expected} bytes of 8-bit RGBA for {width}x{height}, got {len(rgba)}"
        )
    return hashlib.sha256(f"{width}x{height}|".encode() + rgba).hexdigest()


def meme_id_from_digest(digest: str) -> str:
    """Build an id from a digest computed elsewhere.

    Only safe when the digest was taken over the artifact *as served*, by a party trusted
    to have hashed the real bytes. A client-supplied digest is unverifiable, and because
    identity routes payouts a forgeable id is a forgeable cap table — prefer `meme_id` over
    the raw bytes wherever they are available.

    The trap is real rather than hypothetical: memecraft hashes its PNG client-side during
    export and then injects a metadata chunk, so that digest describes the pre-injection
    bytes and not the file anyone downloads.
    """
    normalized = digest.strip().lower()
    if len(normalized) != 64 or not all(c in "0123456789abcdef" for c in normalized):
        raise ValueError(f"expected a 64-character hex sha256 digest, got {digest!r}")
    return f"{PREFIX}:{normalized[:ID_HEX_CHARS]}"
