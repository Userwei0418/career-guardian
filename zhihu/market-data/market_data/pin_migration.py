from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_data.models.raw import CollectionTemplate, DataSource, RecruitmentCompany


TEMPLATES = {
    "moka": ("Moka 招聘", "moka"),
    "feishu": ("飞书招聘", "feishu"),
    "hotjob": ("Hotjob 招聘", "hotjob"),
    "beisen": ("北森招聘", "beisen"),
    "zhiye": ("智联/智业招聘", "zhiye"),
    "pin-special-api": ("Pin 专用 API", "api"),
    "custom-rendered": ("企业官网通用渲染", "custom"),
}


def infer_template(url: str, config: dict) -> str:
    host = (urlparse(url).hostname or "").lower()
    if str(config.get("data_proc_type") or "").lower() == "api":
        return "pin-special-api"
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
    return f"pin-company-{hashlib.sha1(name.strip().encode('utf-8')).hexdigest()[:12]}"


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
        if template is None:
            template = CollectionTemplate(
                code=code,
                name=name,
                platform_type=platform_type,
                adapter_type="pin",
                description="从 Pin 配置驱动采集能力迁移的公司招聘渠道模板",
                capabilities={"list": True, "detail": True, "pagination": True},
                default_config={"max_records": 100, "settle_milliseconds": 1500},
            )
            session.add(template)
            session.flush()
        result[code] = template
    return result


def migrate_pin_company_rows(
    session: Session,
    rows: list[dict],
    *,
    parser_root: Path,
) -> dict[str, int]:
    templates = _ensure_templates(session)
    companies_created = 0
    channels_created = 0
    channels_updated = 0
    invalid_channels = 0
    companies: dict[str, RecruitmentCompany] = {}
    for row in rows:
        name = str(row.get("com_name") or "").strip()
        if not name:
            continue
        company = companies.get(name)
        if company is None:
            code = _company_code(name)
            company = session.scalar(select(RecruitmentCompany).where(RecruitmentCompany.code == code))
            if company is None:
                company = RecruitmentCompany(
                    code=code,
                    name=name,
                    website_url=row.get("career_url") or None,
                    logo_url=row.get("com_logo") or None,
                    origin="pin",
                    enabled=bool(row.get("is_active", 1)),
                )
                session.add(company)
                session.flush()
                companies_created += 1
            companies[name] = company
        raw_config = row.get("json_config") or {}
        if isinstance(raw_config, str):
            try:
                raw_config = json.loads(raw_config)
            except json.JSONDecodeError:
                raw_config = {}
        urls = raw_config.get("urls") or {}
        if not isinstance(urls, dict):
            urls = {}
        for label, value in urls.items():
            url = str(value or "").strip()
            if not url:
                continue
            legacy_code = str(row.get("com_id") or "unknown")
            source_code = f"pin-{legacy_code.lower().replace('_', '-')}-{str(label).lower().replace('_', '-')}"[:80]
            source = session.scalar(select(DataSource).where(DataSource.code == source_code))
            template_code = infer_template(url, raw_config)
            channel_type = infer_channel_type(str(label))
            parser_function = str(raw_config.get("func_name") or "").strip()
            parser_exists = bool(parser_function and (parser_root / f"{parser_function}.py").is_file())
            parsed = urlparse(url)
            valid_url = parsed.scheme == "https" and bool(parsed.hostname)
            configuration_status = "ready" if parser_exists and valid_url else "invalid"
            if configuration_status == "invalid":
                invalid_channels += 1
            table_selector = raw_config.get("table_selector") or raw_config.get("table_selectors") or ""
            detail_selector = raw_config.get("detail_selector") or raw_config.get("detail_selectors") or ""
            technical_config = {
                "parser_function": parser_function,
                "table_selector": table_selector,
                "detail_selector": detail_selector,
                "pre_open_url": raw_config.get("pre_open_url") or "",
                "json_domain": raw_config.get("json_domain") or "",
                "click_text": raw_config.get("click_text"),
                "click_type": raw_config.get("click_type"),
                "click_load_more": raw_config.get("click_load_more") or "",
                "page_count": raw_config.get("page_count", 1),
                "page_function": raw_config.get("page_func_name") or "",
                "max_parent_level": raw_config.get("max_parent_level"),
                "max_records": 100,
                "promotion_mapping": _promotion_mapping(name, channel_type),
            }
            values = {
                "company_id": company.id,
                "template_id": templates[template_code].id,
                "name": f"{name} · {channel_type_name(channel_type)}",
                "adapter_type": "pin",
                "base_url": url,
                "allowed_hosts": [parsed.hostname.lower()] if parsed.hostname else [],
                "config": technical_config,
                "channel_type": channel_type,
                "source_kind": "company_channel",
                "legacy_company_code": legacy_code,
                "configuration_status": configuration_status,
                "min_interval_seconds": 3,
                "timeout_seconds": 60,
                "max_retries": 1,
            }
            if source is None:
                source = DataSource(code=source_code, terms_review_status="pending", enabled=False, **values)
                session.add(source)
                channels_created += 1
            else:
                for key, item in values.items():
                    setattr(source, key, item)
                channels_updated += 1
    session.commit()
    return {
        "companies_created": companies_created,
        "channels_created": channels_created,
        "channels_updated": channels_updated,
        "invalid_channels": invalid_channels,
        "input_rows": len(rows),
    }


def read_crawl_company_rows(backup_path: Path, schema_path: Path) -> list[dict]:
    audit_path = Path(__file__).resolve().parents[1] / "scripts" / "audit_pin_backup.py"
    spec = importlib.util.spec_from_file_location("career_guardian_pin_dump", audit_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Pin dump parser")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    columns = module.load_columns(schema_path)
    names = columns.get("crawl_companies")
    if not names:
        raise RuntimeError("crawl_companies schema is unavailable")
    rows: list[dict] = []

    def on_row(table: str, values: list) -> None:
        if table == "crawl_companies" and len(values) == len(names):
            rows.append(dict(zip(names, values)))

    parser = module.DumpInsertParser(on_row)
    with backup_path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        while chunk := handle.read(1024 * 1024):
            parser.feed(chunk)
    return rows
