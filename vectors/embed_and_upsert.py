"""Embed the agent records and push them to Pinecone.

Vector ids are the agent ids themselves (KUM-001, not a uuid) so the
Pinecone contents line up with the OpenFGA object ids by eye. Handy
when something looks wrong at 6am the day of the talk.

    uv run python vectors/embed_and_upsert.py
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_pinecone import PineconeVectorStore
from langchain_voyageai import VoyageAIEmbeddings
from pinecone import Pinecone

load_dotenv(override=True)  # .env wins over exported shell vars

AGENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "agents.json"
EMBEDDING_MODEL = "voyage-4"


def main() -> None:
    agents = json.loads(AGENTS_FILE.read_text())

    docs = [
        Document(
            page_content=agent["text"],
            metadata={
                "agent_id": agent["agent_id"],
                "agent_name": agent["agent_name"],
                "territory": agent["territory"],
                "risk_level": agent["risk_level"],
                "missed_payments": agent["missed_payments"],
            },
        )
        for agent in agents
    ]

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(os.environ["PINECONE_INDEX_NAME"])

    store = PineconeVectorStore(index=index, embedding=VoyageAIEmbeddings(model=EMBEDDING_MODEL))
    store.add_documents(docs, ids=[a["agent_id"] for a in agents])

    print(f"Upserted {len(docs)} agent records to '{os.environ['PINECONE_INDEX_NAME']}'.")
    print("Pinecone indexes asynchronously — give it ~10 seconds before querying.")


if __name__ == "__main__":
    main()
