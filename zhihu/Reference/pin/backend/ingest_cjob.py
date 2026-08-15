#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ingest_cjob.py - model.json + raw.json -> jobs + job_sources

Single-responsibility explicit field mapping with robust data cleansing.
Handles multiple date formats, salary formats with fallback defaults.
"""
import os, sys, json, re, logging
from datetime import datetime, date
from typing import Optional, Tuple, Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "api"))
from db import get_db_cursor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "crawler"))
from crawl_db import get_pending_ingest, update_ingested

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

CITY_TO_PROVINCE: Dict[str, str] = {
    "北京": "北京市",
    "上海": "上海市",
    "天津": "天津市",
    "重庆": "重庆市",
    "广州": "广东省",
    "深圳": "广东省",
    "杭州": "浙江省",
    "南京": "江苏省",
    "成都": "四川省",
    "武汉": "湖北省",
    "长沙": "湖南省",
    "西安": "陕西省",
    "济南": "山东省",
    "郑州": "河南省",
    "福州": "福建省",
    "合肥": "安徽省",
    "沈阳": "辽宁省",
    "大连": "辽宁省",
    "哈尔滨": "黑龙江省",
    "长春": "吉林省",
    "石家庄": "河北省",
    "太原": "山西省",
    "南昌": "江西省",
    "昆明": "云南省",
    "贵阳": "贵州省",
    "南宁": "广西壮族自治区",
    "海口": "海南省",
    "兰州": "甘肃省",
    "乌鲁木齐": "新疆维吾尔自治区",
    "呼和浩特": "内蒙古自治区",
    "拉萨": "西藏自治区",
    "银川": "宁夏回族自治区",
    "西宁": "青海省",
}

_CN_NUM = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "两": 2,
}

_AI_KEYWORDS = [
    "ai", "aigc", "人工智能", "大模型", "llm", "深度学习",
    "机器学习", "agent", "gpt", "prompt", "神经网络", "nlp",
    "cv", "计算机视觉", "语音识别", "模型微调", "mcp", "多模态",
    "大语言模型", "rag", "embedding", "diffusion", "transformer",
]


# ═══════════════════════════════════════════════════════════════════════════════
# PARSING UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def parse_date(value: Any) -> Optional[str]:
    """Parse a date value from multiple formats. Returns yyyy-mm-dd or None."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    if s.isdigit():
        ts = int(s)
        if 1_000_000_000 < ts < 2_000_000_000:
            try:
                return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass
        elif 10_000_000_000 < ts < 20_000_000_000:
            try:
                return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                pass

    m = re.match(r"(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            return date(datetime.now().year, int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def parse_salary(text: Any) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Parse salary text into (min, max, unit). Returns (None, None, None) for '面议'."""
    if text is None:
        return (None, None, None)
    raw = str(text).strip()
    if not raw:
        return (None, None, None)

    neg_lower = raw.lower()
    if neg_lower in ("面议", "negotiable", "", "-", "--", "——", "—", "暂无"):
        return (None, None, None)

    unit = "month"
    if any(x in raw for x in ("/天", "元/天", "每天")):
        unit = "day"
    elif any(x in raw for x in ("/月", "元/月", "每月", "/month")):
        unit = "month"
    elif any(x in raw for x in ("/年", "万/年", "年薪", "/year", "annual")):
        unit = "year"
    elif any(x in raw for x in ("/时", "元/时", "元/小时", "每小时", "/hour")):
        unit = "hour"
    elif any(x in raw for x in ("/周", "每周", "/week")):
        unit = "week"
    elif "k" in neg_lower or "K" in raw:
        unit = "month"

    cn = raw
    for ch, num in _CN_NUM.items():
        cn = cn.replace(ch, " " + str(num) + " ")

    multi_unit = None
    if "万" in cn:
        multi_unit = 10000
    elif "亿" in cn:
        multi_unit = 100000000
    has_k = bool(re.search(r"\d[kK]", cn))

    found = re.findall(r"(\d+\.?\d*)", cn)
    nums = []
    for num_str in found:
        val = float(num_str)
        if val <= 0:
            continue
        if multi_unit:
            nums.append(int(val * multi_unit))
        elif has_k:
            nums.append(int(val * 1000))
        else:
            nums.append(int(val))
    nums = sorted(set(nums))
    if not nums:
        return (None, None, None)

    if unit == "day":
        nums = [n for n in nums if 10 <= n <= 5000]
    elif unit == "hour":
        nums = [n for n in nums if 5 <= n <= 500]
    elif unit == "week":
        nums = [n for n in nums if 50 <= n <= 50000]
    elif unit == "year":
        nums = [n for n in nums if 3000 <= n <= 2000000]
    else:
        nums = [n for n in nums if 50 <= n <= 2000000]
    if not nums:
        return (None, None, None)

    mn, mx = min(nums), max(nums)

    if unit == "year":
        mn, mx = int(mn / 12), int(mx / 12)
        if mn < 100:
            return (None, None, None)
        return (mn, mx, "month")
    if unit == "hour":
        return (mn, mx, "hour")
    if unit == "day":
        return (mn, mx, "day")
    if unit == "week":
        return (mn, mx, "week")
    return (mn, mx, "month")


def derive_province(city_text: Any) -> Optional[str]:
    if not city_text:
        return None
    s = str(city_text)
    for city, province in CITY_TO_PROVINCE.items():
        if city in s:
            return province
    return None


def extract_first_city(city_text: Any, max_len: int = 100) -> Optional[str]:
    if not city_text:
        return None
    s = str(city_text).strip()
    s = re.sub(r"\s+", "", s)
    for sep in ("/", ",", "，", "、", "|", ";", "；"):
        if sep in s:
            s = s.split(sep)[0]
            break
    s = s.strip()
    return s[:max_len] if s else None


def dedupe_to_list(v: Any) -> Optional[List[str]]:
    if v is None:
        return None
    if isinstance(v, str):
        items = [x.strip() for x in re.split(r"[,，、|;/]", v)]
    elif isinstance(v, (list, tuple)):
        items = [str(x).strip() for x in v]
    else:
        s = str(v).strip()
        items = [s] if s else []
    seen, out = set(), []
    for item in items:
        if item and item not in seen and item.lower() != "none":
            seen.add(item)
            out.append(item)
    return out if out else None


# ═══════════════════════════════════════════════════════════════════════════════
# COMPANY RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_company_id(cur, com_id: str, com_name: str = "") -> Optional[int]:
    if not com_id:
        return None
    # First: get the official company name from crawl_companies
    cur.execute("SELECT com_name FROM crawl_companies WHERE com_id = %s LIMIT 1", (com_id,))
    cc_row = cur.fetchone()
    official_name = cc_row["com_name"].strip() if cc_row and cc_row.get("com_name") else ""

    # Try to find existing company by official name
    if official_name:
        cur.execute("SELECT id FROM companies WHERE name = %s LIMIT 1", (official_name,))
        r = cur.fetchone()
        if r:
            return r["id"]

    # Fallback: try the name from cjob
    if com_name and com_name != official_name:
        cur.execute("SELECT id FROM companies WHERE name = %s LIMIT 1", (com_name[:255],))
        r = cur.fetchone()
        if r:
            return r["id"]

    # Create new company using official name
    name_to_find = (official_name or com_name or com_id)[:255]
    cur.execute(
        "INSERT INTO companies (name, status, created_at, updated_at) "
        "VALUES (%s, 1, NOW(), NOW())",
        (name_to_find,),
    )
    return cur.lastrowid


# ═══════════════════════════════════════════════════════════════════════════════
# JOB DATA BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def _is_ai_related(title: str, cjob: Dict) -> int:
    try:
        title_l = str(title or "").lower()
        if any(kw in title_l for kw in ("ai", "人工智能", "算法", "大模型", "机器学习")):
            return 1
        blob = " ".join(
            str(cjob.get(k, "")) for k in ("Skills", "JobFunctionTags", "WorkTags", "JobDescribe")
        ).lower()
        if any(kw in blob for kw in _AI_KEYWORDS):
            return 1
    except Exception:
        pass
    return 0


def _coalesce(*values, transform=None):
    for v in values:
        if v is not None and str(v).strip():
            s = str(v).strip()
            if transform:
                s = transform(s)
            return s if s else None
    return None


def build_job_data(cjob: Dict, other: Optional[Dict] = None, raw_json: Optional[Dict] = None) -> Dict:
    other = other or {}
    raw_json = raw_json or {}
    if not cjob or not isinstance(cjob, dict):
        return {}

    doc_type = str(cjob.get("DocType", "")).strip().lower()
    hope_type = str(cjob.get("HopeWorkType", "")).strip()

    is_campus = 1 if doc_type in ("xiaozhao", "campus") or "校招" in hope_type else 0
    is_intern = 1 if doc_type in ("shixi", "intern") or "实习" in hope_type else 0
    if not is_intern and not is_campus:
        for k in ("Intern", "CampusRecruitment", "SummerInternship", "IsStudentDeliver"):
            if str(cjob.get(k, "")).strip() in ("是", "1", "yes", "true"):
                is_intern = 1

    work_place = _coalesce(cjob.get("WorkPlace"), other.get("hd_loc")) or ""
    city_text = extract_first_city(work_place)

    salary_text_raw = _coalesce(cjob.get("Salary"), other.get("hd_salary")) or ""
    salary_text = salary_text_raw if "面议" not in salary_text_raw else "面议"
    s_min, s_max, s_unit = (
        parse_salary(salary_text_raw) if salary_text != "面议" else (None, None, None)
    )
    salary_months = {"day": 22, "week": 4, "month": 1, "year": 12, "hour": 176}.get(s_unit)

    published_at = (
        parse_date(cjob.get("PublishTime"))
        or parse_date(other.get("publish_time"))
        or parse_date(other.get("Publish_time"))
        or parse_date(raw_json.get("publish_time"))
        or parse_date(raw_json.get("Publish_time"))
    )
    deadline_at = parse_date(cjob.get("CutDate"))

    major_raw = cjob.get("MajorRequirement")
    if isinstance(major_raw, dict):
        em = major_raw.get("ExplicitMajors") or []
        im = major_raw.get("ImplicitMajors") or []
        major_str = ", ".join(str(x).strip() for x in (*em, *im) if str(x).strip()) or None
    elif isinstance(major_raw, (list, tuple)):
        major_str = ", ".join(str(x).strip() for x in major_raw if str(x).strip()) or None
    else:
        major_str = str(major_raw).strip() or None

    edu_raw = cjob.get("Degree") or cjob.get("DegreeRequirement")
    if isinstance(edu_raw, (list, tuple)):
        edu_list = dedupe_to_list(edu_raw)
        edu_str = ", ".join(edu_list) if edu_list else None
    else:
        edu_str = str(edu_raw).strip() or None

    welfare_raw = cjob.get("Welfare")
    welfare_list = dedupe_to_list(welfare_raw)
    benefits_str = ", ".join(welfare_list) if welfare_list else None

    skills_raw = cjob.get("Skills")
    skills_list = dedupe_to_list(skills_raw)
    skills_json = json.dumps(skills_list, ensure_ascii=False) if skills_list else None

    worktime_raw = cjob.get("WorkTime")
    wt_list = dedupe_to_list(worktime_raw)
    worktime_str = ", ".join(wt_list) if wt_list else None

    salarypay_raw = cjob.get("SalaryPayment")
    sp_list = dedupe_to_list(salarypay_raw)
    salarypay_str = ", ".join(sp_list) if sp_list else None

    resp_raw = cjob.get("CoreWorkContent")
    if isinstance(resp_raw, (list, tuple)):
        resp_list = [str(x).strip() for x in resp_raw if str(x).strip()]
        resp_str = "\n".join(resp_list) if resp_list else None
    else:
        resp_str = str(resp_raw).strip() or None

    industry_raw = cjob.get("PastIndustryRequirement") or cjob.get("IndustryRequirement")
    industry_list = dedupe_to_list(industry_raw)
    industry_str = ", ".join(industry_list) if industry_list else None

    title = (
        str(cjob.get("JobTitle", "")).strip()
        or str(other.get("announcement_name", "")).strip()
        or str(raw_json.get("announcement_name", "")).strip()
        or ""
    )
    title = re.sub(r"\s+", " ", title)
    raw_title = title[:255] if title else "未知职位"
    normalized_title = raw_title

    type_level = cjob.get("TypeAndLevel", {})
    job_level = (
        str(type_level.get("Level", "")).strip()
        if isinstance(type_level, dict)
        else None
    )

    detail_url = (
        str(raw_json.get("full_url", "")).strip()
        or str(other.get("full_url", "")).strip()
        or str(cjob.get("JobLink", "")).strip()
        or ""
    )
    apply_url = (
        str(cjob.get("JobLink", "")).strip()
        or str(raw_json.get("ApplyTypeLink", "")).strip()
        or detail_url
        or ""
    )

    is_ai = _is_ai_related(raw_title, cjob)

    job_data: Dict[str, Any] = {
        "company_id": None,
        "title": raw_title,
        "normalized_title": normalized_title,
        "department": str(cjob.get("JobDept", "")).strip() or None,
        "job_category": str(cjob.get("JobCategory", "")).strip() or str(other.get("hd_job_category", "")).strip() or None,
        "employment_type": hope_type or None,
        "is_campus": is_campus,
        "is_intern": is_intern,
        "location_text": work_place[:200] or None,
        "city": city_text,
        "province": derive_province(work_place),
        "district": None,
        "address": str(cjob.get("Address", "")).strip() or None,
        "location_list": None,
        "education_requirement": edu_str,
        "education_level": edu_str,
        "experience_requirement": str(cjob.get("WorkYears", "")).strip() or None,
        "experience_min_months": None,
        "experience_max_months": None,
        "salary_text": salary_text or None,
        "salary_min": s_min,
        "salary_max": s_max,
        "salary_unit": s_unit,
        "salary_months": salary_months,
        "salary_currency": "CNY" if (s_min or s_max) else None,
        "job_description": str(cjob.get("JobDescribe", "")).strip() or None,
        "job_requirements": str(cjob.get("Jobreq", "")).strip() or None,
        "job_responsibilities": resp_str,
        "benefits": benefits_str,
        "skill_tags": skills_json,
        "major_requirement": major_str,
        "language_requirement": str(cjob.get("LanguageRequirement", "")).strip() or None,
        "certificate_requirement": str(cjob.get("CertificateRequirement", "")).strip() or None,
        "work_time": worktime_str,
        "salary_payment": salarypay_str,
        "industry_requirement": industry_str or None,
        "job_level": job_level,
        "apply_url": apply_url[:500] if apply_url else None,
        "detail_url": detail_url[:500] if detail_url else None,
        "source_site": "",
        "source_job_id": str(cjob.get("FileId", "")).strip() or None,
        "published_at": published_at,
        "deadline_at": deadline_at,
        "first_seen_at": None,
        "last_seen_at": None,
        "status": "open",
        "is_active": 1,
        "quality_score": None,
        "dedupe_key": "",
        "is_ai_related": is_ai,
    }

    filled = sum(1 for k, v in job_data.items()
                 if v is not None and v != "" and k not in ("status", "is_active", "is_campus", "is_intern"))
    total = len(job_data)
    denom = total - 5
    job_data["quality_score"] = round(filled / max(denom, 1) * 100)

    return job_data


# ═══════════════════════════════════════════════════════════════════════════════
# DB INSERT
# ═══════════════════════════════════════════════════════════════════════════════

def insert_job(cur, job_data: Dict, com_id: str) -> Optional[int]:
    title = job_data.get("title", "")
    dedupe_key = f"{com_id}_{title[:200]}"
    job_data["dedupe_key"] = dedupe_key
    job_data["source_site"] = "官网"

    cur.execute("SELECT id FROM jobs WHERE dedupe_key = %s LIMIT 1", (dedupe_key,))
    if cur.fetchone():
        return None

    keys = list(job_data.keys())
    cols = ", ".join(keys)
    placeholders = ", ".join(["%s"] * len(keys))
    vals = tuple(job_data[k] for k in keys)

    cur.execute(f"INSERT INTO jobs ({cols}) VALUES ({placeholders})", vals)
    job_id = cur.lastrowid
    if not job_id:
        return None

    cur.execute(
        "INSERT INTO job_sources "
        "(job_id, source_site, source_type, source_url, apply_url, is_official, is_primary_source, status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            job_id,
            "官网",
            "官网",
            job_data.get("detail_url"),
            job_data.get("apply_url"),
            1,
            1,
            "active",
        ),
    )
    return job_id


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════

