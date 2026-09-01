"""The authorization layer.

Everything in here answers one question: which agent records is this
user allowed to see? Nothing in here knows about embeddings, vectors,
or language models — that separation is the point.
"""

import time
from dataclasses import dataclass

from openfga_sdk.client.models import (
    ClientListObjectsRequest,
    ClientTuple,
    ClientWriteRequest,
)

from fga.client import fga_client

AGENT_TYPE = "agent"
VIEWER = "viewer"

# OpenFGA reports "tuple already existed" and "tuple did not exist" under
# this one error code. Match the code, not the prose — the wording differs
# between server versions, the code does not. Both of the demo's write
# paths want the same thing: end state, not the transition.
ALREADY_IN_DESIRED_STATE = "write_failed_due_to_invalid_input"


@dataclass
class AuthzResult:
    """What the authorization layer decided, and how it decided it.
    The UI renders this verbatim in the sidebar — the audience should be
    able to see the decision before they see the answer."""

    authorized_ids: list[str]
    call: str
    latency_ms: int

    @property
    def count(self) -> int:
        return len(self.authorized_ids)


def authorized_agent_ids(user_id: str) -> AuthzResult:
    """One call to OpenFGA. Returns every agent this user can view.

    This is the pre-filter. It runs BEFORE the vector search, so the
    similarity query is scoped to documents the user is entitled to and
    ranking happens inside that scope.

    The naive alternative is a Check() per document:

        for agent_id in all_agents:          # 20 round trips here,
            if check(user, "viewer", agent): # 20,000 in production
                authorized.append(agent_id)

    ListObjects does it in one round trip because OpenFGA walks the
    relationship graph server-side. Same answer, one call.
    """
    started = time.perf_counter()

    with fga_client() as client:
        response = client.list_objects(
            ClientListObjectsRequest(
                user=f"user:{user_id}",
                relation=VIEWER,
                type=AGENT_TYPE,
            )
        )

    # OpenFGA returns fully-qualified ids: "agent:KUM-001"
    ids = sorted(obj.split(":", 1)[1] for obj in response.objects)

    return AuthzResult(
        authorized_ids=ids,
        call=f'ListObjects(user:{user_id}, "{VIEWER}", {AGENT_TYPE})',
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def escalate(agent_id: str, user_id: str) -> None:
    """Grant one user direct view access to one agent record.

    This is the live demo beat. It writes a single tuple:

        user:kwame  viewer  agent:ACC-003

    No new role, no schema change, no territory reassignment. One
    relationship, and a Kumasi field officer can see one Accra record.
    Idempotent — OpenFGA treats a duplicate write as already-satisfied.
    """
    tuple_ = ClientTuple(
        user=f"user:{user_id}", relation=VIEWER, object=f"{AGENT_TYPE}:{agent_id}"
    )
    with fga_client() as client:
        try:
            client.write(ClientWriteRequest(writes=[tuple_]))
        except Exception as exc:  # noqa: BLE001 - duplicate write is not an error here
            if ALREADY_IN_DESIRED_STATE not in str(exc):
                raise


def revoke(agent_id: str, user_id: str) -> None:
    """Undo escalate(). Called by reset.py so every rehearsal starts
    from the same known state."""
    tuple_ = ClientTuple(
        user=f"user:{user_id}", relation=VIEWER, object=f"{AGENT_TYPE}:{agent_id}"
    )
    with fga_client() as client:
        try:
            client.write(ClientWriteRequest(deletes=[tuple_]))
        except Exception as exc:  # noqa: BLE001 - absent tuple is the desired state
            if ALREADY_IN_DESIRED_STATE not in str(exc):
                raise
