from __future__ import annotations

from nanorole_runtime.summaries import SummaryStore
from nanorole_runtime.storage import Database


def test_summary_store_upserts_latest_summary(tmp_path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = SummaryStore(database)

    first = store.upsert_summary(
        session_id="s1",
        covered_until_message_id="m1",
        summary="The user introduced a stable preference.",
    )
    second = store.upsert_summary(
        session_id="s1",
        covered_until_message_id="m2",
        summary="The user introduced a stable preference and set a boundary.",
    )

    latest = store.get_latest_summary("s1")

    assert first.summary_id == second.summary_id
    assert latest is not None
    assert latest.covered_until_message_id == "m2"
    assert latest.summary == "The user introduced a stable preference and set a boundary."