def run_ingest(crawl_job_ids=None, com_ids=None) -> Dict:
    records = get_pending_ingest(limit=10000)
    if crawl_job_ids:
        wanted = set(crawl_job_ids)
        records = [r for r in records if r.get("crawl_job_id") in wanted]
    if com_ids:
        wanted = set(com_ids)
        records = [r for r in records if r.get("com_id") in wanted]
    if not records:
        return {"message": "no data", "ingested": 0, "total": 0}

    ingested = skipped_dup = failed = 0
    errors: List[str] = []

    for rec in records:
        try:
            mj = rec.get("model_json") or {}
            if isinstance(mj, str):
                mj = json.loads(mj)
            if not mj or not isinstance(mj, dict):
                skipped_dup += 1
                continue
            cjob = mj.get("cjob") or {}
            if not cjob or not isinstance(cjob, dict):
                skipped_dup += 1
                continue
            other = mj.get("other") or {}
            if not isinstance(other, dict):
                other = {}
            raw_json = rec.get("raw_json") or {}
            if isinstance(raw_json, str):
                raw_json = json.loads(raw_json) if raw_json else {}
            if not isinstance(raw_json, dict):
                raw_json = {}

            com_id = str(rec.get("com_id", "")).strip()
            job_data = build_job_data(cjob, other, raw_json)
            if not job_data:
                skipped_dup += 1
                continue

            crawled_at = rec.get("crawled_at")
            job_data["first_seen_at"] = crawled_at
            job_data["last_seen_at"] = crawled_at
            if not job_data.get("published_at") and crawled_at:
                if isinstance(crawled_at, datetime):
                    job_data["published_at"] = crawled_at.strftime("%Y-%m-%d")
                else:
                    fb = parse_date(crawled_at)
                    if fb:
                        job_data["published_at"] = fb

            with get_db_cursor() as cursor:
                company_name = str(cjob.get("ComName", "")).strip()
                company_id = resolve_company_id(cursor, com_id, company_name)
                if not company_id:
                    failed += 1
                    errors.append(f"{com_id}: company resolution failed")
                    continue
                job_data["company_id"] = company_id
                new_id = insert_job(cursor, job_data, com_id)
                if new_id:
                    update_ingested(rec["crawl_job_id"], new_id)
                    ingested += 1
                else:
                    skipped_dup += 1
        except Exception as e:
            failed += 1
            errors.append(f"{rec.get('com_id', '?')}: {str(e)[:120]}")
            logger.exception("ingest record failed")

    return {
        "message": f"ingested={ingested}, dup={skipped_dup}, failed={failed}",
        "ingested": ingested,
        "skipped_dup": skipped_dup,
        "failed": failed,
        "total": len(records),
        "errors": errors[:20],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", action="append", default=[])
    parser.add_argument("--com-id", action="append", default=[])
    args = parser.parse_args()
    print(
        json.dumps(
            run_ingest(
                crawl_job_ids=args.job_id or None,
                com_ids=args.com_id or None,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
