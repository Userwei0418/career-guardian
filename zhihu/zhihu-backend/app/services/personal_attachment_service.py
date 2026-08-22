from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.personal_attachment import (
    PersonalAttachmentCleanupJob,
    PersonalAttachmentVersion,
)


DOCUMENT_TYPES = {"resume", "offer", "contract", "payslip", "cashflow_import", "other"}
MAX_ORPHAN_SCAN_FILES_PER_RUN = 200
MAX_ORPHAN_SCAN_ENTRIES_PER_FILE = 8
MIN_ORPHAN_SCAN_ENTRIES_PER_RUN = 64


class _BoundedAttachmentTreeScanner:
    """Resume a private-tree walk without materializing or rescanning the tree.

    The cleanup worker owns one scanner for its lifetime. Only ``scandir``
    iterators for the current DFS path are retained, so memory and open file
    descriptors are proportional to directory depth rather than tree size.
    Symlinks are never followed.
    """

    def __init__(self) -> None:
        self._root: Path | None = None
        self._stack: list[Iterator[os.DirEntry[str]]] = []
        self._exhausted = True

    def close(self) -> None:
        while self._stack:
            iterator = self._stack.pop()
            close = getattr(iterator, "close", None)
            if close is not None:
                close()
        self._exhausted = True

    def _start(self, root: Path) -> None:
        self.close()
        self._root = root
        try:
            self._stack.append(os.scandir(root))
        except OSError:
            self._stack = []
        self._exhausted = not self._stack

    def take_files(
        self,
        root: Path,
        *,
        file_limit: int,
        entry_limit: int,
    ) -> list[Path]:
        if file_limit <= 0 or entry_limit <= 0:
            return []
        if self._root != root or self._exhausted:
            self._start(root)
        if not self._stack:
            return []

        files: list[Path] = []
        inspected_entries = 0
        while (
            self._stack
            and len(files) < file_limit
            and inspected_entries < entry_limit
        ):
            iterator = self._stack[-1]
            try:
                entry = next(iterator)
            except StopIteration:
                close = getattr(iterator, "close", None)
                if close is not None:
                    close()
                self._stack.pop()
                continue
            except OSError:
                close = getattr(iterator, "close", None)
                if close is not None:
                    close()
                self._stack.pop()
                continue

            inspected_entries += 1
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    try:
                        self._stack.append(os.scandir(entry.path))
                    except OSError:
                        continue
                elif entry.is_file(follow_symlinks=False):
                    files.append(Path(entry.path))
            except OSError:
                continue

        if not self._stack:
            self._exhausted = True
        return files


def _upload_root() -> Path:
    return Path(settings.UPLOAD_DIR).expanduser().resolve()


def _safe_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return extension if re.fullmatch(r"\.[a-z0-9]{1,10}", extension) else ".bin"


def _ensure_private_directory(path: Path) -> None:
    """Create/repair every private-storage directory below the upload root."""

    root = _upload_root()
    # The upload mount/root may not exist in a fresh checkout. It is not itself
    # private-only because other upload namespaces may share it, so create it
    # safely without changing an existing deployment's root permissions.
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise ValueError("附件存储根目录无效")
    resolved = path.resolve()
    if root not in resolved.parents:
        raise ValueError("附件存储路径无效")
    relative_parts = resolved.relative_to(root).parts
    current = root
    for part in relative_parts:
        current = current / part
        current.mkdir(exist_ok=True, mode=0o700)
        os.chmod(current, 0o700)


