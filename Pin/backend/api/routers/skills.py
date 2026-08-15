# analysis/skills.py - 完整替换

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from db import get_db_cursor
from cache import get_cache, set_cache
import json
from collections import Counter, defaultdict
import traceback

router = APIRouter(prefix="/api/analysis/skills", tags=["skills-analysis"])

CACHE_TTL = 600


# ============================================
# 1. Top 技能排行
# ============================================

@router.get("/top-skills")
async def get_top_skills(
    limit: int = Query(50, ge=10, le=100),
    category: Optional[str] = Query(None, description="筛选职类")
) -> List[Dict[str, Any]]:
    """获取热门技能排行"""
    cache_key = f"skills:top:{limit}:{category or 'all'}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            # 优先使用缓存表
            if category:
                cursor.execute("""
                    SELECT 
                        skill, 
                        CAST(JSON_UNQUOTE(JSON_EXTRACT(category_distribution, CONCAT('$."', %s, '"'))) AS UNSIGNED) AS count
                    FROM skill_stats_cache
                    WHERE JSON_EXTRACT(category_distribution, CONCAT('$."', %s, '"')) IS NOT NULL
                    ORDER BY count DESC
                    LIMIT %s
                """, (category, category, limit))
            else:
                cursor.execute("""
                    SELECT skill, total_count AS count
                    FROM skill_stats_cache
                    ORDER BY total_count DESC
                    LIMIT %s
                """, (limit,))
            
            result = [{"skill": row["skill"], "count": int(row["count"] or 0)} for row in cursor.fetchall()]
        
        # 降级方案：实时计算
        if not result:
            result = await _fallback_top_skills(limit, category)
        
        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in get_top_skills: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


