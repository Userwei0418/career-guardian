"""Version Control and Optimistic Locking Service

Provides optimistic concurrency control for contract file updates,
preventing lost updates when multiple users edit simultaneously.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contract_file import ContractFile
from app.models.user import User


LOCK_TIMEOUT_MINUTES = 5


class VersionControlError(HTTPException):
    """Raised when a version conflict is detected"""
    def __init__(self, current_version: int, attempted_version: int):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: resource has been modified (current={current_version}, your version={attempted_version}). Please refresh and retry.",
        )


def acquire_lock(db: Session, contract_file_id: int, user: User) -> ContractFile:
    """Acquire an optimistic lock on a contract file"""
    contract_file = db.scalar(select(ContractFile).where(ContractFile.id == contract_file_id))
    if contract_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found.")

    now = datetime.now(timezone.utc)

    if contract_file.is_locked and contract_file.locked_by_id != user.id:
        if contract_file.locked_at and (now - contract_file.locked_at) < timedelta(minutes=LOCK_TIMEOUT_MINUTES):
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=f"Contract is currently being edited by another user. Try again in {LOCK_TIMEOUT_MINUTES} minutes.")

    contract_file.is_locked = True
    contract_file.locked_by_id = user.id
    contract_file.locked_at = now
    db.flush()
    return contract_file


def release_lock(db: Session, contract_file_id: int, user: User) -> None:
    """Release a previously acquired lock"""
    contract_file = db.scalar(select(ContractFile).where(ContractFile.id == contract_file_id))
    if contract_file is None:
        return
    if contract_file.locked_by_id == user.id:
        contract_file.is_locked = False
        contract_file.locked_by_id = None
        contract_file.locked_at = None
        db.flush()


def check_version_and_increment(db: Session, contract_file_id: int, expected_version: int) -> ContractFile:
    """Check version for optimistic locking and increment on success"""
    contract_file = db.scalar(select(ContractFile).where(ContractFile.id == contract_file_id))
    if contract_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found.")
    if contract_file.version != expected_version:
        raise VersionControlError(current_version=contract_file.version, attempted_version=expected_version)
    contract_file.version += 1
    db.flush()
    return contract_file


def release_expired_locks(db: Session) -> int:
    """Release all locks that have timed out. Returns count of released locks."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCK_TIMEOUT_MINUTES)
    expired = db.scalars(select(ContractFile).where(ContractFile.is_locked.is_(True), ContractFile.locked_at < cutoff)).all()
    for cf in expired:
        cf.is_locked = False
        cf.locked_by_id = None
        cf.locked_at = None
    db.flush()
    return len(expired)