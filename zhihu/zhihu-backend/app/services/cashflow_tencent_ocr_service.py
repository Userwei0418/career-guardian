from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.ai_configuration import AIInvocationLog
from app.models.user import User


TENCENT_OCR_FEATURE = "cashflow_tencent_ocr"
TENCENT_OCR_PROVIDER = "Tencent Cloud OCR"
TENCENT_OCR_MODEL = "GeneralAccurateOCR"
TENCENT_OCR_ENDPOINT = "ocr.tencentcloudapi.com"
TENCENT_OCR_MAX_IMAGE_BYTES = 10 * 1024 * 1024


class TencentOCRError(RuntimeError):
    def __init__(self, code: str, message: str, *, request_sent: bool = False):
        super().__init__(message)
        self.code = code
        self.user_message = message
        self.request_sent = request_sent


@dataclass(frozen=True)
class TencentOCRLine:
    text: str
    confidence: float | None
    polygon: list[dict[str, int]]


@dataclass(frozen=True)
class TencentOCRResult:
    text: str
    lines: list[TencentOCRLine]
    request_id: str | None
    provider_name: str = TENCENT_OCR_PROVIDER
    model: str = TENCENT_OCR_MODEL

    @property
    def average_confidence(self) -> float | None:
        values = [line.confidence for line in self.lines if line.confidence is not None]
        return round(sum(values) / len(values), 4) if values else None

    def line_positions(self) -> list[dict[str, Any]]:
        return [
            {
                "line_index": index,
                "confidence": line.confidence,
                "polygon": line.polygon,
            }
            for index, line in enumerate(self.lines, start=1)
        ]


def tencent_ocr_configured() -> bool:
    return bool(
        settings.TENCENT_OCR_ENABLED
        and (settings.TENCENT_OCR_SECRET_ID or "").strip()
        and (settings.TENCENT_OCR_SECRET_KEY or "").strip()
    )


def _month_start() -> datetime:
    now = datetime.utcnow()
    return datetime(now.year, now.month, 1)


def _monthly_call_count() -> int:
    with SessionLocal() as db:
        return int(
            db.query(func.count(AIInvocationLog.id))
            .filter(
                AIInvocationLog.feature == TENCENT_OCR_FEATURE,
                AIInvocationLog.created_at >= _month_start(),
                AIInvocationLog.usage_amount.isnot(None),
            )
            .scalar()
            or 0
        )


def _safe_error_code(exc: Exception) -> str:
    raw_code = getattr(exc, "code", None)
    if raw_code:
        return re.sub(r"[^0-9A-Za-z_.-]+", "_", str(raw_code))[:100]
    return type(exc).__name__[:100]


def _record_invocation(
    *,
    user_id: int,
    expected_data_epoch: int | None,
    status: str,
    latency_ms: int,
    error_code: str | None = None,
    request_sent: bool = True,
) -> None:
    try:
        with SessionLocal() as db:
            audit_user_id: int | None = user_id
            if expected_data_epoch is not None:
                owner = db.query(User).filter(User.id == user_id).first()
                if owner is None or owner.business_data_epoch != expected_data_epoch:
                    audit_user_id = None
            db.add(
                AIInvocationLog(
                    setting_id=None,
                    user_id=audit_user_id,
                    feature=TENCENT_OCR_FEATURE,
                    modality="image",
                    provider_name=TENCENT_OCR_PROVIDER,
                    model=TENCENT_OCR_MODEL,
                    status=status,
                    latency_ms=max(0, latency_ms),
                    usage_amount=1 if request_sent else None,
                    usage_unit="requests" if request_sent else None,
                    error_code=error_code[:100] if error_code else None,
                )
            )
            db.commit()
    except Exception:
        # OCR success or fallback must not be converted into a user-visible
        # failure merely because operational audit storage is unavailable.
        return


def _sdk_general_accurate_ocr(content: bytes):
    try:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.ocr.v20181119 import models, ocr_client
    except ImportError as exc:
        raise TencentOCRError(
            "TencentOCRSDKUnavailable",
            "腾讯云 OCR 依赖尚未安装，已保留本机识别降级能力",
        ) from exc

    secret_id = (settings.TENCENT_OCR_SECRET_ID or "").strip()
    secret_key = (settings.TENCENT_OCR_SECRET_KEY or "").strip()
    cred = credential.Credential(secret_id, secret_key)
    http_profile = HttpProfile()
    http_profile.endpoint = TENCENT_OCR_ENDPOINT
    http_profile.reqTimeout = max(5, int(settings.TENCENT_OCR_REQUEST_TIMEOUT_SECONDS))
    client_profile = ClientProfile()
    client_profile.httpProfile = http_profile
    client = ocr_client.OcrClient(
        cred,
        settings.TENCENT_OCR_REGION.strip() or "ap-guangzhou",
        client_profile,
    )
    request = models.GeneralAccurateOCRRequest()
    request.ImageBase64 = base64.b64encode(content).decode("ascii")
    return client.GeneralAccurateOCR(request)


