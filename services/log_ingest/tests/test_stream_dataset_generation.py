from pathlib import Path

from scripts.generate_stream_dataset import (
    DEFAULT_SOURCE_SPECS,
    generate_stream_dataset,
)
from scripts.simulate_log_clients import load_config, load_lines


def test_default_stream_sources_cover_multiple_services():
    source_names = {source.name for source in DEFAULT_SOURCE_SPECS}

    assert source_names == {
        "linux-auth-prod",
        "linux-syslog-prod",
        "mysql-error-prod",
        "mysql-slow-query-prod",
        "app-login-service",
        "app-payment-service",
        "app-order-service",
    }


def test_generate_stream_dataset_creates_one_file_per_source(tmp_path):
    config_path = generate_stream_dataset(
        output_dir=tmp_path,
        lines_per_source=12,
    )

    config = load_config(config_path)

    assert len(config["sources"]) == len(DEFAULT_SOURCE_SPECS)
    for source in config["sources"]:
        log_file = Path(source["file"])
        assert log_file.exists()
        assert len(load_lines(log_file)) == 12


def test_generated_stream_dataset_contains_normal_and_signal_logs(tmp_path):
    config_path = generate_stream_dataset(
        output_dir=tmp_path,
        lines_per_source=20,
    )
    config = load_config(config_path)
    all_logs = []
    for source in config["sources"]:
        all_logs.extend(load_lines(Path(source["file"])))

    joined = "\n".join(all_logs).lower()

    assert "accepted publickey" in joined
    assert "failed password" in joined
    assert "ready for connections" in joined
    assert "too many connections" in joined
    assert "database connection refused" in joined
    assert "order created" in joined