async def _fallback_top_skills(limit: int, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """降级方案：实时统计技能"""
    with get_db_cursor() as cursor:
        where_clause = """
            j.is_active = 1 
            AND j.status = 'open'
            AND j.published_at <= CURRENT_TIMESTAMP
            AND JSON_TYPE(j.skill_tags) = 'ARRAY' 
            AND JSON_LENGTH(j.skill_tags) > 0
        """
        if category:
            where_clause += f" AND j.job_category = '{category}'"
        
        cursor.execute(f"""
            SELECT j.skill_tags
            FROM jobs j
            WHERE {where_clause}
            LIMIT 10000
        """)
        rows = cursor.fetchall()

    counter = Counter()
    for row in rows:
        tags = row["skill_tags"]
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except:
                continue
        if isinstance(tags, list):
            for tag in tags:
                if tag and isinstance(tag, str) and tag.strip():
                    counter[tag.strip()] += 1

    return [{"skill": skill, "count": count} for skill, count in counter.most_common(limit)]


# ============================================
# 2. 职类×技能矩阵（修复版）
# ============================================

@router.get("/category-skill-matrix")
async def get_category_skill_matrix(
    top_categories: int = Query(10, ge=3, le=20),
    top_skills: int = Query(15, ge=5, le=30),
) -> Dict[str, Any]:
    """职类-技能热力矩阵"""
    cache_key = f"skills:matrix:{top_categories}:{top_skills}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            # 1. 获取 Top 职类
            cursor.execute("""
                SELECT job_category, COUNT(*) AS cnt
                FROM jobs
                WHERE is_active = 1 AND status = 'open'
                  AND job_category IS NOT NULL 
                  AND job_category != ''
                  AND job_category != 'null'
                GROUP BY job_category 
                ORDER BY cnt DESC 
                LIMIT %s
            """, (top_categories,))
            categories = [r["job_category"] for r in cursor.fetchall()]

            if not categories:
                empty_result = {"categories": [], "skills": [], "data": []}
                set_cache(cache_key, empty_result, CACHE_TTL)
                return empty_result

            # 2. 获取 Top 技能
            cursor.execute("""
                SELECT skill, total_count
                FROM skill_stats_cache
                ORDER BY total_count DESC
                LIMIT %s
            """, (top_skills,))
            skills = [r["skill"] for r in cursor.fetchall()]

            if not skills:
                # 降级方案
                result = await _fallback_matrix(categories, top_skills)
                set_cache(cache_key, result, CACHE_TTL)
                return result

            # 3. 构建矩阵（优化版）
            matrix = []
            
            for cat in categories:
                row_data = {"category": cat}
                
                # 从缓存表提取该职类的技能分布
                cursor.execute("""
                    SELECT 
                        skill,
                        CAST(JSON_UNQUOTE(JSON_EXTRACT(category_distribution, CONCAT('$."', %s, '"'))) AS UNSIGNED) AS cat_count,
                        total_count
                    FROM skill_stats_cache
                    WHERE skill IN ({})
                """.format(','.join(['%s'] * len(skills))), [cat] + skills)
                
                skill_data = {row["skill"]: {
                    "cat_count": int(row["cat_count"] or 0),
                    "total": int(row["total_count"] or 1)
                } for row in cursor.fetchall()}
                
                # 计算该职类的技能总数（用于归一化）
                total_in_cat = sum(data["cat_count"] for data in skill_data.values()) or 1
                
                # 填充每个技能的占比
                for skill in skills:
                    data = skill_data.get(skill, {"cat_count": 0, "total": 1})
                    count = data["cat_count"]
                    # 计算该技能在该职类中的占比
                    percentage = round(count / total_in_cat * 100, 1) if total_in_cat > 0 else 0
                    row_data[skill] = percentage
                
                matrix.append(row_data)

        result = {
            "categories": categories,
            "skills": skills,
            "data": matrix,
        }
        
        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in get_category_skill_matrix: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


async def _fallback_matrix(categories: List[str], top_skills: int) -> Dict[str, Any]:
    """降级方案：实时计算矩阵"""
    with get_db_cursor() as cursor:
        placeholders = ','.join(['%s'] * len(categories))
        cursor.execute(f"""
            SELECT j.skill_tags, j.job_category
            FROM jobs j
            WHERE j.is_active = 1 
              AND j.status = 'open'
              AND j.published_at <= CURRENT_TIMESTAMP
              AND j.job_category IN ({placeholders})
              AND JSON_TYPE(j.skill_tags) = 'ARRAY'
              AND JSON_LENGTH(j.skill_tags) > 0
            LIMIT 10000
        """, categories)
        rows = cursor.fetchall()

    category_skill_counter = defaultdict(Counter)
    all_skills_counter = Counter()

    for row in rows:
        tags = row["skill_tags"]
        cat = row["job_category"]
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except:
                continue
        if isinstance(tags, list):
            for tag in tags:
                if tag and isinstance(tag, str) and tag.strip():
                    skill = tag.strip()
                    category_skill_counter[cat][skill] += 1
                    all_skills_counter[skill] += 1

    top_skill_list = [skill for skill, _ in all_skills_counter.most_common(top_skills)]

    matrix = []
    for cat in categories:
        row_data = {"category": cat}
        cat_counts = category_skill_counter.get(cat, {})
        total_in_cat = sum(cat_counts.values()) or 1
        for skill in top_skill_list:
            count = cat_counts.get(skill, 0)
            row_data[skill] = round(count / total_in_cat * 100, 1) if total_in_cat > 0 else 0
        matrix.append(row_data)

    return {
        "categories": categories,
        "skills": top_skill_list,
        "data": matrix,
    }


# ============================================
# 3. AI 趋势
# ============================================

@router.get("/ai-trend")
async def get_ai_skill_trend(days: int = Query(180, ge=30, le=730)) -> List[Dict[str, Any]]:
    """AI 职位占比趋势"""
    cache_key = f"skills:ai-trend:{days}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT
                    DATE_FORMAT(published_at, '%%Y-%%m') AS month,
                    COUNT(*) AS total_jobs,
                    SUM(CASE WHEN is_ai_related = 1 THEN 1 ELSE 0 END) AS ai_jobs
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                  AND published_at IS NOT NULL
                GROUP BY DATE_FORMAT(published_at, '%%Y-%%m')
                ORDER BY month ASC
            """, (days,))
            rows = cursor.fetchall()

        result = []
        for r in rows:
            total = r["total_jobs"] or 0
            ai_count = r["ai_jobs"] or 0
            result.append({
                "month": r["month"],
                "totalJobs": total,
                "aiJobs": ai_count,
                "aiRate": round(ai_count / total * 100, 2) if total > 0 else 0,
            })

        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in get_ai_skill_trend: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ============================================
# 4. 特定职类技能
# ============================================

@router.get("/category-top-skills")
async def get_category_top_skills(
    category: str = Query(..., min_length=1),
    limit: int = Query(15, ge=5, le=30),
) -> List[Dict[str, Any]]:
    """指定职类的 Top 技能"""
    cache_key = f"skills:cat:{category}:{limit}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    skill,
                    CAST(JSON_UNQUOTE(JSON_EXTRACT(category_distribution, CONCAT('$."', %s, '"'))) AS UNSIGNED) AS count
                FROM skill_stats_cache
                WHERE JSON_EXTRACT(category_distribution, CONCAT('$."', %s, '"')) IS NOT NULL
                ORDER BY count DESC
                LIMIT %s
            """, (category, category, limit))
            result = [{"skill": r["skill"], "count": int(r["count"] or 0)} for r in cursor.fetchall()]

        if not result:
            # 降级方案
            with get_db_cursor() as cursor:
                cursor.execute("""
                    SELECT j.skill_tags
                    FROM jobs j
                    WHERE j.is_active = 1 
                      AND j.status = 'open'
                      AND j.published_at <= CURRENT_TIMESTAMP
                      AND j.job_category = %s
                      AND JSON_TYPE(j.skill_tags) = 'ARRAY'
                      AND JSON_LENGTH(j.skill_tags) > 0
                    LIMIT 5000
                """, (category,))
                rows = cursor.fetchall()

            counter = Counter()
            for row in rows:
                tags = row["skill_tags"]
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except:
                        continue
                if isinstance(tags, list):
                    for tag in tags:
                        if tag and isinstance(tag, str) and tag.strip():
                            counter[tag.strip()] += 1

            result = [{"skill": s, "count": c} for s, c in counter.most_common(limit)]

        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in get_category_top_skills: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ============================================