def _point_payload(point: Any) -> dict[str, int] | None:
    try:
        return {"x": int(point.X), "y": int(point.Y)}
    except (AttributeError, TypeError, ValueError):
        return None


def _detection_polygon(detection: Any) -> list[dict[str, int]]:
    polygon = [
        payload
        for point in (getattr(detection, "Polygon", None) or [])
        if (payload := _point_payload(point)) is not None
    ]
    if polygon:
        return polygon
    item = getattr(detection, "ItemPolygon", None)
    if item is None:
        return []
    try:
        left = int(item.X)
        top = int(item.Y)
        width = int(item.Width)
        height = int(item.Height)
    except (AttributeError, TypeError, ValueError):
        return []
    return [
        {"x": left, "y": top},
        {"x": left + width, "y": top},
        {"x": left + width, "y": top + height},
        {"x": left, "y": top + height},
    ]


def _line_sort_key(line: TencentOCRLine) -> tuple[int, int]:
    if not line.polygon:
        return (2**31 - 1, 2**31 - 1)
    return (
        min(point["y"] for point in line.polygon),
        min(point["x"] for point in line.polygon),
    )


def _response_payload(response: Any) -> TencentOCRResult:
    lines: list[TencentOCRLine] = []
    for detection in getattr(response, "TextDetections", None) or []:
        text = str(getattr(detection, "DetectedText", "") or "").replace("\x00", "").strip()
        if not text:
            continue
        raw_confidence = getattr(detection, "Confidence", None)
        try:
            confidence = float(raw_confidence) if raw_confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        lines.append(
            TencentOCRLine(
                text=text,
                confidence=confidence,
                polygon=_detection_polygon(detection),
            )
        )
    lines.sort(key=_line_sort_key)
    text = "\n".join(line.text for line in lines).strip()
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 6 or not re.search(r"\d", compact):
        raise TencentOCRError(
            "TencentOCRNoTransactionText",
            "腾讯云没有识别出清晰交易信息",
            request_sent=True,
        )
    return TencentOCRResult(
        text=text,
        lines=lines,
        request_id=str(getattr(response, "RequestId", "") or "").strip() or None,
    )


def recognize_with_tencent_cloud(
    *,
    user_id: int,
    content: bytes,
    expected_data_epoch: int | None = None,
) -> TencentOCRResult:
    if not settings.TENCENT_OCR_ENABLED:
        raise TencentOCRError("TencentOCRDisabled", "腾讯云 OCR 尚未启用")
    if not tencent_ocr_configured():
        raise TencentOCRError(
            "TencentOCRCredentialsMissing",
            "腾讯云 OCR 已启用，但服务端密钥尚未配置完整",
        )
    if not content or len(content) > TENCENT_OCR_MAX_IMAGE_BYTES:
        raise TencentOCRError(
            "TencentOCRImageTooLarge",
            "识别切片超过腾讯云单次请求大小限制",
        )
    soft_limit = max(0, int(settings.TENCENT_OCR_MONTHLY_SOFT_LIMIT))
    if soft_limit and _monthly_call_count() >= soft_limit:
        raise TencentOCRError(
            "TencentOCRMonthlySoftLimitReached",
            "本月腾讯云 OCR 调用已达到应用软上限",
        )

    started = time.monotonic()
    try:
        result = _response_payload(_sdk_general_accurate_ocr(content))
    except TencentOCRError as exc:
        _record_invocation(
            user_id=user_id,
            expected_data_epoch=expected_data_epoch,
            status="failed",
            latency_ms=round((time.monotonic() - started) * 1000),
            error_code=exc.code,
            request_sent=exc.request_sent,
        )
        raise
    except Exception as exc:
        code = _safe_error_code(exc)
        _record_invocation(
            user_id=user_id,
            expected_data_epoch=expected_data_epoch,
            status="failed",
            latency_ms=round((time.monotonic() - started) * 1000),
            error_code=code,
            request_sent=True,
        )
        raise TencentOCRError(
            code,
            "腾讯云 OCR 调用失败，系统将按配置尝试本机识别",
            request_sent=True,
        ) from exc
    _record_invocation(
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        status="success",
        latency_ms=round((time.monotonic() - started) * 1000),
        request_sent=True,
    )
    return result