def _write_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def save_personal_attachment(
    db: Session,
    *,
    user_id: int,
    document_type: str,
    logical_key: str,
    display_name: str,
    original_filename: str,
    content_type: str,
    content: bytes,
    version_number: int | None = None,
) -> PersonalAttachmentVersion:
    if document_type not in DOCUMENT_TYPES:
        raise ValueError("不支持的附件类型")
    normalized_key = logical_key.strip()[:100] or "default"
    if version_number is None:
        version_number = int(
            db.query(func.max(PersonalAttachmentVersion.version_number))
            .filter(
                PersonalAttachmentVersion.user_id == user_id,
                PersonalAttachmentVersion.document_type == document_type,
                PersonalAttachmentVersion.logical_key == normalized_key,
            )
            .scalar()
            or 0
        ) + 1

    digest = hashlib.sha256(content).hexdigest()
    key_digest = hashlib.sha256(normalized_key.encode("utf-8")).hexdigest()[:16]
    # Every physical object gets an unrepeatable name. A durable cleanup job
    # for an old attachment must never be able to match and delete a later
    # upload that happens to reuse the same logical key, version and bytes.
    object_nonce = uuid4().hex
    relative_path = Path("personal") / str(user_id) / document_type / key_digest / f"v{version_number}-{object_nonce}-{digest[:16]}{_safe_extension(original_filename)}"
    absolute_path = (_upload_root() / relative_path).resolve()
    if _upload_root() not in absolute_path.parents:
        raise ValueError("附件存储路径无效")
    _ensure_private_directory(absolute_path.parent)
    existed_before = absolute_path.exists()
    temporary_path = absolute_path.with_suffix(
        f"{absolute_path.suffix}.{uuid4().hex}.part"
    )
    created_file = False
    try:
        _write_private_file(temporary_path, content)
        os.replace(temporary_path, absolute_path)
        os.chmod(absolute_path, 0o600)
        created_file = not existed_before

        db.query(PersonalAttachmentVersion).filter(
            PersonalAttachmentVersion.user_id == user_id,
            PersonalAttachmentVersion.document_type == document_type,
            PersonalAttachmentVersion.logical_key == normalized_key,
        ).update({PersonalAttachmentVersion.is_active: False}, synchronize_session=False)
        attachment = PersonalAttachmentVersion(
            user_id=user_id,
            document_type=document_type,
            logical_key=normalized_key,
            version_number=version_number,
            display_name=display_name.strip()[:200] or original_filename[:200],
            original_filename=original_filename.replace("\\", "/").rsplit("/", 1)[-1][:255],
            content_type=(content_type or "application/octet-stream")[:150],
            storage_path=str(relative_path),
            file_size=len(content),
            content_hash=digest,
            is_active=True,
        )
        db.add(attachment)
        db.flush()
        return attachment
    except Exception:
        temporary_path.unlink(missing_ok=True)
        # Only remove a file created by this invocation. A pre-existing path
        # can belong to an already committed attachment with identical key,
        # version and digest and must survive this failed DB operation.
        if created_file:
            absolute_path.unlink(missing_ok=True)
        raise
    finally:
        temporary_path.unlink(missing_ok=True)


def resolve_attachment_path(attachment: PersonalAttachmentVersion) -> Path:
    root = _upload_root()
    path = (root / attachment.storage_path).resolve()
    if root not in path.parents or not path.is_file():
        raise FileNotFoundError(attachment.storage_path)
    # Repair legacy objects created under a permissive process umask before
    # they can be served again. Failure is intentionally fail-closed.
    _ensure_private_directory(path.parent)
    os.chmod(path, 0o600)
    return path


def delete_attachment_file(attachment: PersonalAttachmentVersion) -> None:
    """Remove one known attachment file without broad directory deletion."""
    try:
        resolve_attachment_path(attachment).unlink(missing_ok=True)
    except FileNotFoundError:
        return


def list_user_attachment_paths(db: Session, user_id: int) -> list[Path]:
    attachments = db.query(PersonalAttachmentVersion).filter_by(user_id=user_id).all()
    paths: list[Path] = []
    seen: set[Path] = set()
    for attachment in attachments:
        try:
            path = resolve_attachment_path(attachment)
        except FileNotFoundError:
            continue
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def delete_attachment_paths(paths: list[Path]) -> list[Path]:
    failures: list[Path] = []
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            failures.append(path)
    return failures


def delete_user_attachment_files(db: Session, user_id: int) -> None:
    """Compatibility wrapper for call sites that already own commit semantics."""
    delete_attachment_paths(list_user_attachment_paths(db, user_id))


def enqueue_user_attachment_cleanup(db: Session, user_id: int) -> list[int]:
    attachments = db.query(PersonalAttachmentVersion).filter_by(user_id=user_id).all()
    # A repeated clear after the metadata was already deleted must still
    # surface prior pending/failed work instead of returning an empty report.
    job_ids: list[int] = [
        row.id
        for row in db.query(PersonalAttachmentCleanupJob.id).filter(
            PersonalAttachmentCleanupJob.user_id == user_id,
            PersonalAttachmentCleanupJob.status != "completed",
        ).order_by(PersonalAttachmentCleanupJob.id.asc()).all()
    ]
    seen_paths: set[str] = set()
    for attachment in attachments:
        if attachment.storage_path in seen_paths:
            continue
        seen_paths.add(attachment.storage_path)
        job = db.query(PersonalAttachmentCleanupJob).filter_by(
            storage_path=attachment.storage_path,
        ).first()
        if job is None:
            job = PersonalAttachmentCleanupJob(
                user_id=user_id,
                storage_path=attachment.storage_path,
                content_hash=attachment.content_hash,
                status="pending",
            )
            db.add(job)
        else:
            job.user_id = user_id
            job.content_hash = attachment.content_hash
            job.status = "pending"
            job.last_error = None
            job.completed_at = None
        db.flush()
        if job.id not in job_ids:
            job_ids.append(job.id)
    return sorted(job_ids)


