from fastapi import APIRouter, Query, HTTPException, Body
from typing import Optional, List

# from api.db import get_db_cursor
# from api.cache import get_cache, set_cache, build_cache_key
# from api.models import Company, CompanyListResponse, CompanyStats, CompanyJobListItem

from db import get_db_cursor
from cache import get_cache, set_cache, build_cache_key
from models import Company, CompanyListResponse, CompanyStats, CompanyJobListItem, CompanyBase


router = APIRouter(prefix="/api/companies", tags=["companies"])

CACHE_TTL = 300


@router.get("", response_model=CompanyListResponse)
async def get_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    industry: Optional[str] = None,
    city: Optional[str] = None,
    sort_by: str = Query("recent_job", pattern="^(recent_job|job_count|name)$")
):
    cacheable = page == 1 and page_size == 20 and not keyword and not industry and not city and sort_by == "recent_job"
    if cacheable:
        cache_key = "companies:list:default"
        cached = get_cache(cache_key)
        if cached is not None:
            return CompanyListResponse(**cached)

    offset = (page - 1) * page_size
    conditions = ["c.status = 1"]
    params = []

    if keyword:
        conditions.append("c.name LIKE %s")
        params.append(f"%{keyword}%")

    if industry:
        conditions.append("c.industry = %s")
        params.append(industry)

    if city:
        conditions.append("c.headquarters = %s")
        params.append(city)

    where_clause = " AND ".join(conditions)

    if sort_by == "recent_job":
        order_clause = "last_job_published_at DESC, c.id DESC"
    elif sort_by == "job_count":
        order_clause = "job_count DESC, c.id DESC"
    else:
        order_clause = "c.name ASC, c.id DESC"

    with get_db_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM companies c
            WHERE {where_clause}
            """,
            params
        )
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""
            SELECT c.*,
                   COUNT(j.id) AS job_count,
                   MAX(j.published_at) AS last_job_published_at
            FROM companies c
            LEFT JOIN jobs j
              ON c.id = j.company_id
             AND j.is_active = 1
             AND j.status = 'open'
             AND j.published_at <= CURRENT_TIMESTAMP
            WHERE {where_clause}
            GROUP BY c.id
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset]
        )
        companies = cursor.fetchall()

    company_list = []
    for c in companies:
        c_dict = dict(c)
        c_dict.pop("job_count", None)
        c_dict.pop("last_job_published_at", None)
        company_list.append(Company(**c_dict))

    result = CompanyListResponse(
        total=total,
        page=page,
        page_size=page_size,
        companies=company_list
    )

    if cacheable:
        set_cache(cache_key, result.model_dump(mode="json"), CACHE_TTL)

    return result


@router.get("/industries", response_model=List[str])
async def get_industries():
    cached = get_cache("companies:industries")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT industry
            FROM companies
            WHERE status = 1 AND industry IS NOT NULL AND industry != ''
            ORDER BY industry
            """
        )
        result = [row["industry"] for row in cursor.fetchall()]

    set_cache("companies:industries", result, CACHE_TTL)
    return result


