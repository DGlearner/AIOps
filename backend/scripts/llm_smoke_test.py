import argparse
import asyncio
import json
from time import perf_counter
from typing import Any

from crossst.core.config import Settings, get_settings
from crossst.services.llm.chat import build_configured_langchain_chat_provider


def build_safe_llm_config_payload(settings: Settings) -> dict[str, Any]:
    return {
        "llm_enabled": settings.llm_enabled,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_api_key": "set" if settings.llm_api_key else "missing",
        "llm_base_url": "set" if settings.llm_base_url else "missing",
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "llm_timeout_seconds": settings.llm_timeout_seconds,
    }


def validate_llm_smoke_settings(settings: Settings) -> list[str]:
    errors: list[str] = []
    if not settings.llm_enabled:
        errors.append("LLM_ENABLED must be true")
    if not settings.llm_provider:
        errors.append("LLM_PROVIDER must be set")
    if not settings.llm_model:
        errors.append("LLM_MODEL must be set")
    if not settings.llm_api_key:
        errors.append("LLM_API_KEY is not set")
    return errors


def build_sample_inputs() -> dict[str, Any]:
    return {
        "question": "请基于当前证据，简短判断 login-service 登录失败是否可能由 MySQL 不可用导致。",
        "detected_intent": "diagnosis_summary",
        "diagnosis": {
            "diagnosis_id": "smoke-diagnosis-001",
            "incident_id": "smoke-incident-001",
            "root_cause": "mysql_or_database_dependency_unavailable",
            "summary": (
                "login-service 出现数据库连接错误，MySQL error log 同一时间窗口出现 "
                "connection refused。"
            ),
            "confidence": 0.76,
            "evidence_chain": [
                {
                    "event_type": "mysql_connection_refused",
                    "source": "mysql-error.log",
                    "count": 8,
                    "window": "5m",
                },
                {
                    "event_type": "app_db_connection_error",
                    "source": "login-service",
                    "count": 31,
                    "window": "5m",
                },
            ],
            "recommendations": [
                "检查 MySQL 进程状态。",
                "检查 login-service 数据库连接池恢复情况。",
            ],
        },
        "tool_calls": [
            {
                "tool_name": "query_events",
                "reason": "验证 MySQL 在登录失败窗口内是否出现连接拒绝。",
                "result_count": 8,
                "result_summary": "MySQL connection refused 在 5 分钟内出现 8 次。",
                "duration_ms": 18,
            }
        ],
        "rag_context": {
            "references": [
                {
                    "document_type": "runbook",
                    "source_id": "runbook-mysql-unavailable",
                    "title": "MySQL unavailable affects login-service",
                }
            ],
            "documents": [
                {
                    "document_type": "runbook",
                    "source_id": "runbook-mysql-unavailable",
                    "title": "MySQL unavailable affects login-service",
                    "content": (
                        "When login-service reports DB connection errors and MySQL "
                        "logs show connection refused, check MySQL process status, "
                        "error logs, and login-service connection pool recovery."
                    ),
                }
            ],
        },
        "memory_context": {
            "window_size": 12,
            "summary": {
                "known_facts": [
                    "登录失败和 MySQL 连接错误发生在同一 5 分钟窗口。",
                    "已有工具查询命中 MySQL connection refused。",
                ],
                "checked_tools": ["query_events"],
                "hypotheses": ["MySQL 不可用导致 login-service 登录失败"],
                "pending_actions": ["检查 MySQL 进程和连接池恢复"],
                "compressed_context": (
                    "user: 先看 login-service 登录失败是否和数据库有关。\n"
                    "assistant: 已发现数据库连接错误与登录失败时间重合。"
                ),
                "message_count": 2,
            },
            "recent_messages": [
                {
                    "role": "user",
                    "content": "刚刚 5 分钟内 login-service 登录失败明显升高。",
                    "created_at": "2026-06-05T10:00:00Z",
                },
                {
                    "role": "assistant",
                    "content": "需要结合 MySQL 错误日志确认是否有数据库不可用信号。",
                    "created_at": "2026-06-05T10:00:05Z",
                },
            ],
            "older_messages": [],
        },
    }


async def run_llm_smoke_test(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    config = build_safe_llm_config_payload(settings)
    errors = validate_llm_smoke_settings(settings)
    if errors:
        return {
            "status": "config_error",
            "config": config,
            "errors": errors,
        }

    provider, provider_error = build_configured_langchain_chat_provider(settings)
    if provider is None:
        return {
            "status": "provider_error",
            "config": config,
            "error": provider_error,
        }

    inputs = build_sample_inputs()
    started_at = perf_counter()
    reply = await provider.generate_chat_reply(**inputs)
    duration_ms = int((perf_counter() - started_at) * 1000)

    return {
        "status": "ok",
        "config": config,
        "duration_ms": duration_ms,
        "reply": reply,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Call the configured LangChain chat model once."
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    args = parser.parse_args()

    result = asyncio.run(run_llm_smoke_test())
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

