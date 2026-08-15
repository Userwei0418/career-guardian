from fastapi import APIRouter, Query, HTTPException, Body
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from db import get_db_cursor
from cache import get_cache, set_cache, build_cache_key
from models import (
    JobWithCompany,
    JobSource,
    JobSourceListResponse,
    CityStats,
    JobListItem,
    JobListResponseV2,
    CursorJobListResponse,
    JobBase,
    Job,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

CACHE_TTL = 300


def parse_job_data(job: dict) -> dict:
    if job.get("skill_tags") and isinstance(job["skill_tags"], str):
        try:
            job["skill_tags"] = json.loads(job["skill_tags"])
        except Exception:
            job["skill_tags"] = []
    return job


def build_job_filters(
    keyword: Optional[str] = None,
    city: Optional[str] = None,
    employment_type: Optional[str] = None,
    is_campus: Optional[int] = None,
    is_intern: Optional[int] = None,
    education_level: Optional[str] = None,
    job_category: Optional[str] = None,
    published_days: Optional[int] = None,
    status: Optional[str] = None,
) -> (str, List[Any]):
    # 基础条件：职位激活、开放，公司状态正常，且【发布时间在当前时间及之前】
    conditions = [
        "j.is_active = 1", 
        # status filter below
        "c.status = 1",
        "j.published_at <= CURRENT_TIMESTAMP"
    ]
    params: List[Any] = []

    if status:
        conditions.append("j.status = %s")
        params.append(status)

    if keyword:
        conditions.append("(j.title LIKE %s OR j.normalized_title LIKE %s OR c.name LIKE %s)")
        keyword_like = f"%{keyword}%"
        params.extend([keyword_like, keyword_like, keyword_like])

    if city:
        conditions.append("j.city = %s")
        params.append(city)

    if employment_type:
        conditions.append("j.employment_type = %s")
        params.append(employment_type)

    if is_campus is not None:
        conditions.append("j.is_campus = %s")
        params.append(is_campus)

    if is_intern is not None:
        conditions.append("j.is_intern = %s")
        params.append(is_intern)

    if education_level:
        conditions.append("j.education_level = %s")
        params.append(education_level)

    if job_category:
        conditions.append("j.job_category = %s")
        params.append(job_category)

    if published_days:
        conditions.append("j.published_at >= DATE_SUB(NOW(), INTERVAL %s DAY)")
        params.append(published_days)

    return " AND ".join(conditions), params


@router.get("", response_model=JobListResponseV2)
async def get_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    city: Optional[str] = None,
    employment_type: Optional[str] = None,
    is_campus: Optional[int] = Query(None, ge=0, le=1),
    is_intern: Optional[int] = Query(None, ge=0, le=1),
    education_level: Optional[str] = None,
    job_category: Optional[str] = None,
    published_days: Optional[int] = Query(None, ge=1, le=365),
    status: Optional[str] = Query(None, pattern="^(open|closed|expired)$"),
    sort_by: str = Query("published_at", pattern="^(published_at|last_seen_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    has_filters = any([
        keyword, city, employment_type, is_campus is not None, is_intern is not None,
        education_level, job_category, published_days
    ])

    cacheable = (
        not has_filters and
        page == 1 and
        page_size == 20 and
        sort_by == "published_at" and
        sort_order == "desc"
    )

    if cacheable:
        cache_key = "jobs:list:v2:default"
        cached = get_cache(cache_key)
        if cached is not None:
            return JobListResponseV2(**cached)

    offset = (page - 1) * page_size
    where_clause, params = build_job_filters(
        keyword=keyword,
        city=city,
        employment_type=employment_type,
        is_campus=is_campus,
        is_intern=is_intern,
        education_level=education_level,
        job_category=job_category,
        published_days=published_days,
        status=status,
    )

    order_clause = f"j.{sort_by} {sort_order}, j.id {sort_order}"

    with get_db_cursor() as cursor:
        # 性能优化：延迟关联 (Late Row Lookup) 
        # 避免在全表 JOIN 和深度分页 OFFSET 时扫描并丢弃大量无用的列数据内容，先通过子查询利用索引找到目标 ID。
        cursor.execute(
            f"""
            SELECT j.id, j.title, j.normalized_title, j.job_category, j.employment_type,
                   j.is_campus, j.is_intern, j.city, j.education_level,
                   j.salary_text, j.salary_min, j.salary_max, j.published_at,
                   j.company_id, j.source_site, j.status,
                   c.name as company_name, c.short_name as company_short_name, c.logo_url as company_logo_url
            FROM (
                SELECT j.id
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE {where_clause}
                ORDER BY {order_clause}
                LIMIT %s OFFSET %s
            ) as sub
            JOIN jobs j ON sub.id = j.id
            JOIN companies c ON j.company_id = c.id
            ORDER BY {order_clause}
            """,
            params + [page_size + 1, offset]
        )
        rows = cursor.fetchall()

    has_more = len(rows) > page_size
    jobs = rows[:page_size]

    # Get total count
    with get_db_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) as total FROM jobs j JOIN companies c ON j.company_id = c.id WHERE {where_clause}", params)
        total = cursor.fetchone()["total"]

    result = JobListResponseV2(
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
        jobs=[JobListItem(**job) for job in jobs]
    )

    if cacheable:
        set_cache(cache_key, result.model_dump(mode="json"), CACHE_TTL)

    return result


