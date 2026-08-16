from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.models.raw import DataSource
from market_data.schemas import SourceDefinition


def load_source_registry(path: str | Path) -> list[SourceDefinition]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [SourceDefinition.model_validate(item) for item in payload["sources"]]


def upsert_sources(session: Session, definitions: list[SourceDefinition]) -> list[DataSource]:
    sources: list[DataSource] = []
    for definition in definitions:
        source = session.scalar(select(DataSource).where(DataSource.code == definition.code))
        values = definition.model_dump(mode="json")
        values["base_url"] = str(definition.base_url)
        if source is None:
            source = DataSource(**values)
            session.add(source)
        # Existing rows deliberately remain unchanged. The registry is only a bootstrap
        # seed; after creation market_raw is the source of truth for technical settings,
        # governance approval and runtime enablement.
        sources.append(source)
    session.commit()
    for source in sources:
        session.refresh(source)
    return sources


def definition_from_model(source: DataSource) -> SourceDefinition:
    return SourceDefinition(
        code=source.code,
        name=source.name,
        adapter_type=source.adapter_type,
        base_url=source.base_url,
        allowed_hosts=source.allowed_hosts,
        config=source.config,
        terms_review_status=source.terms_review_status,
        enabled=source.enabled,
        min_interval_seconds=source.min_interval_seconds,
        timeout_seconds=source.timeout_seconds,
        max_retries=source.max_retries,
    )