def enqueue_attachment_cleanup(
    db: Session,
    attachment: PersonalAttachmentVersion,
) -> int:
    """Create one durable tombstone before retiring attachment metadata."""

    job = db.query(PersonalAttachmentCleanupJob).filter_by(
        storage_path=attachment.storage_path,
    ).first()
    if job is None:
        job = PersonalAttachmentCleanupJob(
            user_id=attachment.user_id,
            storage_path=attachment.storage_path,
            content_hash=attachment.content_hash,
            status="pending",
        )
        db.add(job)
    else:
        job.user_id = attachment.user_id
        job.content_hash = attachment.content_hash
        job.status = "pending"
        job.last_error = None
        job.completed_at = None
    db.flush()
    return job.id


def _stored_file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _is_cleanup_path_conflict(exc: IntegrityError) -> bool:
    """Recognize only the durable cleanup path's cross-worker unique race."""

    message = str(getattr(exc, "orig", exc)).lower()
    return (
        "uq_attachment_cleanup_storage_path" in message
        or (
            "unique constraint failed: "
            "personal_attachment_cleanup_jobs.storage_path"
        ) in message
    )


def process_attachment_cleanup_jobs(db: Session, job_ids: list[int]) -> dict:
    if not job_ids:
        return {"cleanup_ids": [], "completed_ids": [], "failed_ids": []}
    jobs = db.query(PersonalAttachmentCleanupJob).filter(
        PersonalAttachmentCleanupJob.id.in_(set(job_ids)),
    ).order_by(PersonalAttachmentCleanupJob.id.asc()).with_for_update().all()
    completed_ids: list[int] = []
    failed_ids: list[int] = []
    root = _upload_root()
    for job in jobs:
        if job.status == "completed":
            completed_ids.append(job.id)
            db.delete(job)
            continue
        job.attempts += 1
        try:
            relative_parts = Path(job.storage_path).parts
            if (
                len(relative_parts) < 3
                or relative_parts[0] != "personal"
                or relative_parts[1] != str(job.user_id)
            ):
                raise ValueError("InvalidCleanupPath")
            path = (root / job.storage_path).resolve()
            if root not in path.parents:
                raise ValueError("InvalidCleanupPath")
            if db.query(PersonalAttachmentVersion.id).filter(
                PersonalAttachmentVersion.storage_path == job.storage_path,
            ).first() is not None:
                raise ValueError("CleanupTargetStillReferenced")
            if path.exists():
                if not path.is_file():
                    raise ValueError("CleanupTargetNotFile")
                # The physical name contains a random nonce and the database
                # has just proven that no live attachment references it. A
                # changed/corrupt payload is still the same private tombstone
                # target and must be deleted, not retained forever.
                path.unlink(missing_ok=True)
            completed_ids.append(job.id)
            # Success no longer needs a retry tombstone. Removing the row in
            # the same transaction avoids retaining an account-linked path and
            # full content hash indefinitely after the private object is gone.
            db.delete(job)
        except (OSError, ValueError) as exc:
            job.status = "failed"
            job.last_error = str(exc)[:100] or type(exc).__name__
            job.completed_at = None
            failed_ids.append(job.id)
    db.commit()
    return {
        "cleanup_ids": sorted({job.id for job in jobs}),
        "completed_ids": completed_ids,
        "failed_ids": failed_ids,
    }


