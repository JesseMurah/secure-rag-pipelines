"""Your RAG Pipeline Is Leaking — PyCon Ghana 2026.

    uv run streamlit run app.py

Answers are kept in the transcript on purpose. When you switch persona and
ask the same question, the previous answer stays on screen above it — the
audience compares them without you having to say "remember what Kwame got".
"""

import streamlit as st

from pipeline.authz import escalate
from pipeline.rag import MODES, PERSONAS, SUGGESTED_QUESTIONS, answer

ESCALATION_AGENT = "ACC-003"
ESCALATION_USER = "kwame"

st.set_page_config(page_title="Secure RAG — PyCon Ghana", page_icon="🔒", layout="wide")

# Projector legibility. Terminal-sized type does not survive a big room.
st.markdown(
    """
    <style>
      html, body, [class*="st-"] { font-size: 17px; }
      .stChatMessage p { font-size: 1.05rem; line-height: 1.6; }
      code { font-size: 0.95rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_trace" not in st.session_state:
    st.session_state.last_trace = None
if "pending" not in st.session_state:
    st.session_state.pending = None


# ── sidebar: identity, mode, and the authorization decision ──────────

with st.sidebar:
    st.subheader("Logged in as")
    persona = st.selectbox(
        "persona",
        PERSONAS,
        format_func=lambda p: f"{p['label']} — {p['role']}",
        label_visibility="collapsed",
    )
    st.caption(
        "Standing in for your identity provider. In production this id comes "
        "from a verified token, never from the client."
    )

    st.subheader("Mode")
    mode = st.radio(
        "mode",
        [key for key, _ in MODES],
        format_func=lambda key: dict(MODES)[key],
        index=1,  # pre-filter
        label_visibility="collapsed",
    )

    st.divider()
    st.subheader("OpenFGA")
    trace = st.session_state.last_trace
    if trace is None:
        st.caption("Ask something to see the authorization decision.")
    else:
        st.code(trace["call"], language="text")
        st.metric("authorized records", trace["returned"], help=f"{trace['latency_ms']} ms")
        if trace.get("ids"):
            st.caption(" · ".join(trace["ids"]))

    st.divider()
    if st.button(
        f"Escalate {ESCALATION_AGENT} → {ESCALATION_USER.title()}",
        use_container_width=True,
        help="Writes ONE relationship tuple: user:kwame viewer agent:ACC-003",
    ):
        escalate(ESCALATION_AGENT, ESCALATION_USER)
        st.toast(f"Wrote: user:{ESCALATION_USER} viewer agent:{ESCALATION_AGENT}", icon="🔑")

    if st.button("Clear transcript", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_trace = None
        st.rerun()


# ── main pane ────────────────────────────────────────────────────────

st.title("Agent Credit Risk Assistant")
st.caption("20 mobile money agents · 4 territories · one shared vector index")

cols = st.columns(len(SUGGESTED_QUESTIONS))
for col, question in zip(cols, SUGGESTED_QUESTIONS):
    if col.button(question, use_container_width=True):
        st.session_state.pending = question

typed = st.chat_input("Ask about the agent portfolio…")
if typed:
    st.session_state.pending = typed


def render_cards(retrieved: list[dict]) -> None:
    if not retrieved:
        return
    st.caption(f"Retrieved {len(retrieved)} of 20 records — this is all the model saw")
    card_cols = st.columns(min(len(retrieved), 5))
    for col, doc in zip(card_cols, retrieved):
        col.markdown(
            f"**{doc['agent_id']}**  \n"
            f"{doc['territory'].title()}  \n"
            f"`{doc['risk_level']}` · {doc['missed_payments']} missed"
        )


for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "user":
            st.markdown(f"**{message['badge']}**")
            st.markdown(message["content"])
        else:
            st.markdown(message["content"])
            render_cards(message.get("retrieved", []))


# ── run the pipeline ─────────────────────────────────────────────────

question = st.session_state.pending
if question:
    st.session_state.pending = None
    badge = f"{persona['label']} · {dict(MODES)[mode]}"

    st.session_state.messages.append(
        {"role": "user", "content": question, "badge": badge}
    )
    with st.chat_message("user"):
        st.markdown(f"**{badge}**")
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Checking permissions, then retrieving…"):
                result = answer(user_id=persona["id"], question=question, mode=mode)
        except NotImplementedError as exc:
            st.warning(str(exc))
        else:
            st.session_state.last_trace = {**result.trace, "ids": result.authorized_ids}
            st.markdown(result.answer)
            render_cards(result.retrieved)
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": result.answer,
                    "retrieved": result.retrieved,
                }
            )
            st.rerun()  # refresh the sidebar trace
