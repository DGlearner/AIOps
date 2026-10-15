from datetime import datetime, timezone

from crossst.infrastructure.storage.alerts import (
    ALERT_LIFECYCLE_KEY,
    build_alert_lifecycle,
    build_alert_lifecycle_update,
    get_alert_lifecycle,
    summarize_alert_lifecycles,
)


def test_get_alert_lifecycle_defaults_to_open():
    lifecycle = get_alert_lifecycle({})

    assert lifecycle["status"] == "open"
    assert lifecycle["owner"] is None
    assert lifecycle["history"] == []


def test_build_alert_lifecycle_update_merges_status_owner_and_history():
    now = datetime(2026, 6, 5, 8, 0, tzinfo=timezone.utc)
    fields = {
        "src_ip": "8.8.8.8",
        ALERT_LIFECYCLE_KEY: build_alert_lifecycle(
            status="open",
            owner=None,
            updated_by="system",
            note="created",
            updated_at=now,
        ),
    }

    updated = build_alert_lifecycle_update(
        fields,
        status="acknowledged",
        owner="ops-user",
        updated_by="ops-user",
        note="确认处理中",
        updated_at=now,
    )

    assert updated["src_ip"] == "8.8.8.8"
    lifecycle = updated[ALERT_LIFECYCLE_KEY]
    assert lifecycle["status"] == "acknowledged"
    assert lifecycle["owner"] == "ops-user"
    assert lifecycle["updated_by"] == "ops-user"
    assert lifecycle["note"] == "确认处理中"
    assert lifecycle["history"][-1] == {
        "status": "acknowledged",
        "owner": "ops-user",
        "updated_by": "ops-user",
        "note": "确认处理中",
        "updated_at": now.isoformat(),
    }


def test_summarize_alert_lifecycles_counts_status_and_severity():
    class AlertRecord:
        def __init__(self, severity, fields):
            self.severity = severity
            self.fields = fields

    alerts = [
        AlertRecord("high", {}),
        AlertRecord(
            "medium",
            {
                ALERT_LIFECYCLE_KEY: {
                    "status": "acknowledged",
                    "owner": "ops-user",
                    "history": [],
                }
            },
        ),
        AlertRecord(
            "high",
            {
                ALERT_LIFECYCLE_KEY: {
                    "status": "false_positive",
                    "owner": "ops-user",
                    "history": [],
                }
            },
        ),
    ]

    summary = summarize_alert_lifecycles(alerts)

    assert summary["total"] == 3
    assert summary["by_status"] == {
        "open": 1,
        "acknowledged": 1,
        "false_positive": 1,
    }
    assert summary["by_severity"] == {
        "high": 2,
        "medium": 1,
    }

