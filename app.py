from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from x402 import x402ResourceServer
from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import payment_middleware
from x402.mechanisms.evm.exact import register_exact_evm_server

from x420.lineage import BPS_TOTAL, ancestry, resolve_splits
from x420.store import MEMES

PAY_TO = os.environ["X420_PAY_TO"]
NETWORK = os.environ.get("X420_NETWORK", "eip155:84532")
PRICE = os.environ.get("X420_PRICE", "$0.0042")

facilitator = HTTPFacilitatorClient()
resource_server = x402ResourceServer(facilitator)
register_exact_evm_server(resource_server)

gate = payment_middleware(
    {
        "GET /meme/*": {
            "accepts": {
                "scheme": "exact",
                "payTo": PAY_TO,
                "price": PRICE,
                "network": NETWORK,
            }
        }
    },
    resource_server,
)

app = FastAPI(title="x420", version="0.1")


@app.middleware("http")
async def x402_gate(request, call_next):
    return await gate(request, call_next)


@app.get("/catalog")
async def catalog():
    """Free discovery: what exists, what it costs, what you may do with it."""
    return {
        "x420": "0.1",
        "price": PRICE,
        "network": NETWORK,
        "memes": [
            {
                "id": meme.id,
                "media_type": meme.content.media_type,
                "license": meme.license.model_dump(),
                "parents": [p.id for p in meme.parents],
            }
            for meme in MEMES.values()
        ],
    }


@app.get("/meme/{meme_id}")
async def meme(meme_id: str):
    """Payment-gated: content plus the provenance block that justifies the price."""
    record = MEMES.get(meme_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown meme")

    splits = resolve_splits(meme_id, MEMES)
    return {
        **record.model_dump(),
        "resolved": {
            "ancestry": ancestry(meme_id, MEMES),
            "splits_bps": splits,
            "total_bps": BPS_TOTAL,
        },
    }
