#!/usr/bin/env python3
"""
Generate simulated multi-source AIOps logs as JSONL.

Each output line is a JSON object:
{
  "source_type": "linux|mysql|app_service|nginx|docker",
  "host": "...",
  "service": "...",
  "source_name": "...",
  "logs": ["one raw log line"]
}

Only Python standard library modules are used.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta


SIZES = {
    "small": 100,
    "medium": 5000,
    "large": 50000,
}


SCENARIOS = {
    "normal_mixed": {
        "anomaly_ratio": 0.00,
        "cluster_types": [],
        "normal_weights": {
            "linux": 0.22,
            "mysql": 0.18,
            "app_service": 0.26,
            "nginx": 0.24,
            "docker": 0.10,
        },
    },
    "ssh_bruteforce": {
        "anomaly_ratio": 0.16,
        "cluster_types": ["ssh_bruteforce"],
        "normal_weights": {
            "linux": 0.30,
            "mysql": 0.12,
            "app_service": 0.20,
            "nginx": 0.25,
            "docker": 0.13,
        },
    },
    "mysql_down": {
        "anomaly_ratio": 0.22,
        "cluster_types": ["mysql_down"],
        "normal_weights": {
            "linux": 0.12,
            "mysql": 0.30,
            "app_service": 0.30,
            "nginx": 0.18,
            "docker": 0.10,
        },
    },
    "app_db_error_spike": {
        "anomaly_ratio": 0.18,
        "cluster_types": ["app_db_spike"],
        "normal_weights": {
            "linux": 0.12,
            "mysql": 0.14,
            "app_service": 0.38,
            "nginx": 0.28,
            "docker": 0.08,
        },
    },
    "mixed_incident": {
        "anomaly_ratio": 0.32,
        "cluster_types": [
            "ssh_bruteforce",
            "mysql_down",
            "app_db_spike",
            "docker_restart",
            "nginx_500",
        ],
        "normal_weights": {
            "linux": 0.18,
            "mysql": 0.18,
            "app_service": 0.30,
            "nginx": 0.24,
            "docker": 0.10,
        },
    },
    "docker_restart": {
        "anomaly_ratio": 0.20,
        "cluster_types": ["docker_restart"],
        "normal_weights": {
            "linux": 0.14,
            "mysql": 0.12,
            "app_service": 0.24,
            "nginx": 0.20,
            "docker": 0.30,
        },
    },
    "noisy_mixed": {
        "anomaly_ratio": 0.10,
        "cluster_types": ["noise_warning", "nginx_500", "ssh_bruteforce"],
        "normal_weights": {
            "linux": 0.22,
            "mysql": 0.16,
            "app_service": 0.24,
            "nginx": 0.26,
            "docker": 0.12,
        },
    },
    "load_test_mixed": {
        "anomaly_ratio": 0.12,
        "cluster_types": ["load_test"],
        "normal_weights": {
            "linux": 0.10,
            "mysql": 0.14,
            "app_service": 0.36,
            "nginx": 0.40,
            "docker": 0.00,
        },
    },
}


HOSTS = {
    "linux": ["auth-01", "app-01", "app-02", "db-01", "web-01", "worker-01"],
    "mysql": ["db-01", "db-02"],
    "app_service": ["app-01", "app-02", "worker-01"],
    "nginx": ["web-01", "web-02"],
    "docker": ["app-01", "app-02", "web-01", "worker-01"],
}

APP_SERVICES = ["auth-api", "order-api", "payment-api", "inventory-api", "search-api", "billing-worker"]
DOCKER_SERVICES = ["api-gateway", "order-api", "payment-api", "redis-cache", "mysql-exporter", "billing-worker"]
MYSQL_DBS = ["orders", "payments", "inventory", "users", "billing"]

NORMAL_IPS = [
    "10.0.1.11",
    "10.0.1.12",
    "10.0.2.21",
    "10.0.2.22",
    "172.16.10.5",
    "172.16.10.6",
    "192.168.1.20",
    "192.168.1.21",
]
CLIENT_IPS = [
    "198.51.100.21",
    "198.51.100.22",
    "198.51.100.23",
    "203.0.113.31",
    "203.0.113.32",
    "203.0.113.33",
]
ATTACKER_IPS = [
    "45.83.120.17",
    "91.240.118.44",
    "185.220.101.12",
    "203.0.113.250",
    "198.51.100.240",
]
USERS = ["ubuntu", "deploy", "svc_app", "alice", "bob", "mysql", "nginx"]
INVALID_USERS = ["root", "admin", "test", "oracle", "guest", "postgres", "support"]
PATHS = ["/", "/login", "/api/orders", "/api/payments", "/api/inventory", "/api/search", "/static/app.js"]
USER_AGENTS = [
    "Mozilla/5.0",
    "curl/8.1.2",
    "Prometheus/2.48",
    "kube-probe/1.29",
    "ELB-HealthChecker/2.0",
]
CONTAINERS = [
    "api-gateway.1",
    "order-api.2",
    "payment-api.1",
    "redis-cache.1",
    "mysql-exporter.1",
    "billing-worker.1",
]
IMAGES = {
    "api-gateway.1": "registry.local/api-gateway:1.8.4",
    "order-api.2": "registry.local/order-api:2.3.1",
    "payment-api.1": "registry.local/payment-api:2.1.7",
    "redis-cache.1": "redis:7.2",
    "mysql-exporter.1": "prom/mysqld-exporter:v0.15",
    "billing-worker.1": "registry.local/billing-worker:1.4.9",
}


def weighted_choice(weight_map, rng):
    total = sum(weight_map.values())
    if total <= 0:
        return rng.choice(list(weight_map.keys()))
    point = rng.random() * total
    cumulative = 0.0
    for item, weight in weight_map.items():
        cumulative += weight
        if point <= cumulative:
            return item
    return next(reversed(weight_map))


def fmt_syslog(ts):
    return ts.strftime("%b %d %H:%M:%S")


def fmt_iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_nginx(ts):
    return ts.strftime("%d/%b/%Y:%H:%M:%S +0000")


def pid(rng):
    return rng.randint(1000, 65000)


def port(rng):
    return rng.randint(1024, 65535)


def trace_id(rng):
    return "%016x" % rng.getrandbits(64)


def request_id(rng):
    return "%08x" % rng.getrandbits(32)


def container_service(container):
    if container.startswith("api-gateway"):
        return "api-gateway"
    if container.startswith("order-api"):
        return "order-api"
    if container.startswith("payment-api"):
        return "payment-api"
    if container.startswith("redis-cache"):
        return "redis-cache"
    if container.startswith("mysql-exporter"):
        return "mysql-exporter"
    return "billing-worker"


def make_record(source_type, host, service, source_name, line):
    return {
        "source_type": source_type,
        "host": host,
        "service": service,
        "source_name": source_name,
        "logs": [line],
    }


def normal_linux(ts, rng):
    host = rng.choice(HOSTS["linux"])
    event = rng.choice(["ssh_success", "sudo_command", "cron_job", "systemd_started", "disk_ok"])
    user = rng.choice(USERS)
    if event == "ssh_success":
        line = (
            f"{fmt_syslog(ts)} {host} sshd[{pid(rng)}]: "
            f"Accepted publickey for {user} from {rng.choice(NORMAL_IPS)} port {port(rng)} ssh2"
        )
        source_name = "/var/log/auth.log"
        service = "sshd"
    elif event == "sudo_command":
        command = rng.choice(["/usr/bin/systemctl status nginx", "/usr/bin/journalctl -n 20", "/usr/bin/df -h"])
        line = (
            f"{fmt_syslog(ts)} {host} sudo: {user} : TTY=pts/{rng.randint(0, 4)} ; "
            f"PWD=/home/{user} ; USER=root ; COMMAND={command}"
        )
        source_name = "/var/log/auth.log"
        service = "sudo"
    elif event == "cron_job":
        command = rng.choice(["/usr/local/bin/rotate-metrics", "/usr/local/bin/backup-check", "/usr/bin/updatedb"])
        line = f"{fmt_syslog(ts)} {host} CRON[{pid(rng)}]: ({user}) CMD ({command})"
        source_name = "/var/log/syslog"
        service = "cron"
    elif event == "systemd_started":
        svc = rng.choice(["nginx.service", "docker.service", "node-exporter.service", "mysql.service"])
        line = f"{fmt_syslog(ts)} {host} systemd[1]: Started {svc}."
        source_name = "/var/log/syslog"
        service = "systemd"
    else:
        usage = rng.randint(41, 78)
        line = f"{fmt_syslog(ts)} {host} node-exporter[{pid(rng)}]: disk_check mount=/ usage_percent={usage} status=ok"
        source_name = "/var/log/syslog"
        service = "node-exporter"
    return make_record("linux", host, service, source_name, line)


def normal_mysql(ts, rng):
    host = rng.choice(HOSTS["mysql"])
    db = rng.choice(MYSQL_DBS)
    event = rng.choice(["connection_ok", "query_ok", "slow_query_normal", "checkpoint", "backup_success"])
    if event == "connection_ok":
        line = (
            f"{fmt_syslog(ts)} {host} mysqld[{pid(rng)}]: [Note] "
            f"Connection accepted user={rng.choice(USERS)} db={db} host={rng.choice(NORMAL_IPS)}"
        )
    elif event == "query_ok":
        line = (
            f"{fmt_syslog(ts)} {host} mysqld[{pid(rng)}]: [Note] "
            f"Query completed db={db} rows={rng.randint(1, 900)} latency_ms={rng.randint(2, 120)}"
        )
    elif event == "slow_query_normal":
        line = (
            f"{fmt_syslog(ts)} {host} mysqld[{pid(rng)}]: [Warning] "
            f"Slow query db={db} query_time={rng.uniform(0.8, 1.8):.3f}s rows_examined={rng.randint(1000, 9000)}"
        )
    elif event == "checkpoint":
        line = f"{fmt_syslog(ts)} {host} mysqld[{pid(rng)}]: [Note] InnoDB: page_cleaner flushed pages in {rng.randint(8, 80)} ms"
    else:
        line = f"{fmt_syslog(ts)} {host} mysql-backup[{pid(rng)}]: backup completed db={db} bytes={rng.randint(5000000, 90000000)}"
    return make_record("mysql", host, "mysql", "/var/log/mysql/error.log", line)


def normal_app(ts, rng):
    host = rng.choice(HOSTS["app_service"])
    service = rng.choice(APP_SERVICES)
    event = rng.choice(["request_ok", "db_query_ok", "cache_hit", "job_done"])
    if event == "request_ok":
        path = rng.choice(PATHS)
        line = (
            f"{fmt_iso(ts)} INFO service={service} host={host} trace_id={trace_id(rng)} "
            f"method=GET path={path} status=200 latency_ms={rng.randint(12, 240)}"
        )
    elif event == "db_query_ok":
        line = (
            f"{fmt_iso(ts)} INFO service={service} host={host} trace_id={trace_id(rng)} "
            f"db={rng.choice(MYSQL_DBS)} operation=select status=ok latency_ms={rng.randint(3, 110)}"
        )
    elif event == "cache_hit":
        line = (
            f"{fmt_iso(ts)} INFO service={service} host={host} trace_id={trace_id(rng)} "
            f"cache=redis key=feature:{rng.randint(1, 200)} result={rng.choice(['hit', 'miss'])}"
        )
    else:
        line = (
            f"{fmt_iso(ts)} INFO service={service} host={host} job_id={request_id(rng)} "
            f"event=job_completed duration_ms={rng.randint(200, 5000)}"
        )
    return make_record("app_service", host, service, f"/var/log/app/{service}.log", line)


def normal_nginx(ts, rng):
    host = rng.choice(HOSTS["nginx"])
    ip = rng.choice(CLIENT_IPS)
    path = rng.choice(PATHS)
    status = rng.choices([200, 201, 204, 301, 302, 404], weights=[55, 5, 8, 7, 6, 4], k=1)[0]
    upstream = "-" if path.startswith("/static") else rng.choice(["10.0.2.11:8080", "10.0.2.12:8080"])
    latency = rng.uniform(0.01, 0.35)
    line = (
        f"{ip} - - [{fmt_nginx(ts)}] \"GET {path} HTTP/1.1\" {status} {rng.randint(128, 120000)} "
        f"\"-\" \"{rng.choice(USER_AGENTS)}\" upstream=\"{upstream}\" request_time={latency:.3f}"
    )
    return make_record("nginx", host, "nginx", "/var/log/nginx/access.log", line)


def normal_docker(ts, rng):
    host = rng.choice(HOSTS["docker"])
    container = rng.choice(CONTAINERS)
    service = container_service(container)
    event = rng.choice(["health_healthy", "container_started", "image_pull", "container_info"])
    if event == "health_healthy":
        line = (
            f"{fmt_iso(ts)} dockerd[{pid(rng)}]: event=health_status status=healthy "
            f"container={container} image={IMAGES[container]}"
        )
    elif event == "container_started":
        line = (
            f"{fmt_iso(ts)} dockerd[{pid(rng)}]: event=start container={container} "
            f"image={IMAGES[container]} restart_count={rng.randint(0, 1)}"
        )
    elif event == "image_pull":
        line = f"{fmt_iso(ts)} dockerd[{pid(rng)}]: event=pull image={IMAGES[container]} status=up_to_date"
    else:
        line = f"{fmt_iso(ts)} containerd[{pid(rng)}]: container={container} log_level=info message=\"heartbeat ok\""
    return make_record("docker", host, service, "/var/log/docker/events.log", line)


def anomaly_ssh_bruteforce(ts, rng, ctx, seq):
    host = ctx["host"]
    ip = ctx["ip"]
    user = rng.choice(ctx["users"])
    action = rng.choice(["Failed password", "Invalid user"])
    if action == "Invalid user":
        line = f"{fmt_syslog(ts)} {host} sshd[{pid(rng)}]: Invalid user {user} from {ip} port {port(rng)}"
    else:
        line = (
            f"{fmt_syslog(ts)} {host} sshd[{pid(rng)}]: "
            f"Failed password for {user} from {ip} port {port(rng)} ssh2"
        )
    return make_record("linux", host, "sshd", "/var/log/auth.log", line)


def anomaly_mysql_down(ts, rng, ctx, seq):
    host = ctx["db_host"]
    service = rng.choice(ctx["services"])
    choice = rng.random()
    if choice < 0.55:
        line = (
            f"{fmt_syslog(ts)} {host} mysql-healthcheck[{pid(rng)}]: ERROR "
            f"connect mysql://{host}:3306 failed: Connection refused"
        )
        return make_record("mysql", host, "mysql", "/var/log/mysql/healthcheck.log", line)
    if choice < 0.78:
        app_host = rng.choice(HOSTS["app_service"])
        line = (
            f"{fmt_iso(ts)} ERROR service={service} host={app_host} trace_id={trace_id(rng)} "
            f"db_host={host}:3306 error=\"Connection refused\" retry={min(seq, 9)}"
        )
        return make_record("app_service", app_host, service, f"/var/log/app/{service}.log", line)
    if choice < 0.90:
        line = f"{fmt_syslog(ts)} {host} mysqld[{pid(rng)}]: [ERROR] Too many connections max_connections=300"
        return make_record("mysql", host, "mysql", "/var/log/mysql/error.log", line)
    web_host = rng.choice(HOSTS["nginx"])
    line = (
        f"{rng.choice(CLIENT_IPS)} - - [{fmt_nginx(ts)}] \"GET /api/orders HTTP/1.1\" 502 {rng.randint(64, 2048)} "
        f"\"-\" \"{rng.choice(USER_AGENTS)}\" upstream=\"10.0.2.11:8080\" request_time={rng.uniform(1.0, 3.5):.3f}"
    )
    return make_record("nginx", web_host, "nginx", "/var/log/nginx/access.log", line)


def anomaly_app_db_spike(ts, rng, ctx, seq):
    service = ctx["service"]
    app_host = ctx["app_host"]
    db_host = ctx["db_host"]
    choice = rng.random()
    if choice < 0.72:
        line = (
            f"{fmt_iso(ts)} ERROR service={service} host={app_host} trace_id={trace_id(rng)} "
            f"event=db_query_failed db_host={db_host}:3306 error=\"Connection refused\" "
            f"attempt={1 + (seq % 5)}"
        )
        return make_record("app_service", app_host, service, f"/var/log/app/{service}.log", line)
    if choice < 0.92:
        web_host = rng.choice(HOSTS["nginx"])
        path = rng.choice(["/api/orders", "/api/payments", "/api/inventory"])
        line = (
            f"{rng.choice(CLIENT_IPS)} - - [{fmt_nginx(ts)}] \"POST {path} HTTP/1.1\" 500 {rng.randint(128, 8192)} "
            f"\"-\" \"{rng.choice(USER_AGENTS)}\" upstream=\"10.0.2.12:8080\" request_time={rng.uniform(0.8, 4.8):.3f}"
        )
        return make_record("nginx", web_host, "nginx", "/var/log/nginx/access.log", line)
    line = (
        f"{fmt_syslog(ts)} {db_host} mysqld[{pid(rng)}]: [Warning] "
        f"Aborted connection {rng.randint(1000, 90000)} to db: '{rng.choice(MYSQL_DBS)}' "
        f"user: 'app' host: '{app_host}'"
    )
    return make_record("mysql", db_host, "mysql", "/var/log/mysql/error.log", line)


def anomaly_docker_restart(ts, rng, ctx, seq):
    host = ctx["host"]
    container = ctx["container"]
    service = container_service(container)
    choice = rng.random()
    if choice < 0.45:
        line = (
            f"{fmt_iso(ts)} dockerd[{pid(rng)}]: event=die container={container} "
            f"image={IMAGES[container]} exitCode=137 OOMKilled=true"
        )
    elif choice < 0.78:
        line = (
            f"{fmt_iso(ts)} dockerd[{pid(rng)}]: event=restart container={container} "
            f"image={IMAGES[container]} restart_count={seq + 1} reason=on-failure"
        )
    else:
        line = (
            f"{fmt_iso(ts)} dockerd[{pid(rng)}]: event=health_status status=unhealthy "
            f"container={container} failing_streak={seq + 1}"
        )
    return make_record("docker", host, service, "/var/log/docker/events.log", line)


def anomaly_nginx_500(ts, rng, ctx, seq):
    host = ctx["host"]
    upstream = ctx["upstream"]
    status = rng.choices([500, 502, 503, 504], weights=[50, 25, 15, 10], k=1)[0]
    path = rng.choice(["/api/orders", "/api/payments", "/api/search", "/api/inventory"])
    line = (
        f"{rng.choice(CLIENT_IPS)} - - [{fmt_nginx(ts)}] \"GET {path} HTTP/1.1\" {status} {rng.randint(64, 4096)} "
        f"\"-\" \"{rng.choice(USER_AGENTS)}\" upstream=\"{upstream}\" request_time={rng.uniform(1.2, 6.5):.3f}"
    )
    return make_record("nginx", host, "nginx", "/var/log/nginx/access.log", line)


def anomaly_noise_warning(ts, rng, ctx, seq):
    choice = rng.choice(["linux_disk_warn", "mysql_slow", "app_timeout", "nginx_404", "docker_unhealthy_once"])
    if choice == "linux_disk_warn":
        host = rng.choice(HOSTS["linux"])
        line = f"{fmt_syslog(ts)} {host} node-exporter[{pid(rng)}]: disk_check mount=/var usage_percent={rng.randint(82, 88)} status=warning"
        return make_record("linux", host, "node-exporter", "/var/log/syslog", line)
    if choice == "mysql_slow":
        host = rng.choice(HOSTS["mysql"])
        line = (
            f"{fmt_syslog(ts)} {host} mysqld[{pid(rng)}]: [Warning] "
            f"Slow query db={rng.choice(MYSQL_DBS)} query_time={rng.uniform(2.0, 4.2):.3f}s rows_examined={rng.randint(20000, 80000)}"
        )
        return make_record("mysql", host, "mysql", "/var/log/mysql/error.log", line)
    if choice == "app_timeout":
        host = rng.choice(HOSTS["app_service"])
        service = rng.choice(APP_SERVICES)
        line = (
            f"{fmt_iso(ts)} WARN service={service} host={host} trace_id={trace_id(rng)} "
            f"event=downstream_timeout target=cache timeout_ms={rng.randint(800, 1500)}"
        )
        return make_record("app_service", host, service, f"/var/log/app/{service}.log", line)
    if choice == "nginx_404":
        host = rng.choice(HOSTS["nginx"])
        line = (
            f"{rng.choice(CLIENT_IPS)} - - [{fmt_nginx(ts)}] \"GET /wp-login.php HTTP/1.1\" 404 {rng.randint(128, 2048)} "
            f"\"-\" \"{rng.choice(USER_AGENTS)}\" upstream=\"-\" request_time={rng.uniform(0.01, 0.20):.3f}"
        )
        return make_record("nginx", host, "nginx", "/var/log/nginx/access.log", line)
    host = rng.choice(HOSTS["docker"])
    container = rng.choice(CONTAINERS)
    service = container_service(container)
    line = (
        f"{fmt_iso(ts)} dockerd[{pid(rng)}]: event=health_status status=unhealthy "
        f"container={container} failing_streak=1"
    )
    return make_record("docker", host, service, "/var/log/docker/events.log", line)


def anomaly_load_test(ts, rng, ctx, seq):
    choice = rng.random()
    service = ctx["service"]
    if choice < 0.48:
        host = rng.choice(HOSTS["nginx"])
        status = rng.choices([200, 200, 200, 429, 499], weights=[70, 10, 5, 10, 5], k=1)[0]
        line = (
            f"{rng.choice(CLIENT_IPS)} - - [{fmt_nginx(ts)}] \"GET {rng.choice(PATHS)} HTTP/1.1\" {status} {rng.randint(512, 200000)} "
            f"\"-\" \"k6-load-test/0.49\" upstream=\"10.0.2.12:8080\" request_time={rng.uniform(0.25, 2.5):.3f}"
        )
        return make_record("nginx", host, "nginx", "/var/log/nginx/access.log", line)
    if choice < 0.84:
        host = rng.choice(HOSTS["app_service"])
        line = (
            f"{fmt_iso(ts)} WARN service={service} host={host} trace_id={trace_id(rng)} "
            f"event=high_latency path={rng.choice(PATHS)} status=200 latency_ms={rng.randint(800, 4500)}"
        )
        return make_record("app_service", host, service, f"/var/log/app/{service}.log", line)
    host = rng.choice(HOSTS["mysql"])
    line = (
        f"{fmt_syslog(ts)} {host} mysqld[{pid(rng)}]: [Warning] "
        f"Slow query db={rng.choice(MYSQL_DBS)} query_time={rng.uniform(2.5, 8.5):.3f}s rows_examined={rng.randint(50000, 300000)}"
    )
    return make_record("mysql", host, "mysql", "/var/log/mysql/error.log", line)


ANOMALY_RENDERERS = {
    "ssh_bruteforce": anomaly_ssh_bruteforce,
    "mysql_down": anomaly_mysql_down,
    "app_db_spike": anomaly_app_db_spike,
    "docker_restart": anomaly_docker_restart,
    "nginx_500": anomaly_nginx_500,
    "noise_warning": anomaly_noise_warning,
    "load_test": anomaly_load_test,
}


NORMAL_RENDERERS = {
    "linux": normal_linux,
    "mysql": normal_mysql,
    "app_service": normal_app,
    "nginx": normal_nginx,
    "docker": normal_docker,
}


def new_cluster_context(cluster_type, rng):
    if cluster_type == "ssh_bruteforce":
        return {
            "host": rng.choice(["auth-01", "app-01", "web-01"]),
            "ip": rng.choice(ATTACKER_IPS),
            "users": rng.sample(INVALID_USERS, k=min(4, len(INVALID_USERS))),
        }
    if cluster_type == "mysql_down":
        return {
            "db_host": rng.choice(HOSTS["mysql"]),
            "services": rng.sample(APP_SERVICES, k=3),
        }
    if cluster_type == "app_db_spike":
        return {
            "app_host": rng.choice(HOSTS["app_service"]),
            "db_host": rng.choice(HOSTS["mysql"]),
            "service": rng.choice(["order-api", "payment-api", "inventory-api"]),
        }
    if cluster_type == "docker_restart":
        return {
            "host": rng.choice(HOSTS["docker"]),
            "container": rng.choice(CONTAINERS),
        }
    if cluster_type == "nginx_500":
        return {
            "host": rng.choice(HOSTS["nginx"]),
            "upstream": rng.choice(["10.0.2.11:8080", "10.0.2.12:8080"]),
        }
    if cluster_type == "load_test":
        return {
            "service": rng.choice(["order-api", "payment-api", "search-api"]),
        }
    return {}


def cluster_count_for(total, anomaly_count):
    if anomaly_count <= 0:
        return 0
    if total <= 100:
        avg_cluster_size = 6
    elif total <= 5000:
        avg_cluster_size = 15
    else:
        avg_cluster_size = 30
    return max(1, int(round(float(anomaly_count) / avg_cluster_size)))


def split_cluster_sizes(anomaly_count, cluster_count):
    base = anomaly_count // cluster_count
    remainder = anomaly_count % cluster_count
    sizes = []
    for index in range(cluster_count):
        sizes.append(base + (1 if index < remainder else 0))
    return sizes


def find_free_slot(plan, preferred):
    total = len(plan)
    for radius in range(total):
        right = preferred + radius
        if right < total and plan[right]["kind"] == "normal":
            return right
        left = preferred - radius
        if left >= 0 and plan[left]["kind"] == "normal":
            return left
    return None


def build_plan(scenario_name, total, rng):
    config = SCENARIOS[scenario_name]
    plan = [{"kind": "normal"} for _ in range(total)]
    anomaly_count = int(round(total * config["anomaly_ratio"]))
    cluster_types = config["cluster_types"]
    if anomaly_count <= 0 or not cluster_types:
        return plan

    clusters = cluster_count_for(total, anomaly_count)
    sizes = split_cluster_sizes(anomaly_count, clusters)
    segment = max(1, total // clusters)

    for cluster_index, size in enumerate(sizes):
        cluster_type = cluster_types[cluster_index % len(cluster_types)]

        # Keep noisy_mixed below strong thresholds more often by using shorter bursts.
        if scenario_name == "noisy_mixed":
            cluster_type = rng.choices(
                ["noise_warning", "nginx_500", "ssh_bruteforce"],
                weights=[70, 20, 10],
                k=1,
            )[0]

        density = 0.65
        window = max(size, int(size / density) + 1)
        window = min(total, window)
        segment_start = cluster_index * segment
        segment_end = min(total - 1, (cluster_index + 1) * segment - 1)
        latest_start = max(0, min(total - window, segment_end - window + 1))
        earliest_start = max(0, min(segment_start, latest_start))
        start = rng.randint(earliest_start, latest_start) if latest_start >= earliest_start else earliest_start

        candidates = list(range(start, min(total, start + window)))
        if len(candidates) < size:
            candidates = list(range(max(0, total - size), total))
        positions = sorted(rng.sample(candidates, k=min(size, len(candidates))))
        context = new_cluster_context(cluster_type, rng)

        for seq, pos in enumerate(positions):
            slot = pos if plan[pos]["kind"] == "normal" else find_free_slot(plan, pos)
            if slot is None:
                continue
            plan[slot] = {
                "kind": "anomaly",
                "cluster_type": cluster_type,
                "cluster_id": cluster_index,
                "seq": seq,
                "context": context,
            }

    return plan


def render_normal(ts, rng, scenario_name):
    source = weighted_choice(SCENARIOS[scenario_name]["normal_weights"], rng)
    return NORMAL_RENDERERS[source](ts, rng)


def render_anomaly(ts, rng, item):
    cluster_type = item["cluster_type"]
    return ANOMALY_RENDERERS[cluster_type](ts, rng, item["context"], item["seq"])


def generate_records(scenario_name, size_name, seed):
    rng = random.Random(seed)
    total = SIZES[size_name]
    plan = build_plan(scenario_name, total, rng)
    ts = datetime(2026, 1, 1, 0, 0, 0)

    for item in plan:
        if item["kind"] == "anomaly":
            ts += timedelta(seconds=rng.randint(1, 8))
            yield render_anomaly(ts, rng, item)
        else:
            ts += timedelta(seconds=rng.randint(3, 25))
            yield render_normal(ts, rng, scenario_name)


def write_jsonl(records, output_path):
    if output_path == "-":
        for record in records:
            sys.stdout.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        return

    directory = os.path.dirname(os.path.abspath(output_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Generate simulated AIOps multi-source logs as JSONL.")
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS.keys()))
    parser.add_argument("--size", required=True, choices=sorted(SIZES.keys()))
    parser.add_argument("--output", required=True, help="Output JSONL path. Use '-' for stdout.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    records = generate_records(args.scenario, args.size, args.seed)
    write_jsonl(records, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