# 5. 技能薪资分析
# ============================================

@router.get("/skill-salary")
async def get_skill_salary(skill: str = Query(..., min_length=1)) -> Dict[str, Any]:
    """分析特定技能的薪资分布"""
    cache_key = f"skills:salary:{skill}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            # 先从缓存表查
            cursor.execute("""
                SELECT avg_salary_min, avg_salary_max, total_count
                FROM skill_stats_cache
                WHERE skill = %s
            """, (skill,))
            row = cursor.fetchone()

            if row and row["total_count"]:
                result = {
                    "skill": skill,
                    "avgMin": round(float(row["avg_salary_min"] or 0), 2),
                    "avgMax": round(float(row["avg_salary_max"] or 0), 2),
                    "jobCount": int(row["total_count"]),
                }
            else:
                # 实时查询
                cursor.execute("""
                    SELECT 
                        AVG(j.salary_min) AS avg_min,
                        AVG(j.salary_max) AS avg_max,
                        COUNT(*) AS job_count
                    FROM jobs j
                    WHERE j.is_active = 1 
                      AND j.status = 'open'
                      AND JSON_CONTAINS(j.skill_tags, JSON_QUOTE(%s))
                      AND j.salary_min IS NOT NULL
                      AND j.salary_max IS NOT NULL
                      AND j.salary_min > 0
                      AND j.salary_max > 0
                """, (skill,))
                row = cursor.fetchone()

                if not row or not row["job_count"]:
                    raise HTTPException(status_code=404, detail="该技能暂无薪资数据")

                result = {
                    "skill": skill,
                    "avgMin": round(float(row["avg_min"] or 0), 2),
                    "avgMax": round(float(row["avg_max"] or 0), 2),
                    "jobCount": int(row["job_count"]),
                }

        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_skill_salary: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ============================================
# 6. 技能组合分析
# ============================================

@router.get("/skill-combinations")
async def get_skill_combinations(
    base_skill: str = Query(..., description="基础技能"),
    limit: int = Query(10, ge=5, le=20)
) -> List[Dict[str, Any]]:
    """分析与指定技能常见的搭配技能"""
    cache_key = f"skills:combo:{base_skill}:{limit}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT skill_tags
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND JSON_CONTAINS(skill_tags, JSON_QUOTE(%s))
                  AND JSON_TYPE(skill_tags) = 'ARRAY'
                LIMIT 5000
            """, (base_skill,))
            rows = cursor.fetchall()

        counter = Counter()
        for row in rows:
            tags = row["skill_tags"]
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except:
                    continue
            if isinstance(tags, list):
                for tag in tags:
                    if tag and tag != base_skill and isinstance(tag, str):
                        counter[tag.strip()] += 1

        total_jobs = len(rows) or 1
        result = [
            {
                "skill": skill, 
                "coOccurrence": count, 
                "percentage": round(count / total_jobs * 100, 1)
            }
            for skill, count in counter.most_common(limit)
        ]

        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in get_skill_combinations: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ============================================
# 7. 地域技能差异
# ============================================

@router.get("/skill-by-city")
async def get_skill_by_city(
    top_cities: int = Query(8, ge=3, le=15),
    top_skills: int = Query(10, ge=5, le=20)
) -> Dict[str, Any]:
    """城市-技能热力图"""
    cache_key = f"skills:city-map:{top_cities}:{top_skills}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            # 获取 Top 城市
            cursor.execute("""
                SELECT city, COUNT(*) AS cnt
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open' 
                  AND city IS NOT NULL
                  AND city != ''
                  AND city != 'null'
                GROUP BY city
                ORDER BY cnt DESC
                LIMIT %s
            """, (top_cities,))
            cities = [r["city"] for r in cursor.fetchall()]

            # 获取 Top 技能
            cursor.execute("""
                SELECT skill
                FROM skill_stats_cache
                ORDER BY total_count DESC
                LIMIT %s
            """, (top_skills,))
            skills = [r["skill"] for r in cursor.fetchall()]

            if not cities or not skills:
                empty_result = {"cities": [], "skills": [], "data": []}
                set_cache(cache_key, empty_result, CACHE_TTL)
                return empty_result

            # 构建矩阵
            matrix = []
            for city in cities:
                row = {"city": city}
                
                cursor.execute("""
                    SELECT 
                        skill,
                        CAST(JSON_UNQUOTE(JSON_EXTRACT(city_distribution, CONCAT('$."', %s, '"'))) AS UNSIGNED) AS city_count,
                        total_count
                    FROM skill_stats_cache
                    WHERE skill IN ({})
                """.format(','.join(['%s'] * len(skills))), [city] + skills)
                
                city_skills = {r["skill"]: int(r["city_count"] or 0) for r in cursor.fetchall()}
                total = sum(city_skills.values()) or 1
                
                for skill in skills:
                    row[skill] = round(city_skills.get(skill, 0) / total * 100, 1)
                
                matrix.append(row)

        result = {"cities": cities, "skills": skills, "data": matrix}
        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in get_skill_by_city: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")