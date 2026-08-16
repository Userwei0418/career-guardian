from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import websockets
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from jose import jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_db
from app.models.opportunity_target import JobTarget, MockInterviewSession
from app.models.resume import ResumeVersion
from app.models.user import User
from app.schemas.mock_interview import MockInterviewSessionResponse, MockInterviewStartRequest, MockInterviewStartResponse
from app.services.ai_configuration_service import effective_ai_configuration, record_ai_invocation
from app.services.mock_interview_service import (
    build_interview_greeting,
    build_interview_instructions,
    finish_interview_review,
    rubric_version_for,
)


router = APIRouter()


def _response(db: Session, session: MockInterviewSession) -> MockInterviewSessionResponse:
    result = MockInterviewSessionResponse.model_validate(session)
    target = db.get(JobTarget, session.job_target_id)
    resume = db.get(ResumeVersion, session.resume_version_id) if session.resume_version_id else None
    result.job_snapshot = dict(target.job_snapshot or {}) if target else {}
    result.resume_display_name = resume.display_name if resume else None
    return result


def _ticket(session: MockInterviewSession) -> str:
    payload = {
        "sub": str(session.user_id),
        "session_id": session.id,
        "scope": "mock_interview_realtime",
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _ticket_payload(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload if payload.get("scope") == "mock_interview_realtime" else None
    except Exception:
        return None


@router.post("/targets/{target_id}/mock-interviews", response_model=MockInterviewStartResponse, status_code=status.HTTP_201_CREATED)
def start_mock_interview(
    target_id: int,
    request: MockInterviewStartRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.query(JobTarget).filter(JobTarget.id == target_id, JobTarget.user_id == user.id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="目标岗位不存在")
    if target.status != "target":
        raise HTTPException(status_code=409, detail="请先把岗位设为目标，再开始模拟面试")
    resume = db.query(ResumeVersion).filter(ResumeVersion.id == target.resume_version_id, ResumeVersion.user_id == user.id).first()
    if resume is None:
        raise HTTPException(status_code=409, detail="请先为目标岗位选择一份简历")
    configuration = effective_ai_configuration(db)
    if configuration is None or not configuration.realtime_enabled:
        raise HTTPException(status_code=503, detail="管理员尚未启用实时语音面试")
    session = MockInterviewSession(
        user_id=user.id,
        job_target_id=target.id,
        resume_version_id=resume.id,
        status="preparing",
        practice_type=request.practice_type,
        rubric_version=rubric_version_for(request.practice_type),
        interview_type=request.interview_type,
        difficulty=request.difficulty,
        planned_duration_minutes=5 if request.practice_type == "self_introduction" else request.planned_duration_minutes,
        target_duration_seconds=(request.target_duration_seconds or 60) if request.practice_type == "self_introduction" else None,
        model=configuration.realtime_model,
        voice_id=configuration.realtime_voice_id,
        agent_name=configuration.interview_agent_name,
        report={},
        transcript=[],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return MockInterviewStartResponse(
        session=_response(db, session),
        realtime_ticket=_ticket(session),
        websocket_path=f"/api/opportunity/mock-interviews/{session.id}/realtime",
    )


@router.get("/mock-interviews", response_model=list[MockInterviewSessionResponse])
def list_mock_interviews(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sessions = (
        db.query(MockInterviewSession)
        .filter(MockInterviewSession.user_id == user.id)
        .order_by(MockInterviewSession.created_at.desc(), MockInterviewSession.id.desc())
        .all()
    )
    return [_response(db, item) for item in sessions]


@router.get("/mock-interviews/{session_id}", response_model=MockInterviewSessionResponse)
def get_mock_interview(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(MockInterviewSession).filter(MockInterviewSession.id == session_id, MockInterviewSession.user_id == user.id).first()
    if session is None:
        raise HTTPException(status_code=404, detail="模拟面试记录不存在")
    return _response(db, session)


def _provider_websocket_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"wss://{parsed.netloc}/ws/v1/realtime/voice-dialog"


def _event_text(payload: dict) -> str:
    for key in ("text", "transcript", "delta"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        return _event_text(data)
    return ""


@router.websocket("/mock-interviews/{session_id}/realtime")
async def mock_interview_realtime(websocket: WebSocket, session_id: int, ticket: str = Query(default="")):
    payload = _ticket_payload(ticket)
    if payload is None or int(payload.get("session_id") or 0) != session_id:
        await websocket.close(code=4401, reason="会话凭证无效或已过期")
        return
    user_id = int(payload.get("sub") or 0)
    db = SessionLocal()
    try:
        session = db.query(MockInterviewSession).filter(MockInterviewSession.id == session_id, MockInterviewSession.user_id == user_id).first()
        if session is None or session.status != "preparing":
            await websocket.close(code=4409, reason="会话已开始或不存在")
            return
        target = db.query(JobTarget).filter(JobTarget.id == session.job_target_id, JobTarget.user_id == user_id).first()
        resume = db.query(ResumeVersion).filter(ResumeVersion.id == session.resume_version_id, ResumeVersion.user_id == user_id).first()
        configuration = effective_ai_configuration(db)
        if target is None or resume is None or configuration is None or not configuration.realtime_enabled:
            session.status = "failed"
            session.error_message = "实时语音配置、目标岗位或简历已不可用"
            db.commit()
            await websocket.close(code=1011, reason="实时语音暂时不可用")
            return
        previous_session = None
        if session.practice_type == "self_introduction":
            previous_session = (
                db.query(MockInterviewSession)
                .filter(
                    MockInterviewSession.user_id == user_id,
                    MockInterviewSession.job_target_id == session.job_target_id,
                    MockInterviewSession.practice_type == session.practice_type,
                    MockInterviewSession.rubric_version == session.rubric_version,
                    MockInterviewSession.target_duration_seconds == session.target_duration_seconds,
                    MockInterviewSession.status == "completed",
                    MockInterviewSession.id < session.id,
                )
                .order_by(MockInterviewSession.id.desc())
                .first()
            )
        instructions = build_interview_instructions(configuration, session, target, resume, previous_session)
        greeting = build_interview_greeting(configuration, session)
        provider_url = _provider_websocket_url(configuration.base_url)
        provider_key = configuration.api_key
        provider_model = configuration.realtime_model
        provider_voice = configuration.realtime_voice_id
        provider_feature = "self_introduction_realtime" if session.practice_type == "self_introduction" else "mock_interview_realtime"
    finally:
        db.close()

    await websocket.accept()
    transcript: list[dict[str, str]] = []
    started = time.monotonic()
    provider_status = "success"
    provider_error: str | None = None
    try:
        async with websockets.connect(
            provider_url,
            additional_headers={"Authorization": f"Bearer {provider_key}"},
            open_timeout=15,
            close_timeout=5,
            max_size=8 * 1024 * 1024,
        ) as provider:
            await provider.send(json.dumps({
                "type": "start",
                "model": provider_model,
                "voice": provider_voice,
                "instructions": instructions,
                "greeting": greeting,
                "input_audio_format": "pcm_s16le",
                "input_audio_sample_rate": 16000,
            }, ensure_ascii=False))
            live_db = SessionLocal()
            try:
                live_session = live_db.get(MockInterviewSession, session_id)
                if live_session:
                    live_session.status = "active"
                    live_session.started_at = datetime.now()
                    live_db.commit()
            finally:
                live_db.close()

            async def browser_to_provider() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        try:
                            await provider.send(json.dumps({"type": "end"}))
                        except Exception:
                            pass
                        return
                    if message.get("bytes") is not None:
                        await provider.send(message["bytes"])
                        continue
                    raw = message.get("text")
                    if not raw:
                        continue
                    try:
                        command = json.loads(raw)
                    except ValueError:
                        continue
                    command_type = command.get("type")
                    if command_type in {"commit", "cancel", "end"}:
                        await provider.send(json.dumps({"type": command_type}))
                    if command_type == "end":
                        return

            async def provider_to_browser() -> None:
                async for message in provider:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                        continue
                    try:
                        event = json.loads(message)
                    except ValueError:
                        continue
                    event_type = str(event.get("type") or "")
                    text = _event_text(event).strip()
                    if event_type == "user.transcript.done" and text:
                        transcript.append({"role": "user", "text": text})
                    elif event_type == "assistant.text.done" and text:
                        transcript.append({"role": "assistant", "text": text})
                    await websocket.send_json(event)
                    if event_type == "error":
                        raise RuntimeError(str(event.get("message") or "provider_error"))

            browser_task = asyncio.create_task(browser_to_provider())
            provider_task = asyncio.create_task(provider_to_browser())
            done, pending = await asyncio.wait({browser_task, provider_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        provider_status = "failed"
        provider_error = type(exc).__name__
        try:
            await websocket.send_json({"type": "error", "message": "实时语音连接中断，已保留本场逐字稿并尝试生成复盘。"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
        final_db = SessionLocal()
        try:
            finish_interview_review(
                session_id,
                user_id,
                transcript,
                final_db,
                failure_message=provider_error if provider_status == "failed" else None,
            )
            configuration = effective_ai_configuration(final_db)
            if configuration is not None:
                record_ai_invocation(
                    final_db,
                    configuration,
                    feature=provider_feature,
                    modality="realtime",
                    model=provider_model,
                    status=provider_status,
                    latency_ms=round((time.monotonic() - started) * 1000),
                    usage_amount=max(0, round(time.monotonic() - started)),
                    usage_unit="seconds",
                    error_code=provider_error,
                    user_id=user_id,
                )
        finally:
            final_db.close()
