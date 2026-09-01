"""Put OpenFGA back to a known state.

Run this before every rehearsal and once more before you walk on stage.
The only thing the demo mutates is the escalation tuple, so that is the
only thing to undo — but "the only thing" is exactly the kind of
assumption that breaks a live demo, so this asserts the full expected
permission set afterwards.

    uv run python -m fga.reset
"""

from pipeline.authz import authorized_agent_ids, revoke

ESCALATION = ("ACC-003", "kwame")

EXPECTED = {
    "kwame": 5,   # Kumasi only
    "yaw": 5,     # Accra only
    "ama": 20,    # national, via one org tuple
}


def main() -> None:
    agent_id, user_id = ESCALATION
    revoke(agent_id, user_id)
    print(f"revoked  user:{user_id} viewer agent:{agent_id}")

    ok = True
    for user_id, expected_count in EXPECTED.items():
        result = authorized_agent_ids(user_id)
        status = "ok " if result.count == expected_count else "BAD"
        if result.count != expected_count:
            ok = False
        print(f"{status} {user_id:6s} sees {result.count:2d} agents (expected {expected_count})")

    if not ok:
        raise SystemExit(
            "\nPermission set is wrong. Re-seed with:\n"
            "  fga tuple write --store-id=$FGA_STORE_ID --file fga/tuples.yaml"
        )
    print("\nKnown-good state. Ready to rehearse.")


if __name__ == "__main__":
    main()
