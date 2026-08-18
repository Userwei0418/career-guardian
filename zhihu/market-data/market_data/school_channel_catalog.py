from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.adapters.company_channel import validate_compat_parser_source
from market_data.models.raw import CollectionTemplate, DataSource, RecruitmentSchool


ASSET_ROOT = Path(__file__).resolve().parent / "assets" / "school_channels"
CATALOG_PATH = ASSET_ROOT / "catalog.v1.json"
COMPAT_PARSER_ROOT = ASSET_ROOT / "compat_parsers"
TEMPLATE_CODE = "school-announcement-rendered"


def _promotion_mapping() -> dict:
    return {
        "company_name": {
            "paths": [
                "hd_company",
                "company_name",
                "employer_name",
                "_derived_company_name",
            ]
        },
        "title": {"paths": ["announcement_name", "title", "job_name"]},
        "city": {"paths": ["hd_loc", "location", "city"]},
        "location_text": {"paths": ["hd_loc", "location", "city"]},
        "department": {"paths": ["hd_dept", "department"]},
        "description": {"paths": ["_detail_text", "job_description", "description"]},
        "requirements": {"paths": ["requirements", "qualification", "_detail_text"]},
        "responsibilities": {"paths": ["responsibilities", "_detail_text"]},
        "job_category": {"paths": ["hd_job_category", "category"]},
        "employment_type": {"literal": "campus"},
        "is_campus": {"literal": True},
        "is_intern": {"paths": ["is_intern"]},
        "apply_url": {"path": "_source_url"},
        "detail_url": {"path": "_source_url"},
        "published_at": {"paths": ["publish_time", "published_at"]},
        "skill_tags": {"paths": ["skill_tags", "skills"]},
    }


