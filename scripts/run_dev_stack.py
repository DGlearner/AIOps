import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import request
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
LOG_INGEST_DIR = ROOT_DIR / "services" / "log_ingest"
RUNTIME_LOG_DIR = ROOT_DIR / "runtime_logs"


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    command: list[str]
    cwd: Path
    allow_clean_exit: bool = False


DEFAULT_SIMULATION_CONFIG = (
    LOG_INGEST_DIR / "datasets" / "stream" / "stream_sources.example.json"
)
DEFAULT_SIMULATION_ENDPOINT = "ws://localhost:8100/ws/ingest/logs"


def build_process_specs(
    *,
    python_executable: str,
    include_diagnosis_worker: bool = False,
) -> list[ProcessSpec]:
    specs = [
        ProcessSpec(
            name="log_ingest",
            command=[python_executable, "-m", "log_ingest.main"],
            cwd=LOG_INGEST_DIR,
        ),
        ProcessSpec(
            name="backend_api",
            command=[python_executable, "-m", "crossst.main"],
            cwd=BACKEND_DIR,
        ),
        ProcessSpec(
            name="parser_worker",
            command=[python_executable, "-m", "crossst.workers.parser_worker"],
            cwd=BACKEND_DIR,
        ),
        ProcessSpec(
            name="event_sink_worker",
            command=[python_executable, "-m", "crossst.workers.event_sink_worker"],
            cwd=BACKEND_DIR,
        ),
        ProcessSpec(
            name="detection_worker",
            command=[python_executable, "-m", "crossst.workers.detection_worker"],
            cwd=BACKEND_DIR,
        ),
        ProcessSpec(
            name="correlation_worker",
            command=[python_executable, "-m", "crossst.workers.correlation_worker"],
            cwd=BACKEND_DIR,
        ),
    ]
    if include_diagnosis_worker:
        specs.append(
            ProcessSpec(
                name="diagnosis_worker",
                command=[python_executable, "-m", "crossst.workers.diagnosis_worker"],
                cwd=BACKEND_DIR,
            )
        )
    return specs


def _format_seconds(value: float) -> str:
    float_value = float(value)
    if float_value.is_integer():
        return str(int(float_value))
    return str(value)


def build_simulation_spec(
    *,
    python_executable: str,
    config_path: Path,
    endpoint: str,
    duration_seconds: float | None,
    loop: bool,
) -> ProcessSpec:
    command = [
        python_executable,
        "-m",
        "scripts.simulate_log_clients",
        str(config_path),
        "--endpoint",
        endpoint,
    ]
    if loop:
        command.append("--loop")
    if duration_seconds is not None:
        command.extend(["--duration-seconds", _format_seconds(duration_seconds)])
    command.append("--pretty")

    return ProcessSpec(
        name="stream_simulator",
        command=command,
        cwd=LOG_INGEST_DIR,
        allow_clean_exit=True,
    )


def _process_env(spec: ProcessSpec) -> dict[str, str]:
    env = os.environ.copy()
    if spec.cwd == LOG_INGEST_DIR:
        src_path = LOG_INGEST_DIR / "src"
        env["PYTHONPATH"] = (
            str(src_path)
            if not env.get("PYTHONPATH")
            else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        )
    return env


def start_process(spec: ProcessSpec) -> subprocess.Popen:
    RUNTIME_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = RUNTIME_LOG_DIR / f"{spec.name}.out.log"
    stderr_path = RUNTIME_LOG_DIR / f"{spec.name}.err.log"
    stdout_file = stdout_path.open("a", encoding="utf-8")
    stderr_file = stderr_path.open("a", encoding="utf-8")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(
        spec.command,
        cwd=spec.cwd,
        env=_process_env(spec),
        stdout=stdout_file,
        stderr=stderr_file,
        creationflags=creationflags,
    )


def build_service_checks() -> dict[str, str]:
    return {
        "log_ingest": "http://localhost:8100/health",
        "backend_api": "http://localhost:8888/health",
    }


def build_service_port_checks() -> dict[str, tuple[str, int]]:
    checks = {}
    for name, url in build_service_checks().items():
        parsed = urlparse(url)
        if parsed.hostname and parsed.port:
            checks[name] = (parsed.hostname, parsed.port)
    return checks


def http_health_probe(url: str, timeout: float) -> bool:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except OSError:
        return False


