from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from db import get_db_cursor
from cache import get_cache, set_cache

router = APIRouter(prefix="/api/company-lists", tags=["company-lists"])

CACHE_TTL = 600


@router.get("")
async def get_company_lists(
    category: Optional[str] = Query(None, description="分类筛选"),
) -> List[Dict[str, Any]]:
    """获取所有企业名录"""
    cache_key = f"company-lists:all:{category or 'all'}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        where = "WHERE is_active = 1"
        params = []
        if category:
            where += " AND category = %s"
            params.append(category)

        cursor.execute(
            f"""SELECT id, name, short_name, category, source_url, source_year,
                       total_count, description
                FROM company_lists
                {where}
                ORDER BY category, total_count DESC""",
            params
        )
        rows = cursor.fetchall()

    result = [dict(r) for r in rows]
    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.get("/categories")
async def get_categories() -> List[Dict[str, Any]]:
    """获取名录分类及每类数量"""
    cached = get_cache("company-lists:categories")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT category, COUNT(*) as list_count, SUM(total_count) as entry_count
            FROM company_lists
            WHERE is_active = 1
            GROUP BY category
            ORDER BY list_count DESC
        """)
        result = [dict(r) for r in cursor.fetchall()]

    set_cache("company-lists:categories", result, CACHE_TTL)
    return result


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """统计概览"""
    cached = get_cache("company-lists:stats")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as total FROM company_lists WHERE is_active = 1")
        total_lists = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM company_list_entries")
        total_entries = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(DISTINCT e.company_name_normalized) as total
            FROM company_list_entries e
            WHERE e.company_name_normalized IS NOT NULL AND e.company_name_normalized != ''
        """)
        unique_companies = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(DISTINCT e.matched_company_id) as total
            FROM company_list_entries e
            WHERE e.matched_company_id IS NOT NULL
        """)
        matched_with_jobs = cursor.fetchone()["total"]

    result = {
        "totalLists": total_lists,
        "totalEntries": total_entries,
        "uniqueCompanies": unique_companies,
        "matchedWithJobs": matched_with_jobs,
    }
    set_cache("company-lists:stats", result, CACHE_TTL)
    return result


@router.get("/matched-jobs")
async def get_matched_jobs_stats(
    list_id: Optional[int] = Query(None, description="指定名录ID"),
) -> Any:
    """分析：名录企业关联到的职位统计"""
    cache_key = f"company-lists:matched-jobs:{list_id or 'all'}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        if list_id:
            cursor.execute("""
                SELECT l.id, l.name, l.category,
                       COUNT(DISTINCT e.matched_company_id) as matched_companies,
                       COUNT(DISTINCT j.id) as job_count
                FROM company_lists l
                JOIN company_list_entries e ON l.id = e.list_id
                LEFT JOIN jobs j ON e.matched_company_id = j.company_id
                    AND j.is_active = 1 AND j.status = 'open'
                    AND j.published_at <= CURRENT_TIMESTAMP
                WHERE l.id = %s AND e.matched_company_id IS NOT NULL
                GROUP BY l.id
            """, (list_id,))
        else:
            cursor.execute("""
                SELECT l.id, l.name, l.category,
                       COUNT(DISTINCT e.matched_company_id) as matched_companies,
                       COUNT(DISTINCT j.id) as job_count
                FROM company_lists l
                JOIN company_list_entries e ON l.id = e.list_id
                LEFT JOIN jobs j ON e.matched_company_id = j.company_id
                    AND j.is_active = 1 AND j.status = 'open'
                    AND j.published_at <= CURRENT_TIMESTAMP
                WHERE e.matched_company_id IS NOT NULL
                GROUP BY l.id
                ORDER BY job_count DESC
            """)

        result = [dict(r) for r in cursor.fetchall()]

    set_cache(cache_key, result, CACHE_TTL)
    return result


# 注意：以下动态路由 /{list_id} 和 /{list_id}/entries
# 必须放在所有固定路径路由之后，否则会拦截 /stats、/matched-jobs 等


@router.get("/{list_id}")
async def get_company_list_detail(list_id: int) -> Dict[str, Any]:
    """获取单个名录详情"""
    cache_key = f"company-lists:detail:{list_id}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT id, name, short_name, category, source_url, source_year,
                   total_count, description
            FROM company_lists
            WHERE id = %s AND is_active = 1
        """, (list_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="名录不存在")

    result = dict(row)
    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.get("/{list_id}/entries")
async def get_list_entries(
    list_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    keyword: Optional[str] = Query(None, description="搜索企业名称"),
) -> Dict[str, Any]:
    """获取名录下的企业列表"""
    cache_key = f"company-lists:entries:{list_id}:{page}:{page_size}:{keyword or ''}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    offset = (page - 1) * page_size

    with get_db_cursor() as cursor:
        where = "WHERE e.list_id = %s"
        params = [list_id]

        if keyword:
            where += " AND e.company_name LIKE %s"
            params.append(f"%{keyword}%")

        cursor.execute(
            f"""SELECT COUNT(*) as total
                FROM company_list_entries e
                {where}""",
            params
        )
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""SELECT e.id, e.company_name, e.rank_num, e.stock_code, e.province,
                       e.matched_company_id, e.match_score,
                       c.name as matched_company_name,
                       c.short_name as matched_company_short_name,
                       c.logo_url as matched_company_logo_url
                FROM company_list_entries e
                LEFT JOIN companies c ON e.matched_company_id = c.id AND c.status = 1
                {where}
                ORDER BY e.rank_num ASC, e.id ASC
                LIMIT %s OFFSET %s""",
            params + [page_size, offset]
        )
        entries = cursor.fetchall()

    result = {
        "listId": list_id,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "entries": [dict(r) for r in entries],
    }
    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.get("/company/{company_name:path}")
async def find_company_lists(company_name: str) -> List[Dict[str, Any]]:
    """查询某公司属于哪些名录"""
    decoded = company_name.strip()
    if not decoded:
        return []

    cache_key = f"company-lists:company:{decoded}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT l.id, l.name, l.category, l.source_year,
                   e.company_name, e.rank_num, e.matched_company_id
            FROM company_list_entries e
            JOIN company_lists l ON e.list_id = l.id
            WHERE e.company_name LIKE %s OR e.company_name_normalized LIKE %s
            ORDER BY l.category, l.name
        """, (f"%{decoded}%", f"%{decoded}%"))

        result = [dict(r) for r in cursor.fetchall()]

    set_cache(cache_key, result, CACHE_TTL)
    return result
