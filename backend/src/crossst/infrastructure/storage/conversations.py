from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from crossst.domain.models.conversation import (
    ConversationMessage,
    ConversationSession,
    ConversationSummary,
)
from crossst.domain.schemas.conversations import (
    ConversationMessageRecord,
    ConversationSessionRecord,
    ConversationSummaryRecord,
)


def build_conversation_session_extra(
    conversation: ConversationSessionRecord,
) -> dict:
    extra = dict(conversation.metadata)
    if conversation.team_id is not None:
        extra["team_id"] = conversation.team_id
    return extra


def get_conversation_team_id(record) -> str | None:
    extra = getattr(record, "extra", None) or {}
    if not isinstance(extra, dict):
        return None
    team_id = extra.get("team_id")
    return str(team_id) if team_id is not None else None


async def save_conversation_session(
    session: AsyncSession,
    conversation: ConversationSessionRecord,
) -> None:
    session.add(
        ConversationSession(
            session_id=conversation.session_id,
            user_id=conversation.user_id,
            current_incident_id=conversation.current_incident_id,
            title=conversation.title,
            status=conversation.status,
            extra=build_conversation_session_extra(conversation),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )
    )
    await session.commit()


async def get_conversation_session(
    session: AsyncSession,
    session_id: str,
) -> ConversationSession | None:
    result = await session.execute(
        select(ConversationSession).where(ConversationSession.session_id == session_id)
    )
    return result.scalar_one_or_none()


def build_query_conversation_sessions_statement(
    *,
    user_id: str | None = None,
    team_id: str | None = None,
    incident_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> Select[tuple[ConversationSession]]:
    statement = select(ConversationSession).order_by(ConversationSession.updated_at.desc())

    if user_id is not None:
        statement = statement.where(ConversationSession.user_id == user_id)
    if team_id is not None:
        statement = statement.where(
            ConversationSession.extra.contains({"team_id": team_id})
        )
    if incident_id is not None:
        statement = statement.where(ConversationSession.current_incident_id == incident_id)
    if status is not None:
        statement = statement.where(ConversationSession.status == status)

    return statement.limit(limit)


async def query_conversation_sessions(
    session: AsyncSession,
    *,
    user_id: str | None = None,
    team_id: str | None = None,
    incident_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[ConversationSession]:
    statement = build_query_conversation_sessions_statement(
        user_id=user_id,
        team_id=team_id,
        incident_id=incident_id,
        status=status,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


def build_update_conversation_session_values(
    *,
    title: str | None = None,
    status: str | None = None,
    updated_at: datetime,
) -> dict:
    values = {"updated_at": updated_at}
    if title is not None:
        values["title"] = title
    if status is not None:
        values["status"] = status
    return values


async def update_conversation_session(
    session: AsyncSession,
    conversation: ConversationSession,
    *,
    title: str | None = None,
    status: str | None = None,
    updated_at: datetime,
) -> None:
    values = build_update_conversation_session_values(
        title=title,
        status=status,
        updated_at=updated_at,
    )
    for key, value in values.items():
        setattr(conversation, key, value)
    await session.commit()


async def save_conversation_message(
    session: AsyncSession,
    message: ConversationMessageRecord,
) -> None:
    session.add(
        ConversationMessage(
            message_id=message.message_id,
            session_id=message.session_id,
            incident_id=message.incident_id,
            role=message.role,
            content=message.content,
            extra=message.metadata,
            created_at=message.created_at,
        )
    )
    await session.commit()


def build_query_conversation_messages_statement(
    *,
    session_id: str,
    before_created_at: datetime | None = None,
    newest_first: bool = False,
    limit: int = 100,
) -> Select[tuple[ConversationMessage]]:
    statement = (
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
    )
    if before_created_at is not None:
        statement = statement.where(ConversationMessage.created_at < before_created_at)

    if newest_first:
        statement = statement.order_by(ConversationMessage.created_at.desc())
    else:
        statement = statement.order_by(ConversationMessage.created_at.asc())

    return statement.limit(limit)


async def query_conversation_messages(
    session: AsyncSession,
    *,
    session_id: str,
    before_created_at: datetime | None = None,
    newest_first: bool = False,
    limit: int = 100,
) -> list[ConversationMessage]:
    statement = build_query_conversation_messages_statement(
        session_id=session_id,
        before_created_at=before_created_at,
        newest_first=newest_first,
        limit=limit,
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def save_conversation_summary(
    session: AsyncSession,
    summary: ConversationSummaryRecord,
) -> None:
    session.add(
        ConversationSummary(
            summary_id=summary.summary_id,
            session_id=summary.session_id,
            current_incident_id=summary.current_incident_id,
            known_facts=summary.known_facts,
            checked_tools=summary.checked_tools,
            hypotheses=summary.hypotheses,
            pending_actions=summary.pending_actions,
            compressed_context=summary.compressed_context,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            message_count=summary.message_count,
        )
    )
    await session.commit()


def build_update_conversation_summary_values(
    existing: ConversationSummary,
    summary: ConversationSummaryRecord,
) -> dict:
    return {
        "known_facts": summary.known_facts,
        "checked_tools": summary.checked_tools,
        "hypotheses": summary.hypotheses,
        "pending_actions": summary.pending_actions,
        "compressed_context": summary.compressed_context,
        "message_count": summary.message_count,
        "updated_at": summary.updated_at,
    }


async def update_conversation_summary(
    session: AsyncSession,
    existing: ConversationSummary,
    summary: ConversationSummaryRecord,
) -> None:
    values = build_update_conversation_summary_values(existing, summary)
    for key, value in values.items():
        setattr(existing, key, value)
    await session.commit()


async def get_latest_conversation_summary(
    session: AsyncSession,
    session_id: str,
) -> ConversationSummary | None:
    result = await session.execute(
        select(ConversationSummary)
        .where(ConversationSummary.session_id == session_id)
        .order_by(ConversationSummary.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()