def enqueue_orphaned_attachment_cleanup(
    db: Session,
    *,
    grace_seconds: int,
    limit: int = 200,
    scanner: _BoundedAttachmentTreeScanner | None = None,
) -> list[int]:
    """Create durable jobs for aged private files with no committed metadata.

    The grace period is essential: a request may have atomically installed a
    file but not committed its attachment row yet. Fresh ``.part`` files are
    protected by the same grace period; stale ones are private crash residue
    and must not remain outside the durable cleanup path forever. A long-lived
    scanner makes each worker pass bounded while continuing where the previous
    pass stopped; standalone callers still receive one bounded pass.
    """

    effective_limit = min(max(0, limit), MAX_ORPHAN_SCAN_FILES_PER_RUN)
    if effective_limit == 0:
        return []
    root = _upload_root()
    raw_personal_root = root / "personal"
    if raw_personal_root.is_symlink() or not raw_personal_root.is_dir():
        return []
    personal_root = raw_personal_root.resolve()
    if personal_root.parent != root:
        return []

    owns_scanner = scanner is None
    active_scanner = scanner or _BoundedAttachmentTreeScanner()
    try:
        candidates = active_scanner.take_files(
            personal_root,
            file_limit=effective_limit,
            entry_limit=max(
                MIN_ORPHAN_SCAN_ENTRIES_PER_RUN,
                effective_limit * MAX_ORPHAN_SCAN_ENTRIES_PER_FILE,
            ),
        )
    finally:
        if owns_scanner:
            active_scanner.close()
    if not candidates:
        return []

    now = time.time()
    inspected: list[tuple[str, Path, int, float]] = []
    for candidate in candidates:
        if candidate.is_symlink():
            continue
        try:
            resolved = candidate.resolve()
            if root not in resolved.parents or not resolved.is_file():
                continue
            relative = resolved.relative_to(root).as_posix()
            age_seconds = now - resolved.stat().st_mtime
        except (OSError, ValueError):
            continue
        parts = Path(relative).parts
        if len(parts) < 3 or parts[0] != "personal" or not parts[1].isdigit():
            continue
        try:
            _ensure_private_directory(resolved.parent)
            os.chmod(resolved, 0o600)
        except OSError:
            continue
        inspected.append((relative, resolved, int(parts[1]), age_seconds))

    if not inspected:
        return []
    inspected_paths = [item[0] for item in inspected]
    # Query only the bounded filesystem page instead of materializing every
    # committed attachment and cleanup tombstone on each worker cycle.
    referenced = {
        row[0]
        for row in db.query(PersonalAttachmentVersion.storage_path).filter(
            PersonalAttachmentVersion.storage_path.in_(inspected_paths),
        ).all()
    }
    known = {
        row[0]
        for row in db.query(PersonalAttachmentCleanupJob.storage_path).filter(
            PersonalAttachmentCleanupJob.storage_path.in_(inspected_paths),
        ).all()
    }

    created_ids: list[int] = []
    for relative, resolved, user_id, age_seconds in inspected:
        # Permission repair applies to referenced legacy attachments too;
        # orphan classification happens only after the file is private.
        if (
            relative in referenced
            or relative in known
            or age_seconds < max(0, grace_seconds)
        ):
            continue
        try:
            content_hash = _stored_file_digest(resolved)
        except OSError:
            continue
        job = PersonalAttachmentCleanupJob(
            user_id=user_id,
            storage_path=relative,
            content_hash=content_hash,
            status="pending",
        )
        try:
            # The unique path constraint is the cross-worker last line of
            # defense. A savepoint keeps a benign race from poisoning the
            # surrounding cleanup transaction.
            with db.begin_nested():
                db.add(job)
                db.flush()
        except IntegrityError as exc:
            # Do not query for the winner in this transaction: under MySQL
            # REPEATABLE READ the earlier page query may keep a snapshot that
            # cannot see the newly committed row. The named/column-specific
            # unique constraint already proves a durable winner exists.
            if not _is_cleanup_path_conflict(exc):
                raise
            continue
        known.add(relative)
        created_ids.append(job.id)
    if created_ids:
        db.commit()
    return created_ids


def claim_attachment_cleanup_jobs(
    db: Session,
    *,
    limit: int = 50,
    stale_processing_seconds: int = 300,
) -> list[int]:
    stale_before = datetime.utcnow() - timedelta(seconds=stale_processing_seconds)
    jobs = (
        db.query(PersonalAttachmentCleanupJob)
        .filter(
            or_(
                PersonalAttachmentCleanupJob.status.in_({"pending", "failed"}),
                (
                    (PersonalAttachmentCleanupJob.status == "processing")
                    & (PersonalAttachmentCleanupJob.updated_at < stale_before)
                ),
            ),
        )
        .order_by(
            case(
                (PersonalAttachmentCleanupJob.status == "pending", 0),
                (PersonalAttachmentCleanupJob.status == "processing", 1),
                else_=2,
            ),
            PersonalAttachmentCleanupJob.updated_at.asc(),
            PersonalAttachmentCleanupJob.id.asc(),
        )
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    claimed: list[int] = []
    for job in jobs:
        job.status = "processing"
        job.completed_at = None
        claimed.append(job.id)
    db.commit()
    return claimed
