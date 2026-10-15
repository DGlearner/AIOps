import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_dev_stack import (  # noqa: E402
    BACKEND_DIR,
    DEFAULT_SIMULATION_CONFIG,
    DEFAULT_SIMULATION_ENDPOINT,
    LOG_INGEST_DIR,
    build_process_specs,
    build_service_port_checks,
    build_service_checks,
    build_simulation_spec,
    find_occupied_service_ports,
    wait_for_service,
)


def test_build_process_specs_starts_ingest_backend_and_core_workers():
    specs = build_process_specs(
        python_executable="python",
        include_diagnosis_worker=False,
    )

    names = [spec.name for spec in specs]

    assert names == [
        "log_ingest",
        "backend_api",
        "parser_worker",
        "event_sink_worker",
        "detection_worker",
        "correlation_worker",
    ]
    assert specs[0].cwd == LOG_INGEST_DIR
    assert specs[1].cwd == BACKEND_DIR
    assert specs[0].command == ["python", "-m", "log_ingest.main"]
    assert specs[2].command == ["python", "-m", "crossst.workers.parser_worker"]


def test_build_process_specs_can_include_diagnosis_worker():
    specs = build_process_specs(
        python_executable="python",
        include_diagnosis_worker=True,
    )

    assert specs[-1].name == "diagnosis_worker"
    assert specs[-1].command == ["python", "-m", "crossst.workers.diagnosis_worker"]


def test_build_simulation_spec_uses_default_stream_dataset():
    spec = build_simulation_spec(
        python_executable="python",
        config_path=DEFAULT_SIMULATION_CONFIG,
        endpoint=DEFAULT_SIMULATION_ENDPOINT,
        duration_seconds=30,
        loop=False,
    )

    assert spec.name == "stream_simulator"
    assert spec.cwd == LOG_INGEST_DIR
    assert spec.command == [
        "python",
        "-m",
        "scripts.simulate_log_clients",
        str(DEFAULT_SIMULATION_CONFIG),
        "--endpoint",
        DEFAULT_SIMULATION_ENDPOINT,
        "--duration-seconds",
        "30",
        "--pretty",
    ]


def test_build_simulation_spec_can_run_continuously():
    spec = build_simulation_spec(
        python_executable="python",
        config_path=DEFAULT_SIMULATION_CONFIG,
        endpoint=DEFAULT_SIMULATION_ENDPOINT,
        duration_seconds=None,
        loop=True,
    )

    assert "--loop" in spec.command
    assert "--duration-seconds" not in spec.command


def test_build_service_checks_targets_ingest_and_backend_health():
    checks = build_service_checks()

    assert checks == {
        "log_ingest": "http://localhost:8100/health",
        "backend_api": "http://localhost:8888/health",
    }


def test_build_service_port_checks_extracts_local_service_ports():
    checks = build_service_port_checks()

    assert checks == {
        "log_ingest": ("localhost", 8100),
        "backend_api": ("localhost", 8888),
    }


def test_find_occupied_service_ports_uses_probe():
    probed = []

    def probe(host: str, port: int, timeout: float) -> bool:
        probed.append((host, port, timeout))
        return port == 8888

    occupied = find_occupied_service_ports(
        {
            "log_ingest": ("localhost", 8100),
            "backend_api": ("localhost", 8888),
        },
        probe=probe,
    )

    assert occupied == ["backend_api localhost:8888"]
    assert probed == [
        ("localhost", 8100, 1.0),
        ("localhost", 8888, 1.0),
    ]


def test_wait_for_service_returns_true_when_probe_succeeds():
    attempts = []

    def probe(url: str, timeout: float) -> bool:
        attempts.append((url, timeout))
        return True

    assert wait_for_service(
        "http://localhost:8100/health",
        timeout_seconds=1,
        interval_seconds=0,
        probe=probe,
    )
    assert attempts == [("http://localhost:8100/health", 1.0)]


def test_wait_for_service_returns_false_after_timeout():
    attempts = []

    def probe(url: str, timeout: float) -> bool:
        attempts.append((url, timeout))
        return False

    assert not wait_for_service(
        "http://localhost:8100/health",
        timeout_seconds=0,
        interval_seconds=0,
        probe=probe,
    )
    assert attempts == [("http://localhost:8100/health", 1.0)]
