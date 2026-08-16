from __future__ import annotations

import time
import hashlib
import json

import httpx
from sqlalchemy.orm import Session

from app.services.ai_configuration_service import EffectiveAIConfiguration, effective_ai_configuration, record_ai_invocation


PLAN_SPEECH_PARAMETERS = {
    "speed": 1,
    "vol": 1,
    "pitch": 0,
    "format": "mp3",
    "sample_rate": 32000,
    "bitrate": 128000,
    "channel": 2,
}


def plan_audio_cache_hash(text: str, configuration: EffectiveAIConfiguration) -> str:
    payload = {
        "summary": text.strip()[:1200],
        "provider": configuration.provider_name,
        "base_url": configuration.base_url.rstrip("/"),
        "model": configuration.tts_model,
        "voice_id": configuration.tts_voice_id,
        **PLAN_SPEECH_PARAMETERS,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def synthesize_plan_summary(
    db: Session,
    *,
    user_id: int,
    text: str,
    configuration: EffectiveAIConfiguration | None = None,
) -> tuple[bytes, str]:
    """Synthesize only the persisted plan summary; never sends a resume or full plan."""
    configuration = configuration or effective_ai_configuration(db)
    if configuration is None or not configuration.tts_enabled:
        raise RuntimeError("管理员尚未启用语音朗读")
    summary = text.strip()[:1200]
    if not summary:
        raise RuntimeError("当前能力路线没有可朗读的摘要")
    endpoint = f"{configuration.base_url.rstrip('/')}/t2a_v2"
    started = time.perf_counter()
    try:
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {configuration.api_key}"},
            json={
                "model": configuration.tts_model,
                "text": summary,
                "stream": False,
                "voice_setting": {
                    "voice_id": configuration.tts_voice_id,
                    "speed": PLAN_SPEECH_PARAMETERS["speed"],
                    "vol": PLAN_SPEECH_PARAMETERS["vol"],
                    "pitch": PLAN_SPEECH_PARAMETERS["pitch"],
                },
                "audio_setting": {
                    "format": PLAN_SPEECH_PARAMETERS["format"],
                    "sample_rate": PLAN_SPEECH_PARAMETERS["sample_rate"],
                    "bitrate": PLAN_SPEECH_PARAMETERS["bitrate"],
                    "channel": PLAN_SPEECH_PARAMETERS["channel"],
                },
            },
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        base_response = payload.get("base_resp") or {}
        data = payload.get("data") or {}
        if int(base_response.get("status_code") or 0) != 0 or int(data.get("status") or 0) != 2:
            raise RuntimeError(str(base_response.get("status_msg") or "语音合成未完成"))
        audio_hex = str(data.get("audio") or "")
        if not audio_hex:
            raise RuntimeError("语音服务没有返回音频")
        audio = bytes.fromhex(audio_hex)
        usage_characters = int((payload.get("extra_info") or {}).get("usage_characters") or len(summary))
        record_ai_invocation(
            db,
            configuration,
            feature="target_plan_tts",
            modality="audio",
            model=configuration.tts_model,
            status="success",
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage_amount=usage_characters,
            usage_unit="characters",
            user_id=user_id,
        )
        return audio, "audio/mpeg"
    except Exception as exc:
        record_ai_invocation(
            db,
            configuration,
            feature="target_plan_tts",
            modality="audio",
            model=configuration.tts_model,
            status="failed",
            latency_ms=round((time.perf_counter() - started) * 1000),
            error_code=type(exc).__name__,
            user_id=user_id,
        )
        raise RuntimeError("语音朗读暂时不可用，请稍后重试") from exc
