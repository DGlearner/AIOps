from fastapi.testclient import TestClient

from log_ingest.app import app
from log_ingest.ingest import build_raw_log_messages
from log_ingest.schemas import IngestLogsRequest


def test_build_raw_log_messages_from_ingest_request():
    request = IngestLogsRequest(
        source_type="linux",
        source_name="auth.log",
        host="app-prod-01",
        logs=[
            "Jun  3 14:03:12 app-prod-01 sshd[2311]: "
            "Failed password for root from 1.2.3.4 port 52231 ssh2"
        ],
    )

    raw_logs = build_raw_log_messages(request)

    assert len(raw_logs) == 1
    assert raw_logs[0].source_type == "linux"
    assert raw_logs[0].source_name == "auth.log"
    assert raw_logs[0].host == "app-prod-01"
    assert raw_logs[0].log_id


def test_http_ingest_accepts_batch_and_publishes_to_raw_logs(monkeypatch):
    sent_messages = []

    async def fake_send_json_message(producer, *, topic, key=None, value):
        sent_messages.append(
            {
                "producer": producer,
                "topic": topic,
                "key": key,
                "value": value,
            }
        )

    monkeypatch.setattr("log_ingest.ingest.send_json_message", fake_send_json_message)
    app.state.kafka_producer = object()

    with TestClient(app) as client:
        response = client.post(
            "/ingest/logs",
            json={
                "source_type": "mysql",
                "source_name": "mysql-error.log",
                "host": "db-prod-01",
                "service": "mysql",
                "logs": [
                    "2026-06-03T14:04:02.123456Z 0 [ERROR] Can't connect to local MySQL server through socket",
                    "2026-06-03T14:04:03.123456Z 0 [ERROR] Too many connections",
                ],
            },
        )

    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "accepted"
    assert payload["topic"] == "raw_logs"
    assert payload["accepted"] == 2
    assert len(payload["log_ids"]) == 2
    assert len(sent_messages) == 2
    assert sent_messages[0]["topic"] == "raw_logs"


def test_websocket_ingest_accepts_batch_and_returns_ack(monkeypatch):
    sent_messages = []

    async def fake_send_json_message(producer, *, topic, key=None, value):
        sent_messages.append(
            {
                "producer": producer,
                "topic": topic,
                "key": key,
                "value": value,
            }
        )

    monkeypatch.setattr("log_ingest.ingest.send_json_message", fake_send_json_message)
    app.state.kafka_producer = object()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/ingest/logs") as websocket:
            websocket.send_json(
                {
                    "source_type": "linux",
                    "source_name": "auth.log",
                    "host": "app-prod-01",
                    "logs": [
                        "Jun  3 14:03:12 app-prod-01 sshd[2311]: Failed password for root from 8.8.8.8 port 52231 ssh2",
                        "Jun  3 14:03:13 app-prod-01 sshd[2312]: Failed password for root from 8.8.8.8 port 52232 ssh2",
                    ],
                }
            )
            ack = websocket.receive_json()

    assert ack["status"] == "accepted"
    assert ack["topic"] == "raw_logs"
    assert ack["accepted"] == 2
    assert len(ack["log_ids"]) == 2
    assert len(sent_messages) == 2


def test_health_reports_service_identity():
    app.state.kafka_producer = object()

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "CrossST Log Ingest"
