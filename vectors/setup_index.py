"""Create the Pinecone index.

Dimension is 1024 because that is voyage-4's default output size. It
cannot be changed after creation — if you get it wrong you delete the
index and start again. This is the one number in the whole demo that
is expensive to fix later.

    uv run python vectors/setup_index.py
"""

import os

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv(override=True)  # .env wins over exported shell vars

DIMENSION = 1024  # voyage-4 default
METRIC = "cosine"


def main() -> None:
    index_name = os.environ["PINECONE_INDEX_NAME"]
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])

    if pc.has_index(index_name):
        existing = pc.describe_index(index_name)
        if existing.dimension != DIMENSION:
            raise SystemExit(
                f"Index '{index_name}' exists with dimension {existing.dimension}, "
                f"but voyage-4 produces {DIMENSION}. Delete the index in the "
                f"Pinecone console and re-run this script."
            )
        print(f"Index '{index_name}' already exists at dimension {DIMENSION}.")
        return

    pc.create_index(
        name=index_name,
        dimension=DIMENSION,
        metric=METRIC,
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    print(f"Created index '{index_name}' — dimension {DIMENSION}, metric {METRIC}.")


if __name__ == "__main__":
    main()
