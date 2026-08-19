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
