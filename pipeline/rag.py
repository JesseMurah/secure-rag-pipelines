"""The RAG pipeline.

Three modes, one code path:

    no_authz     retrieve everything, answer from everything
    pre_filter   ask OpenFGA first, scope the vector search to the answer
    post_filter  retrieve everything, throw away what you shouldn't have

The only difference between them is *when* the authorization check runs
relative to the retrieval. That timing is the entire talk.
"""

import functools
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.documents import Document
from langchain_pinecone import PineconeVectorStore
from langchain_voyageai import VoyageAIEmbeddings
from pinecone import Pinecone

from pipeline.authz import authorized_agent_ids

# override=True: .env wins over whatever is already exported in the shell.
# Without it, a stale ANTHROPIC_API_KEY in your profile silently shadows the
# one in .env and you debug a 401 that has nothing to do with this file.
load_dotenv(override=True)

TOP_K = 5

EMBEDDING_MODEL = "voyage-4"
CHAT_MODEL = "claude-sonnet-5"

PERSONAS = [
    {"id": "kwame", "label": "Kwame Boateng", "role": "Field Officer — Kumasi"},
    {"id": "yaw", "label": "Yaw Mensah", "role": "Field Officer — Accra"},
    {"id": "ama", "label": "Ama Darko", "role": "Credit Risk Analyst — HQ"},
]

MODES = [
    ("no_authz", "No authorization"),
    ("pre_filter", "Pre-filter (ListObjects)"),
    ("post_filter", "Post-filter"),
]

SUGGESTED_QUESTIONS = [
    "Which agents are showing signs of default?",
    "What is the total loan exposure in my portfolio?",
    "Tell me about agent ACC-003.",
]

SYSTEM_PROMPT = """You are a credit risk assistant for a mobile money \
network in Ghana. Answer using only the agent records provided as context. \
If the context does not contain the answer, say so plainly — never guess at \
records you were not given. Be concise: name the agents, give the numbers \
that matter, and stop."""


@dataclass
class RagResult:
    answer: str
    authorized_ids: list[str]
    retrieved: list[dict] = field(default_factory=list)
    trace: dict = field(default_factory=dict)


# ── plumbing ─────────────────────────────────────────────────────────
# Each network hop lives in its own function so DEMO_CACHE can replace
# them without touching the pipeline logic.


@functools.lru_cache(maxsize=1)
def _vector_store() -> PineconeVectorStore:
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pc.Index(os.environ["PINECONE_INDEX_NAME"])
    embeddings = VoyageAIEmbeddings(model=EMBEDDING_MODEL)
    return PineconeVectorStore(index=index, embedding=embeddings)


@functools.lru_cache(maxsize=1)
def _llm() -> ChatAnthropic:
    # No temperature: sampling parameters were removed on Sonnet 5 and now
    # return a 400. Rehearsal-to-rehearsal determinism has to come from
    # DEMO_CACHE replaying recorded answers instead — the model can no
    # longer be pinned from here.
    return ChatAnthropic(model=CHAT_MODEL)


def _retrieve(question: str, allowed_ids: list[str] | None) -> list[Document]:
    """Vector search, optionally scoped to a set of document ids.

    `allowed_ids=None` means no scope — every record is a candidate.
    Passing a list turns it into a Pinecone metadata filter, which is
    where authorization meets retrieval. One line."""
    search_filter = {"agent_id": {"$in": allowed_ids}} if allowed_ids is not None else None
    return _vector_store().similarity_search(question, k=TOP_K, filter=search_filter)


def _generate(question: str, docs: list[Document]) -> str:
    if not docs:
        return "You do not have access to any agent records that answer this question."
    context = "\n\n".join(doc.page_content for doc in docs)
    response = _llm().invoke(
        [
            ("system", SYSTEM_PROMPT),
            ("human", f"Agent records:\n\n{context}\n\nQuestion: {question}"),
        ]
    )
    return response.content


def _cards(docs: list[Document]) -> list[dict]:
    return [
        {
            "agent_id": doc.metadata.get("agent_id"),
            "agent_name": doc.metadata.get("agent_name"),
            "territory": doc.metadata.get("territory"),
            "risk_level": doc.metadata.get("risk_level"),
            "missed_payments": doc.metadata.get("missed_payments"),
        }
        for doc in docs
    ]


# ── the pipeline ─────────────────────────────────────────────────────


def answer(user_id: str, question: str, mode: str = "pre_filter") -> RagResult:
    if mode == "no_authz":
        return _no_authz(user_id, question)
    if mode == "pre_filter":
        return _pre_filter(user_id, question)
    if mode == "post_filter":
        raise NotImplementedError(
            "Post-filter mode is phase 2. Use pre_filter or no_authz."
        )
    raise ValueError(f"unknown mode: {mode}")


def _no_authz(user_id: str, question: str) -> RagResult:
    """Standard RAG, as most tutorials teach it. No authorization
    anywhere. Every user gets every record."""
    docs = _retrieve(question, allowed_ids=None)
    return RagResult(
        answer=_generate(question, docs),
        authorized_ids=[],
        retrieved=_cards(docs),
        trace={
            "call": "— no authorization check —",
            "returned": "all 20 records are candidates",
            "latency_ms": 0,
        },
    )


def _pre_filter(user_id: str, question: str) -> RagResult:
    """Ask OpenFGA who this user can see, then scope the vector search
    to exactly those records. Similarity ranking happens *inside* the
    user's permission scope, so the top-k they get is the best k
    available to them."""
    authz = authorized_agent_ids(user_id)

    if not authz.authorized_ids:
        return RagResult(
            answer="You are not authorized to access any agent records.",
            authorized_ids=[],
            trace={"call": authz.call, "returned": 0, "latency_ms": authz.latency_ms},
        )

    docs = _retrieve(question, allowed_ids=authz.authorized_ids)

    return RagResult(
        answer=_generate(question, docs),
        authorized_ids=authz.authorized_ids,
        retrieved=_cards(docs),
        trace={
            "call": authz.call,
            "returned": authz.count,
            "latency_ms": authz.latency_ms,
        },
    )