@router.get("/cursor", response_model=CursorJobListResponse)
async def get_jobs_by_cursor(
    limit: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    city: Optional[str] = None,
    employment_type: Optional[str] = None,
    is_campus: Optional[int] = Query(None, ge=0, le=1),
    is_intern: Optional[int] = Query(None, ge=0, le=1),
    education_level: Optional[str] = None,
    job_category: Optional[str] = None,
    published_days: Optional[int] = Query(None, ge=1, le=365),
    status: Optional[str] = Query(None, pattern="^(open|closed|expired)$"),
    last_published_at: Optional[datetime] = None,
    last_id: Optional[int] = None,
):
    where_clause, params = build_job_filters(
        keyword=keyword,
        city=city,
        employment_type=employment_type,
        is_campus=is_campus,
        is_intern=is_intern,
        education_level=education_level,
        job_category=job_category,
        published_days=published_days,
        status=status,
    )

    if last_published_at is not None and last_id is not None:
        where_clause += " AND (j.published_at < %s OR (j.published_at = %s AND j.id < %s))"
        params.extend([last_published_at, last_published_at, last_id])

    with get_db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT j.id, j.title, j.normalized_title, j.job_category, j.employment_type,
                   j.is_campus, j.is_intern, j.city, j.education_level,
                   j.salary_text, j.salary_min, j.salary_max, j.published_at,
                   j.company_id, j.source_site,
                   c.name as company_name, c.short_name as company_short_name, c.logo_url as company_logo_url
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE {where_clause}
            ORDER BY j.published_at DESC, j.id DESC
            LIMIT %s
            """,
            params + [limit + 1]
        )
        rows = cursor.fetchall()

    has_more = len(rows) > limit
    jobs = rows[:limit]

    next_cursor_published_at = None
    next_cursor_id = None
    if jobs and has_more:
        last_row = jobs[-1]
        next_cursor_published_at = last_row["published_at"]
        next_cursor_id = last_row["id"]

    return CursorJobListResponse(
        page_size=limit,
        has_more=has_more,
        next_cursor_published_at=next_cursor_published_at,
        next_cursor_id=next_cursor_id,
        jobs=[JobListItem(**job) for job in jobs]
    )


@router.get("/cities", response_model=List[CityStats])
async def get_job_cities():
    cached = get_cache("jobs:cities")
    if cached is not None:
        return [CityStats(**c) for c in cached]

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT city, COUNT(*) as count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' 
              AND city IS NOT NULL AND city != ''
              AND published_at <= CURRENT_TIMESTAMP
            GROUP BY city
            ORDER BY count DESC
            LIMIT 50
            """
        )
        result = [dict(row) for row in cursor.fetchall()]

    set_cache("jobs:cities", result, CACHE_TTL)
    return [CityStats(**c) for c in result]