def tcp_port_probe(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def find_occupied_service_ports(
    checks: dict[str, tuple[str, int]],
    *,
    probe=tcp_port_probe,
) -> list[str]:
    occupied = []
    for name, (host, port) in checks.items():
        if probe(host, port, 1.0):
            occupied.append(f"{name} {host}:{port}")
    return occupied


def wait_for_service(
    url: str,
    *,
    timeout_seconds: float,
    interval_seconds: float,
    probe=http_health_probe,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if probe(url, 1.0):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval_seconds)


def wait_for_services(
    checks: dict[str, str],
    *,
    timeout_seconds: float,
    interval_seconds: float = 1.0,
) -> bool:
    ready = True
    for name, url in checks.items():
        print(f"waiting for {name} {url}")
        if wait_for_service(
            url,
            timeout_seconds=timeout_seconds,
            interval_seconds=interval_seconds,
        ):
            print(f"{name} is healthy")
        else:
            print(f"{name} did not become healthy within {timeout_seconds:.0f}s")
            ready = False
    return ready


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.terminate()

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_dev_stack(
    *,
    include_diagnosis_worker: bool,
    health_check: bool,
    health_timeout_seconds: float,
    simulate_logs: bool = False,
    simulation_config_path: Path = DEFAULT_SIMULATION_CONFIG,
    simulation_endpoint: str = DEFAULT_SIMULATION_ENDPOINT,
    simulation_duration_seconds: float | None = 30.0,
    simulation_loop: bool = False,
    port_preflight: bool = True,
) -> int:
    specs = build_process_specs(
        python_executable=sys.executable,
        include_diagnosis_worker=include_diagnosis_worker,
    )
    processes: list[tuple[ProcessSpec, subprocess.Popen]] = []

    try:
        if port_preflight:
            occupied_ports = find_occupied_service_ports(build_service_port_checks())
            if occupied_ports:
                print("service ports are already in use:")
                for occupied_port in occupied_ports:
                    print(f"- {occupied_port}")
                print("stop the existing service first, or run with --no-port-preflight.")
                return 1

        for spec in specs:
            process = start_process(spec)
            processes.append((spec, process))
            print(f"started {spec.name} pid={process.pid}")

        print("dev stack is running. Press Ctrl+C to stop.")
        print(f"logs: {RUNTIME_LOG_DIR}")

        if health_check:
            if not wait_for_services(
                build_service_checks(),
                timeout_seconds=health_timeout_seconds,
            ):
                return 1

        if simulate_logs:
            simulation_spec = build_simulation_spec(
                python_executable=sys.executable,
                config_path=simulation_config_path,
                endpoint=simulation_endpoint,
                duration_seconds=simulation_duration_seconds,
                loop=simulation_loop,
            )
            process = start_process(simulation_spec)
            processes.append((simulation_spec, process))
            print(f"started {simulation_spec.name} pid={process.pid}")

        while True:
            for spec, process in processes:
                exit_code = process.poll()
                if exit_code is not None:
                    if spec.allow_clean_exit and exit_code == 0:
                        continue
                    print(f"{spec.name} exited with code {exit_code}")
                    return exit_code or 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("stopping dev stack...")
        return 0
    finally:
        for _, process in reversed(processes):
            stop_process(process)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run CrossST local development stack processes."
    )
    parser.add_argument(
        "--with-diagnosis-worker",
        action="store_true",
        help="Also start diagnosis_worker. This may call LLM depending on env flags.",
    )
    parser.add_argument(
        "--no-health-check",
        action="store_true",
        help="Do not wait for log-ingest and backend /health endpoints.",
    )
    parser.add_argument(
        "--no-port-preflight",
        action="store_true",
        help="Do not fail early when local service ports are already in use.",
    )
    parser.add_argument(
        "--health-timeout-seconds",
        type=float,
        default=30.0,
        help="Seconds to wait for each service health endpoint.",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="Start the WebSocket stream simulator after health checks pass.",
    )
    parser.add_argument(
        "--simulation-config",
        type=Path,
        default=DEFAULT_SIMULATION_CONFIG,
        help="Path to the stream simulator config JSON.",
    )
    parser.add_argument(
        "--simulation-endpoint",
        default=DEFAULT_SIMULATION_ENDPOINT,
        help="WebSocket endpoint used by the stream simulator.",
    )
    parser.add_argument(
        "--simulation-duration-seconds",
        type=float,
        default=30.0,
        help="Seconds to run the stream simulator. Use <= 0 with --simulation-loop for continuous streaming.",
    )
    parser.add_argument(
        "--simulation-loop",
        action="store_true",
        help="Loop over source log files while the stream simulator is running.",
    )
    args = parser.parse_args()
    simulation_duration_seconds = (
        None
        if args.simulation_duration_seconds <= 0
        else args.simulation_duration_seconds
    )

    raise SystemExit(
        run_dev_stack(
            include_diagnosis_worker=args.with_diagnosis_worker,
            health_check=not args.no_health_check,
            health_timeout_seconds=args.health_timeout_seconds,
            simulate_logs=args.simulate,
            simulation_config_path=args.simulation_config,
            simulation_endpoint=args.simulation_endpoint,
            simulation_duration_seconds=simulation_duration_seconds,
            simulation_loop=args.simulation_loop,
            port_preflight=not args.no_port_preflight,
        )
    )


if __name__ == "__main__":
    main()
