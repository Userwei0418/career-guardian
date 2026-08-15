"""文档上传与 Offer 信息抽取 API"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.career_case import CareerCase
from app.models.offer import Offer
from app.services.document_service import validate_upload, extract_text
from app.services.assistant_service import extract_offer_fields, build_mock_offer
from app.schemas.offer import OfferExtractedFields

router = APIRouter()


@router.post("/upload-offer")
async def upload_and_extract_offer(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传 Offer 文件（PDF/图片），提取文本并用 LLM 结构化抽取"""
    filename = file.filename or "unknown"
    file_bytes = await file.read()

    # 校验
    error = validate_upload(filename, file.content_type or "", len(file_bytes))
    if error:
        raise HTTPException(status_code=400, detail=error)

    # 提取文本
    result = extract_text(file_bytes, filename)
    if result.parse_mode == "failed":
        return {
            "status": "failed",
            "notice": result.parse_notice or "这份没太看清，换粘贴或手动填也一样",
            "fields": None,
        }

    # LLM 结构化抽取
    fields = extract_offer_fields(result.raw_text)

    # 计算整体置信度
    confidences = [
        getattr(fields, k).confidence
        for k in fields.model_fields
        if getattr(fields, k).value is not None
    ]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "status": "ok",
        "raw_text": result.raw_text[:200],
        "page_count": result.page_count,
        "fields": fields.model_dump(),
        "overall_confidence": round(overall_confidence, 3),
    }


@router.post("/paste-offer")
def paste_and_extract_offer(
    data: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """粘贴 Offer 文本，用 LLM 结构化抽取"""
    text = data.get("text", "")
    if not text or len(text.strip()) < 10:
        raise HTTPException(status_code=400, detail="文本内容太少，请粘贴完整的 Offer 信息")

    fields = extract_offer_fields(text)

    confidences = [
        getattr(fields, k).confidence
        for k in fields.model_fields
        if getattr(fields, k).value is not None
    ]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return {
        "status": "ok",
        "fields": fields.model_dump(),
        "overall_confidence": round(overall_confidence, 3),
    }


@router.get("/demo-offer")
def get_demo_offer(user: User = Depends(get_current_user)):
    """获取演示 Offer 数据（小林案例）"""
    return build_mock_offer()
