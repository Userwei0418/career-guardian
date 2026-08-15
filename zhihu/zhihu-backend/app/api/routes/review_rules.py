from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.review_rule import ReviewRuleCreateRequest, ReviewRuleUpdateRequest, ReviewRuleResponse
from app.services.review_rule_service import list_review_rules, create_review_rule, update_review_rule

router = APIRouter(prefix="/review-rules", tags=["审查规则"])


@router.get("", response_model=List[ReviewRuleResponse])
def get_rules(
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    return list_review_rules(db)


@router.post("", response_model=ReviewRuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: ReviewRuleCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        return create_review_rule(db, payload, user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{rule_id}", response_model=ReviewRuleResponse)
def update_rule(
    rule_id: int,
    payload: ReviewRuleUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        return update_review_rule(db, rule_id, payload, user)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