@router.get("/categories", response_model=List[str])
async def get_job_categories():
    cached = get_cache("jobs:categories")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT job_category
            FROM jobs
            WHERE is_active = 1 AND status = 'open' 
              AND job_category IS NOT NULL AND job_category != ''
              AND published_at <= CURRENT_TIMESTAMP
            ORDER BY job_category
            """
        )
        result = [row["job_category"] for row in cursor.fetchall()]

    set_cache("jobs:categories", result, CACHE_TTL)
    return result

# 详情及来源部分不需要改动，因为如果是未来发布的，上面列表根本查不出。
# 但为了严谨，你也可以在 get_job 处加同样的条件。
@router.get("/{job_id}", response_model=JobWithCompany)
async def get_job(job_id: int):
    cache_key = f"jobs:detail:{job_id}"
    cached = get_cache(cache_key)
    if cached is not None:
        return JobWithCompany(**cached)

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT j.*,
                   c.name as company_name,
                   c.short_name as company_short_name,
                   c.logo_url as company_logo_url,
                   c.website_url as company_website_url,
                   c.career_page_url as company_career_page_url,
                   c.industry, c.company_type, c.size_range
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.id = %s AND j.is_active = 1 
              AND c.status = 1 AND j.published_at <= CURRENT_TIMESTAMP
            """,
            (job_id,)
        )
        job = cursor.fetchone()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    parsed = parse_job_data(job)
    set_cache(cache_key, parsed, CACHE_TTL)
    return JobWithCompany(**parsed)

@router.get("/{job_id}/sources", response_model=JobSourceListResponse)
async def get_job_sources(job_id: int):
    cache_key = f"jobs:sources:{job_id}"
    cached = get_cache(cache_key)
    if cached is not None:
        return JobSourceListResponse(**cached)

    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) as total FROM job_sources WHERE job_id = %s",
            (job_id,)
        )
        total = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT * FROM job_sources
            WHERE job_id = %s
            ORDER BY is_official DESC, is_primary_source DESC, id DESC
            """,
            (job_id,)
        )
        sources = cursor.fetchall()

    result = JobSourceListResponse(
        total=total,
        sources=[JobSource(**s) for s in sources]
    )
    set_cache(cache_key, result.model_dump(mode="json"), CACHE_TTL)
    return result


@router.post("", response_model=Job)
async def create_job(job: JobBase = Body(...), company_id: int = Body(..., embed=True)):
    """创建新职位"""
    with get_db_cursor(commit=True) as cursor:
        # 检查公司是否存在
        cursor.execute(
            "SELECT id FROM companies WHERE id = %s AND status = 1",
            (company_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Company not found")
        
        # 插入新职位
        cursor.execute(
            """
            INSERT INTO jobs (
                company_id, title, normalized_title, department, job_category, employment_type,
                is_campus, is_intern, location_text, city, province, district, address,
                education_requirement, education_level, experience_requirement,
                salary_text, salary_min, salary_max, salary_unit, salary_months,
                job_description, job_requirements, job_responsibilities, benefits,
                skill_tags, major_requirement, language_requirement, certificate_requirement,
                work_time, salary_payment, industry_requirement, job_level,
                apply_url, detail_url, source_site, source_job_id,
                published_at, deadline_at, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                company_id, job.title, job.normalized_title, job.department, job.job_category, job.employment_type,
                job.is_campus, job.is_intern, job.location_text, job.city, job.province, job.district, job.address,
                job.education_requirement, job.education_level, job.experience_requirement,
                job.salary_text, job.salary_min, job.salary_max, job.salary_unit, job.salary_months,
                job.job_description, job.job_requirements, job.job_responsibilities, job.benefits,
                job.skill_tags, job.major_requirement, job.language_requirement, job.certificate_requirement,
                job.work_time, job.salary_payment, job.industry_requirement, job.job_level,
                job.apply_url, job.detail_url, job.source_site, job.source_job_id,
                job.published_at, job.deadline_at, job.status
            )
        )
        
        # 获取新创建的职位
        job_id = cursor.lastrowid
        cursor.execute(
            "SELECT * FROM jobs WHERE id = %s",
            (job_id,)
        )
        new_job = cursor.fetchone()
    
    # 清除相关缓存
    set_cache("jobs:list:v2:default", None, 0)
    set_cache("jobs:cities", None, 0)
    set_cache("jobs:categories", None, 0)
    
    return Job(**new_job)