def load_school_channel_catalog(path: Path = CATALOG_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "career-guardian-school-channels-v1":
        raise RuntimeError("学校招聘公告渠道目录版本不受支持")
    if not isinstance(payload.get("schools"), list):
        raise RuntimeError("学校招聘公告渠道目录缺少 schools")
    return payload


def _selector_list(*values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            for text in str(candidate or "").split("|"):
                text = text.strip()
                if text and text not in result:
                    result.append(text)
    return result


def _ensure_template(session: Session) -> CollectionTemplate:
    template = session.scalar(
        select(CollectionTemplate).where(CollectionTemplate.code == TEMPLATE_CODE)
    )
    if template is None:
        template = CollectionTemplate(
            code=TEMPLATE_CODE,
            name="学校招聘公告网页",
            platform_type="school-rendered",
            adapter_type="company_channel",
            description="职护自有的学校就业网公告采集模板，统一进入 Raw、标准化与岗位主库",
            capabilities={},
            default_config={},
            enabled=True,
        )
        session.add(template)
        session.flush()
    template.name = "学校招聘公告网页"
    template.platform_type = "school-rendered"
    template.adapter_type = "company_channel"
    template.description = "职护自有的学校就业网公告采集模板，统一进入 Raw、标准化与岗位主库"
    template.capabilities = {
        "list": True,
        "detail": True,
        "iframe": True,
        "raw_html": True,
        "raw_only": False,
    }
    template.default_config = {
        "max_records": 100,
        "settle_milliseconds": 1500,
        "detail_capture_required": True,
    }
    template.enabled = True
    return template


def migrate_school_channel_catalog(
    session: Session,
    catalog: dict | None = None,
    *,
    approve_and_enable: bool = False,
    actor: str = "school-catalog-import",
) -> dict[str, int]:
    """Import packaged public school rules into the unified job pipeline.

    Approval is deliberately explicit.  Even when an administrator authorizes
    the import, only rules that pass the packaged parser and declarative-rule
    checks are enabled; review/invalid entries stay visible but cannot run.
    """

    catalog = catalog or load_school_channel_catalog()
    template = _ensure_template(session)
    created = 0
    updated = 0
    schools_created = 0
    schools_updated = 0
    invalid = 0
    enabled = 0
    review_required = 0
    reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for school in catalog["schools"]:
        school_code = str(school.get("school_code") or "").strip().lower()
        school_name = str(school.get("school_name") or school.get("school_webname") or "").strip()
        employment_center_name = str(
            school.get("school_webname") or school.get("school_name") or ""
        ).strip()
        raw_config = dict(school.get("configuration") or {})
        compatibility = dict(school.get("compatibility") or {})
        urls = raw_config.get("urls") or {}
        if (
            not school_code
            or not school_name
            or not employment_center_name
            or not isinstance(urls, dict)
        ):
            continue
        first_url = next((str(value).strip() for value in urls.values() if str(value or "").strip()), None)
        subject = session.scalar(
            select(RecruitmentSchool).where(RecruitmentSchool.code == school_code)
        )
        if subject is None:
            subject = RecruitmentSchool(
                code=school_code,
                name=school_name,
                employment_center_name=employment_center_name,
                website_url=first_url,
                origin="catalog",
                status="active",
            )
            session.add(subject)
            session.flush()
            schools_created += 1
        else:
            subject.name = school_name
            subject.employment_center_name = employment_center_name
            subject.website_url = first_url or subject.website_url
            if subject.origin != "manual":
                subject.origin = "catalog"
            schools_updated += 1
        parser_name = str(raw_config.get("func_name") or "").strip()
        parser_path = COMPAT_PARSER_ROOT / f"{parser_name}.py"
        parser_valid = False
        if parser_name and parser_path.is_file():
            try:
                validate_compat_parser_source(parser_path)
                parser_valid = True
            except Exception:
                parser_valid = False
        for label, value in urls.items():
            url = str(value or "").strip()
            if not url:
                continue
            parsed = urlparse(url)
            secure = parsed.scheme == "https" and bool(parsed.hostname)
            declarative_supported = bool(compatibility.get("declarative_supported", True))
            if secure and parser_valid and declarative_supported:
                configuration_status = "ready"
            elif secure and parser_valid:
                configuration_status = "needs_review"
            else:
                configuration_status = "invalid"
            if configuration_status == "invalid":
                invalid += 1
            if configuration_status != "ready":
                review_required += 1
            suffix = str(label).lower().replace("_", "-")
            source_code = f"school-{school_code.replace('_', '-')}-{suffix}"[:80]
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            allowed_hosts = {
                host
                for host in (
                    parsed.hostname,
                    urlparse(str(raw_config.get("json_domain") or "")).hostname,
                    urlparse(str(raw_config.get("pre_open_url") or "")).hostname,
                )
                if host
            }
            technical_config = {
                "platform_type": "school-rendered",
                "compat_parser_namespace": "school",
                "compat_parser": parser_name,
                "list_selectors": _selector_list(
                    raw_config.get("table_selectors"), raw_config.get("table_selector")
                ),
                "detail_selectors": _selector_list(
                    raw_config.get("detail_selectors"), raw_config.get("detail_selector")
                ),
                "detail_fallback_selectors": ["main", "article", "[role=main]", "body"],
                "detail_iframe": raw_config.get("detail_iframe") or "",
                "pre_open_url": raw_config.get("pre_open_url") or "",
                "json_domain": raw_config.get("json_domain") or "",
                "click_text": raw_config.get("click_text"),
                "click_type": raw_config.get("click_type"),
                "published_within_days": 180,
                "raw_only": False,
                "raw_contract": "school-announcement-v1",
                "promotion_mapping": _promotion_mapping(),
                "detail_capture_required": True,
                "pagination": {
                    "mode": "auto",
                    "max_pages": 20,
                    "max_records": 500,
                    "stable_rounds": 2,
                },
                "incremental": {
                    "enabled": True,
                    "ordering": "newest_first",
                    "recent_id_window": 300,
                    "full_refresh_every_runs": 10,
                },
                "collection_runtime": "career-guardian-v1",
                "legacy_unsupported_action_fields": list(
                    compatibility.get("unsupported_action_fields") or []
                ),
            }
            values = {
                "company_id": None,
                "school_id": subject.id,
                "template_id": template.id,
                "name": f"{employment_center_name} · 招聘公告",
                "adapter_type": "company_channel",
                "base_url": url,
                "allowed_hosts": sorted(host.lower() for host in allowed_hosts),
                "config": technical_config,
                "channel_type": "campus",
                "source_kind": "school_announcement",
                "legacy_company_code": school_code,
                "configuration_status": configuration_status,
                "min_interval_seconds": 5,
                "timeout_seconds": 60,
                "max_retries": 1,
            }
            if source is None:
                source = DataSource(
                    code=source_code,
                    terms_review_status=(
                        "approved" if approve_and_enable else "pending"
                    ),
                    terms_reviewed_by=(actor if approve_and_enable else None),
                    terms_reviewed_at=(reviewed_at if approve_and_enable else None),
                    terms_review_note=(
                        "管理员批准正式学校目录导入；仅启用配置校验通过的统一岗位来源"
                        if approve_and_enable
                        else None
                    ),
                    enabled=approve_and_enable and configuration_status == "ready",
                    **values,
                )
                session.add(source)
                created += 1
            else:
                for key, item in values.items():
                    setattr(source, key, item)
                if approve_and_enable:
                    source.terms_review_status = "approved"
                    source.terms_reviewed_by = actor
                    source.terms_reviewed_at = reviewed_at
                    source.terms_review_note = (
                        "管理员批准正式学校目录导入；仅启用配置校验通过的统一岗位来源"
                    )
                    source.enabled = configuration_status == "ready"
                updated += 1
            if source.enabled:
                enabled += 1
    session.commit()
    return {
        "schools": len(catalog["schools"]),
        "school_subjects_created": schools_created,
        "school_subjects_updated": schools_updated,
        "sources_created": created,
        "sources_updated": updated,
        "invalid_sources": invalid,
        "review_required_sources": review_required,
        "enabled_sources": enabled,
    }
