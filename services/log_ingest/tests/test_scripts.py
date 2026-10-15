from pathlib import Path

from scripts.send_sample_logs import load_jsonl
from scripts.simulate_log_clients import batch_lines, build_payload, load_config


def test_load_jsonl_reads_dataset(tmp_path):
    dataset = tmp_path / "payloads.jsonl"
    dataset.write_text(
        '{"source_type":"linux","logs":["log-1"]}\n'
        '{"source_type":"mysql","logs":["log-2"]}\n',
        encoding="utf-8",
    )

    payloads = load_jsonl(dataset)

    assert len(payloads) == 2
    assert payloads[0]["source_type"] == "linux"
    assert payloads[1]["logs"] == ["log-2"]


def test_stream_simulator_batches_log_lines():
    batches = batch_lines(["log-1", "log-2", "log-3"], batch_size=2)

    assert batches == [["log-1", "log-2"], ["log-3"]]


def test_stream_simulator_builds_ingest_payload_without_none_fields():
    payload = build_payload(
        {
            "source_type": "app_service",
            "source_name": "login-service.log",
            "host": None,
            "service": "login-service",
        },
        ["2026-06-03T14:04:22Z login-service ERROR database connection refused"],
    )

    assert payload == {
        "source_type": "app_service",
        "source_name": "login-service.log",
        "service": "login-service",
        "logs": ["2026-06-03T14:04:22Z login-service ERROR database connection refused"],
    }


def test_stream_simulator_resolves_log_files_relative_to_config(tmp_path):
    log_file = tmp_path / "linux_auth.log"
    log_file.write_text(
        "Jun  3 14:03:12 app-prod-01 sshd[2311]: Failed password for root from 8.8.8.8 port 52231 ssh2\n",
        encoding="utf-8",
    )
    config_file = tmp_path / "stream_sources.json"
    config_file.write_text(
        """
{
  "batch_size": 2,
  "sources": [
    {
      "name": "linux-auth",
      "source_type": "linux",
      "source_name": "auth.log",
      "file": "linux_auth.log"
    }
  ]
}
""",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert config["sources"][0]["file"] == str(log_file)


def test_stream_simulator_filters_disabled_sources(tmp_path):
    enabled_log = tmp_path / "enabled.log"
    disabled_log = tmp_path / "disabled.log"
    enabled_log.write_text("enabled log\n", encoding="utf-8")
    disabled_log.write_text("disabled log\n", encoding="utf-8")
    config_file = tmp_path / "stream_sources.json"
    config_file.write_text(
        """
{
  "sources": [
    {
      "name": "enabled-source",
      "source_type": "app_service",
      "file": "enabled.log",
      "enabled": true
    },
    {
      "name": "disabled-source",
      "source_type": "mysql",
      "file": "disabled.log",
      "enabled": false
    }
  ]
}
""",
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert [source["name"] for source in config["sources"]] == ["enabled-source"]
