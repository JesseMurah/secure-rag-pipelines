"""OpenFGA client.

Synchronous on purpose. Streamlit re-runs the whole script on every
interaction and does not own an event loop you can safely reuse, so the
async client turns into a fight over loops. `openfga_sdk.sync` avoids
the entire problem.
"""

import os

from dotenv import load_dotenv
from openfga_sdk import ClientConfiguration
from openfga_sdk.sync import OpenFgaClient

load_dotenv(override=True)


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Run `bash fga/bootstrap.sh` and paste the "
            f"printed values into .env"
        )
    return value


def fga_client() -> OpenFgaClient:
    """Build a client from .env. Caller is responsible for closing it,
    or use it as a context manager."""
    config = ClientConfiguration(
        api_url=os.getenv("FGA_API_URL", "http://localhost:8080"),
        store_id=_require("FGA_STORE_ID"),
        authorization_model_id=_require("FGA_MODEL_ID"),
    )
    return OpenFgaClient(config)
