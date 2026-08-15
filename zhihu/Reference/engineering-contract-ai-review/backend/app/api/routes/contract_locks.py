from fastapi import APIRouter, Depends

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.contract_file import ContractFile
from app.models.user import User
from app.schemas.contract import ContractLockResponse
from app.services.permission_service import ensure_can_modify_contracts
from app.services.version_control_service import acquire_lock, release_lock


router = APIRouter(prefix="/contracts", tags=["contract-locks"])


@router.post("/{contract_file_id}/lock", response_model=ContractLockResponse)
def lock_contract(
    contract_file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContractLockResponse:
    ensure_can_modify_contracts(current_user)
    contract_file = acquire_lock(db, contract_file_id, current_user)
    db.commit()
    return ContractLockResponse(
        file_id=contract_file.id,
        version=contract_file.version,
        is_locked=True,
        locked_by=current_user.username,
        locked_at=contract_file.locked_at.isoformat() if contract_file.locked_at else None,
    )


@router.post("/{contract_file_id}/unlock", response_model=ContractLockResponse)
def unlock_contract(
    contract_file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ContractLockResponse:
    ensure_can_modify_contracts(current_user)
    release_lock(db, contract_file_id, current_user)
    db.commit()
    contract_file = db.scalar(select(ContractFile).where(ContractFile.id == contract_file_id))
    return ContractLockResponse(
        file_id=contract_file.id,
        version=contract_file.version,
        is_locked=contract_file.is_locked,
        locked_by=None,
        locked_at=None,
    )