@router.get("/hot", response_model=List[CompanyStats])
async def get_hot_companies(limit: int = Query(10, ge=1, le=50)):
    cache_key = f"companies:hot:{limit}"
    cached = get_cache(cache_key)
    if cached is not None:
        return [CompanyStats(**c) for c in cached]

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id AS company_id,
                   c.name AS company_name,
                   c.short_name AS company_short_name,
                   c.logo_url AS company_logo_url,
                   COUNT(j.id) AS job_count
            FROM companies c
            JOIN jobs j
              ON c.id = j.company_id
             AND j.is_active = 1
             AND j.status = 'open'
             AND j.published_at <= CURRENT_TIMESTAMP
            WHERE c.status = 1
            GROUP BY c.id
            ORDER BY job_count DESC, MAX(j.published_at) DESC
            LIMIT %s
            """,
            (limit,)
        )
        result = [dict(row) for row in cursor.fetchall()]

    set_cache(cache_key, result, CACHE_TTL)
    return [CompanyStats(**c) for c in result]


@router.get("/{company_id}", response_model=Company)
async def get_company(company_id: int):
    cache_key = f"companies:detail:{company_id}"
    cached = get_cache(cache_key)
    if cached is not None:
        return Company(**cached)

    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM companies WHERE id = %s AND status = 1",
            (company_id,)
        )
        company = cursor.fetchone()

    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    set_cache(cache_key, company, CACHE_TTL)
    return Company(**company)

@router.get("/{company_id}/jobs", response_model=List[CompanyJobListItem])
async def get_company_jobs(
    company_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    offset = (page - 1) * page_size

    cache_key = build_cache_key(
        f"companies:{company_id}:jobs",
        page=page,
        page_size=page_size,
    )
    cached = get_cache(cache_key)
    if cached is not None:
        return [CompanyJobListItem(**row) for row in cached]

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, title, employment_type, is_campus, is_intern, city, published_at
            FROM jobs
            WHERE company_id = %s AND is_active = 1 AND status = 'open'
              AND published_at <= CURRENT_TIMESTAMP
            ORDER BY published_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,
            (company_id, page_size, offset)
        )
        rows = cursor.fetchall()

    result = [dict(row) for row in rows]
    set_cache(cache_key, result, CACHE_TTL)
    return [CompanyJobListItem(**row) for row in rows]


@router.post("", response_model=Company)
async def create_company(company: CompanyBase = Body(...)):
    """创建新企业"""
    with get_db_cursor() as cursor:
        # 检查公司名称是否已存在
        cursor.execute(
            "SELECT id FROM companies WHERE name = %s",
            (company.name,)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Company with this name already exists")
        
        # 插入新公司
        cursor.execute(
            """
            INSERT INTO companies (
                name, alias_name, short_name, logo_url, website_url, career_page_url,
                industry, company_type, size_range, headquarters, description, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                company.name, company.alias_name, company.short_name, company.logo_url,
                company.website_url, company.career_page_url, company.industry, company.company_type,
                company.size_range, company.headquarters, company.description, company.tags
            )
        )
        
        # 获取新创建的公司
        company_id = cursor.lastrowid
        cursor.execute(
            "SELECT * FROM companies WHERE id = %s",
            (company_id,)
        )
        new_company = cursor.fetchone()
    
    # 清除相关缓存
    set_cache("companies:list:default", None, 0)
    set_cache("companies:industries", None, 0)
    
    return Company(**new_company)


@router.put("/{company_id}", response_model=Company)
async def update_company(company_id: int, company: CompanyBase = Body(...)):
    """更新企业信息"""
    with get_db_cursor() as cursor:
        # 检查公司是否存在
        cursor.execute(
            "SELECT id FROM companies WHERE id = %s",
            (company_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Company not found")
        
        # 检查公司名称是否与其他公司重复
        cursor.execute(
            "SELECT id FROM companies WHERE name = %s AND id != %s",
            (company.name, company_id)
        )
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Company with this name already exists")
        
        # 更新公司信息
        cursor.execute(
            """
            UPDATE companies SET
                name = %s, alias_name = %s, short_name = %s, logo_url = %s, website_url = %s, career_page_url = %s,
                industry = %s, company_type = %s, size_range = %s, headquarters = %s, description = %s, tags = %s
            WHERE id = %s
            """,
            (
                company.name, company.alias_name, company.short_name, company.logo_url,
                company.website_url, company.career_page_url, company.industry, company.company_type,
                company.size_range, company.headquarters, company.description, company.tags, company_id
            )
        )
        
        # 获取更新后的公司
        cursor.execute(
            "SELECT * FROM companies WHERE id = %s",
            (company_id,)
        )
        updated_company = cursor.fetchone()
    
    # 清除相关缓存
    set_cache("companies:list:default", None, 0)
    set_cache(f"companies:detail:{company_id}", None, 0)
    set_cache("companies:industries", None, 0)
    
    return Company(**updated_company)


@router.delete("/{company_id}")
async def delete_company(company_id: int):
    """删除企业"""
    with get_db_cursor() as cursor:
        # 检查公司是否存在
        cursor.execute(
            "SELECT id FROM companies WHERE id = %s",
            (company_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Company not found")
        
        # 软删除公司
        cursor.execute(
            "UPDATE companies SET status = 0 WHERE id = %s",
            (company_id,)
        )
    
    # 清除相关缓存
    set_cache("companies:list:default", None, 0)
    set_cache(f"companies:detail:{company_id}", None, 0)
    set_cache("companies:industries", None, 0)
    
    return {"message": "Company deleted successfully"}