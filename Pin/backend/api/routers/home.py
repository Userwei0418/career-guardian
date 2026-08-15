from fastapi import APIRouter
from typing import Dict, Any

# from api.cache import get_cache, set_cache
# from api.db import get_db_cursor
from cache import get_cache, set_cache
from db import get_db_cursor

router = APIRouter(prefix="/api/home", tags=["home"])

CACHE_TTL = 180


@router.get("")
async def get_home_data() -> Dict[str, Any]:
    cache_key = "home:default"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM jobs WHERE is_active = 1 AND status = 'open'")
        job_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) AS count FROM companies WHERE status = 1")
        company_count = cursor.fetchone()["count"]

        cursor.execute("""
            SELECT COUNT(DISTINCT city) AS count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND city IS NOT NULL AND city != ''
        """)
        city_count = cursor.fetchone()["count"]

        cursor.execute("""
            SELECT c.id as company_id,
                   c.name as company_name,
                   c.short_name as company_short_name,
                   c.logo_url as company_logo_url,
                   COUNT(j.id) as job_count
            FROM companies c
            JOIN jobs j
              ON c.id = j.company_id
             AND j.is_active = 1
             AND j.status = 'open'
             AND j.published_at <= CURRENT_TIMESTAMP
            WHERE c.status = 1
            GROUP BY c.id
            ORDER BY job_count DESC, MAX(j.published_at) DESC
            LIMIT 10
        """)
        hot_companies = list(cursor.fetchall())

        cursor.execute("""
            SELECT j.id, j.title, j.normalized_title, j.job_category, j.employment_type,
                   j.is_campus, j.is_intern, j.city, j.education_level,
                   j.salary_text, j.salary_min, j.salary_max, j.published_at,
                   j.company_id, j.source_site,
                   c.name as company_name, c.short_name as company_short_name, c.logo_url as company_logo_url
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.is_active = 1 AND j.status = 'open' AND c.status = 1
              AND j.published_at <= CURRENT_TIMESTAMP
            ORDER BY j.published_at DESC, j.id DESC
            LIMIT 20
        """)
        latest_jobs = list(cursor.fetchall())

    result = {
        "stats": {
            "job_count": job_count,
            "company_count": company_count,
            "city_count": city_count,
        },
        "hot_companies": hot_companies,
        "latest_jobs": latest_jobs,
    }

    set_cache(cache_key, result, CACHE_TTL)
    return result