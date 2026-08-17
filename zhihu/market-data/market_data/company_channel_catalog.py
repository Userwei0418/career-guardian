from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from market_data.models.raw import CollectionTemplate, DataSource, RecruitmentCompany


ASSET_ROOT = Path(__file__).resolve().parent / "assets" / "company_channels"
CATALOG_PATH = ASSET_ROOT / "catalog.v1.json"
COMPAT_PARSER_ROOT = ASSET_ROOT / "compat_parsers"

TEMPLATES = {
    "moka": ("Moka 招聘", "moka"),
    "feishu": ("飞书招聘", "feishu"),
    "hotjob": ("Hotjob 招聘", "hotjob"),
    "beisen": ("北森招聘", "beisen"),
    "zhiye": ("智业招聘", "zhiye"),
    "special-api": ("企业招聘 API", "api"),
    "custom-rendered": ("企业官网通用渲染", "custom"),
}

BUILT_IN_PLATFORM_PARSERS = {"zhiye"}


def load_company_channel_catalog(path: Path = CATALOG_PATH) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "career-guardian-company-channels-v1":
        raise RuntimeError("公司招聘渠道目录版本不受支持")
    if not isinstance(payload.get("companies"), list):
        raise RuntimeError("公司招聘渠道目录缺少 companies")
    return payload


def infer_template(url: str, config: dict) -> str:
    host = (urlparse(url).hostname or "").lower()
    if str(config.get("data_proc_type") or "").lower() == "api":
        return "special-api"
    if "mokahr" in host or "moka" in host:
        return "moka"
    if "feishu" in host or "atsx" in host:
        return "feishu"
    if "hotjob" in host:
        return "hotjob"
    if "beisen" in host:
        return "beisen"
    if "zhiye" in host:
        return "zhiye"
    return "custom-rendered"


def infer_channel_type(label: str) -> str:
    lowered = label.lower()
    if "xiaozhao" in lowered or "campus" in lowered:
        return "campus"
    if "shixi" in lowered or "intern" in lowered:
        return "internship"
    if "shezhao" in lowered or "social" in lowered:
        return "social"
    return "mixed"


def channel_type_name(channel_type: str) -> str:
    return {
        "campus": "校园招聘",
        "internship": "实习招聘",
        "social": "社会招聘",
    }.get(channel_type, "综合招聘")


def _company_code(name: str) -> str:
    return f"company-{hashlib.sha1(name.strip().encode('utf-8')).hexdigest()[:12]}"


def _legacy_company_code(name: str) -> str:
    return f"pin-company-{hashlib.sha1(name.strip().encode('utf-8')).hexdigest()[:12]}"


def _selector_list(*values: object) -> list[str]:
    result: list[str] = []
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text and text not in result:
                result.append(text)
    return result


def _promotion_mapping(company_name: str, channel_type: str) -> dict:
    return {
        "company_name": {"literal": company_name},
        "title": {"paths": ["announcement_name", "title", "job_name"]},
        "city": {"paths": ["hd_loc", "location", "city"]},
        "location_text": {"paths": ["hd_loc", "location", "city"]},
        "department": {"paths": ["hd_dept", "department"]},
        "experience_requirement": {"paths": ["experience", "work_year"]},
        "education_requirement": {"paths": ["education", "degree"]},
        "description": {"paths": ["_detail_text", "job_description", "description"]},
        "requirements": {"paths": ["requirements", "qualification", "_detail_text"]},
        "responsibilities": {"paths": ["responsibilities", "_detail_text"]},
        "job_category": {"paths": ["hd_job_category", "category"]},
        "employment_type": {"literal": channel_type},
        "is_campus": {"literal": channel_type == "campus"},
        "is_intern": {"literal": channel_type == "internship"},
        "apply_url": {"path": "_source_url"},
        "detail_url": {"path": "_source_url"},
        "published_at": {"paths": ["publish_time", "published_at"]},
        "skill_tags": {"paths": ["skill_tags", "skills"]},
    }


def _ensure_templates(session: Session) -> dict[str, CollectionTemplate]:
    result: dict[str, CollectionTemplate] = {}
    for code, (name, platform_type) in TEMPLATES.items():
        template = session.scalar(select(CollectionTemplate).where(CollectionTemplate.code == code))
        if template is None and code == "special-api":
            template = session.scalar(
                select(CollectionTemplate).where(CollectionTemplate.code == "pin-special-api")
            )
            if template is not None:
                template.code = code
        if template is None:
            template = CollectionTemplate(
                code=code,
                name=name,
                platform_type=platform_type,
                adapter_type="company_channel",
                description="职护自有的公司招聘渠道采集模板",
                capabilities={"list": True, "detail": True, "pagination": True},
                default_config={"max_records": 100, "settle_milliseconds": 1500},
                enabled=True,
            )
            session.add(template)
            session.flush()
        template.name = name
        template.platform_type = platform_type
        template.adapter_type = "company_channel"
        template.description = "职护自有的公司招聘渠道采集模板"
        template.capabilities = {"list": True, "detail": True, "pagination": True}
        template.default_config = {"max_records": 100, "settle_milliseconds": 1500}
        template.enabled = True
        result[code] = template
    return result