@router.put("/{job_id}", response_model=Job)
async def update_job(job_id: int, job: JobBase = Body(...)):
    """更新职位信息"""
    with get_db_cursor(commit=True) as cursor:
        # 检查职位是否存在
        cursor.execute(
            "SELECT id FROM jobs WHERE id = %s",
            (job_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 更新职位信息
        cursor.execute(
            """
            UPDATE jobs SET
                title = %s, normalized_title = %s, department = %s, job_category = %s, employment_type = %s,
                is_campus = %s, is_intern = %s, location_text = %s, city = %s, province = %s, district = %s, address = %s,
                education_requirement = %s, education_level = %s, experience_requirement = %s,
                salary_text = %s, salary_min = %s, salary_max = %s, salary_unit = %s, salary_months = %s,
                job_description = %s, job_requirements = %s, job_responsibilities = %s, benefits = %s,
                skill_tags = %s, major_requirement = %s, language_requirement = %s, certificate_requirement = %s,
                work_time = %s, salary_payment = %s, industry_requirement = %s, job_level = %s,
                apply_url = %s, detail_url = %s, source_site = %s, source_job_id = %s,
                published_at = %s, deadline_at = %s, status = %s
            WHERE id = %s
            """,
            (
                job.title, job.normalized_title, job.department, job.job_category, job.employment_type,
                job.is_campus, job.is_intern, job.location_text, job.city, job.province, job.district, job.address,
                job.education_requirement, job.education_level, job.experience_requirement,
                job.salary_text, job.salary_min, job.salary_max, job.salary_unit, job.salary_months,
                job.job_description, job.job_requirements, job.job_responsibilities, job.benefits,
                job.skill_tags, job.major_requirement, job.language_requirement, job.certificate_requirement,
                job.work_time, job.salary_payment, job.industry_requirement, job.job_level,
                job.apply_url, job.detail_url, job.source_site, job.source_job_id,
                job.published_at, job.deadline_at, job.status, job_id
            )
        )
        
        # 获取更新后的职位
        cursor.execute(
            "SELECT * FROM jobs WHERE id = %s",
            (job_id,)
        )
        updated_job = cursor.fetchone()
    
    # 清除相关缓存
    set_cache("jobs:list:v2:default", None, 0)
    set_cache(f"jobs:detail:{job_id}", None, 0)
    set_cache("jobs:cities", None, 0)
    set_cache("jobs:categories", None, 0)
    
    return Job(**updated_job)


@router.delete("/{job_id}")
async def delete_job(job_id: int):
    """删除职位"""
    with get_db_cursor(commit=True) as cursor:
        # 检查职位是否存在
        cursor.execute(
            "SELECT id FROM jobs WHERE id = %s",
            (job_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
        
        # 软删除职位
        cursor.execute(
            "UPDATE jobs SET is_active = 0, status = 'closed' WHERE id = %s",
            (job_id,)
        )
    
    # 清除相关缓存
    set_cache("jobs:list:v2:default", None, 0)
    set_cache(f"jobs:detail:{job_id}", None, 0)
    set_cache("jobs:cities", None, 0)
    set_cache("jobs:categories", None, 0)
    
    return {"message": "Job deleted successfully"}