def migrate_company_channel_catalog(
    session: Session,
    catalog: dict | None = None,
) -> dict[str, int]:
    catalog = catalog or load_company_channel_catalog()
    templates = _ensure_templates(session)
    companies_created = 0
    channels_created = 0
    channels_updated = 0
    invalid_channels = 0
    companies: dict[str, RecruitmentCompany] = {}
    for row in catalog["companies"]:
        name = str(row.get("company_name") or "").strip()
        if not name:
            continue
        company = companies.get(name)
        if company is None:
            new_code = _company_code(name)
            company = session.scalar(
                select(RecruitmentCompany).where(
                    or_(
                        RecruitmentCompany.code == new_code,
                        RecruitmentCompany.code == _legacy_company_code(name),
                    )
                )
            )
            if company is None:
                company = RecruitmentCompany(code=new_code, name=name)
                session.add(company)
                session.flush()
                companies_created += 1
            company.code = new_code
            company.name = name
            company.website_url = row.get("career_url") or None
            company.logo_url = row.get("logo_url") or None
            company.origin = "migrated_catalog"
            company.enabled = bool(row.get("enabled", True))
            companies[name] = company

        raw_config = row.get("configuration") or {}
        urls = raw_config.get("urls") or {}
        if not isinstance(urls, dict):
            continue
        for label, value in urls.items():
            url = str(value or "").strip()
            if not url:
                continue
            historical_code = str(row.get("company_code") or "unknown")
            channel_suffix = str(label).lower().replace("_", "-")
            source_code = f"channel-{historical_code.lower().replace('_', '-')}-{channel_suffix}"[:80]
            legacy_source_code = f"pin-{historical_code.lower().replace('_', '-')}-{channel_suffix}"[:80]
            source = session.scalar(
                select(DataSource).where(
                    or_(DataSource.code == source_code, DataSource.code == legacy_source_code)
                )
            )
            template_code = infer_template(url, raw_config)
            channel_type = infer_channel_type(str(label))
            compat_parser = str(raw_config.get("func_name") or "").strip()
            parser_exists = bool(
                compat_parser and (COMPAT_PARSER_ROOT / f"{compat_parser}.py").is_file()
            )
            parsed = urlparse(url)
            valid_url = parsed.scheme == "https" and bool(parsed.hostname)
            has_parser = parser_exists or template_code in BUILT_IN_PLATFORM_PARSERS
            configuration_status = "ready" if has_parser and valid_url else "invalid"
            if configuration_status == "invalid":
                invalid_channels += 1
            technical_config = {
                "platform_type": template_code,
                "compat_parser": compat_parser,
                "list_selectors": _selector_list(
                    raw_config.get("table_selectors"), raw_config.get("table_selector")
                ),
                "detail_selectors": _selector_list(
                    raw_config.get("detail_selectors"), raw_config.get("detail_selector")
                ),
                "pre_open_url": raw_config.get("pre_open_url") or "",
                "json_domain": raw_config.get("json_domain") or "",
                "click_text": raw_config.get("click_text"),
                "click_type": raw_config.get("click_type"),
                "click_load_more": raw_config.get("click_load_more") or "",
                "page_count": raw_config.get("page_count", 1),
                "page_function": raw_config.get("page_func_name") or "",
                "max_parent_level": raw_config.get("max_parent_level"),
                "max_records": 100,
                "collection_runtime": "career-guardian-v1",
                "promotion_mapping": _promotion_mapping(name, channel_type),
            }
            values = {
                "company_id": company.id,
                "template_id": templates[template_code].id,
                "name": f"{name} · {channel_type_name(channel_type)}",
                "adapter_type": "company_channel",
                "base_url": url,
                "allowed_hosts": [parsed.hostname.lower()] if parsed.hostname else [],
                "config": technical_config,
                "channel_type": channel_type,
                "source_kind": "company_channel",
                "legacy_company_code": historical_code,
                "configuration_status": configuration_status,
                "min_interval_seconds": 3,
                "timeout_seconds": 60,
                "max_retries": 1,
            }
            if source is None:
                source = DataSource(
                    code=source_code, terms_review_status="pending", enabled=False, **values
                )
                session.add(source)
                channels_created += 1
            else:
                source.code = source_code
                for key, item in values.items():
                    setattr(source, key, item)
                channels_updated += 1
    session.commit()
    return {
        "companies_created": companies_created,
        "channels_created": channels_created,
        "channels_updated": channels_updated,
        "invalid_channels": invalid_channels,
        "input_rows": len(catalog["companies"]),
    }
