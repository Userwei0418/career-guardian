# salary_analysis.py - 城市字段硬核清洗、大类降维、统计过滤版

from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from db import get_db_cursor
from cache import get_cache, set_cache, clear_cache_pattern
import numpy as np
from collections import defaultdict
import traceback
import re

router = APIRouter(prefix="/api/analysis/salary", tags=["salary-analysis"])
CACHE_TTL = 600

# ─────────────────────────────────────────
# 核心引擎：行业大类智能字典 (Bucket Mapping)
# ─────────────────────────────────────────
BROAD_MAPPING = {
    "IT/互联网研发": ["java", "c++", "前端", "后端", "测试", "运维", "数据", "算法", "开发", "软件", "架构", "web", "android", "ios", "ai", "python", "golang"],
    "产品与设计": ["产品", "设计", "ui", "ux", "交互", "视觉", "原画", "体验", "策划"],
    "市场与运营": ["运营", "市场", "营销", "pr", "公关", "新媒体", "活动", "内容", "电商", "媒介"],
    "销售与商务": ["销售", "商务", "bd", "客户", "招商", "渠道", "顾问", "代表", "销售专员"],
    "职能与管理": ["财务", "会计", "审计", "人事", "hr", "行政", "法务", "合规", "助理", "秘书", "采购", "后勤"],
    "医疗与健康": ["医疗", "医药", "医生", "临床", "护士", "制药", "生物", "检验", "药代"],
    "教育与外贸": ["教育", "教师", "培训", "外贸", "英语", "翻译", "讲师", "留学", "班主任"]
}

def get_broad_category(query: str):
    q = query.strip()
    for broad_name, keywords in BROAD_MAPPING.items():
        if broad_name in q or q in broad_name:
            return broad_name, keywords
    return q, [q.lower()]

def normalize_edu(raw: str) -> str:
    if not raw: return ""
    raw = str(raw).lower()
    if "博士" in raw: return "博士"
    if "硕士" in raw or "研究" in raw: return "硕士"
    if "本" in raw or "学士" in raw: return "本科"
    if "大专" in raw or "专" in raw: return "大专"
    return ""

def normalize_city(raw: str) -> str:
    """硬核城市提取：将一切垃圾数据拒之门外"""
    if not raw: return ""
    c = str(raw).strip().split('-')[0].split('·')[0].split('/')[0].split(',')[0].strip()
    
    # 1. 过滤任何包含英文字母的（排除 United States, Remote 等）
    if re.search(r'[a-zA-Z]', c):
        return ""
        
    # 2. 清理后缀
    c = re.sub(r'(省|市|回族自治区|维吾尔自治区|壮族自治区|自治区)$', '', c)
    if not c: return ""

    # 3. 拦截明显的错位字段
    invalid_words = ["其它", "其他", "销售", "技术", "大类", "研发", "前端", "后端", "运营", "测试", "管理", "工程师", "不限", "全省", "专员", "代表", "助理", "主管", "全国", "中国", "全职", "异地", "驻场"]
    if any(w in c for w in invalid_words):
        return ""
        
    # 4. 长度限制
    if len(c) < 2 or len(c) > 6:
        return ""
        
    # 5. 必须是纯汉字
    if not re.fullmatch(r'[\u4e00-\u9fa5]+', c):
        return ""
        
    return c

def normalize_to_monthly(min_val: float, max_val: float, unit: str, months: int) -> Optional[float]:
    months = max(1, min(24, int(months or 12)))
    try:
        if unit == '年': lo, hi = min_val / months, max_val / months
        elif unit == '日': lo, hi = min_val * 21.75, max_val * 21.75
        elif unit == '小时': lo, hi = min_val * 8 * 21.75, max_val * 8 * 21.75
        else: lo, hi = min_val, max_val

        if 1500 <= lo <= 300000 and 1500 <= hi <= 300000 and hi >= lo:
            return (lo + hi) / 2
    except Exception:
        pass
    return None

def format_sub_name(kw: str) -> str:
    upper_words = ['ui','ux','pr','hr','bd','it','ai','ios','web','java','c++','python','golang']
    return kw.upper() if kw in upper_words else kw.title()

BASE_WHERE = """
    j.salary_min IS NOT NULL AND j.salary_min > 0
    AND j.salary_max IS NOT NULL AND j.salary_max >= j.salary_min
    AND j.published_at <= CURRENT_TIMESTAMP
"""

def _salary_select() -> str:
    return """
        COALESCE(j.job_category, '') AS job_category,
        COALESCE(j.title, '') AS title,
        COALESCE(j.department, '') AS department,
        COALESCE(j.skill_tags, '') AS skill_tags,
        COALESCE(j.city, j.location_text, '') AS city,
        COALESCE(j.education_level, j.education_requirement, '') AS education,
        j.salary_min,
        j.salary_max,
        COALESCE(NULLIF(TRIM(j.salary_unit), ''), '月') AS salary_unit,
        COALESCE(NULLIF(j.salary_months, 0), 12) AS salary_months
    """

# ─────────────────────────────────────────
# 接口1：职类箱线图 (保留离群值供观测)
# ─────────────────────────────────────────
@router.get("/category-boxplot")
async def get_salary_category_boxplot(
    min_samples: int = Query(5, ge=2), 
) -> List[Dict[str, Any]]:
    cache_key = f"salary:category-boxplot:{min_samples}"
    cached = get_cache(cache_key)
    if cached is not None: return cached

    try:
        with get_db_cursor() as cursor:
            cursor.execute(f"SELECT {_salary_select()} FROM jobs j WHERE {BASE_WHERE}")
            rows = cursor.fetchall()

        category_data: dict[str, list[float]] = defaultdict(list)
        
        for row in rows:
            text_pool = f"{row['title']} {row['job_category']} {row['skill_tags']} {row['department']}".lower()
            monthly = normalize_to_monthly(row["salary_min"], row["salary_max"], row["salary_unit"], row["salary_months"])
            if not monthly: continue

            matched = False
            for _, keywords in BROAD_MAPPING.items():
                for kw in keywords:
                    if kw in text_pool:
                        category_data[format_sub_name(kw)].append(monthly)
                        matched = True
                        break 
                if matched: break

        result = []
        for cat, salaries in category_data.items():
            if len(salaries) < min_samples: continue
            arr = np.array(sorted(salaries))
            q1, med, q3 = np.percentile(arr, [25, 50, 75])
            iqr = q3 - q1
            inliers = arr[(arr >= q1 - 1.5 * iqr) & (arr <= q3 + 1.5 * iqr)]
            outliers = arr[(arr < q1 - 1.5 * iqr) | (arr > q3 + 1.5 * iqr)]

            result.append({
                "category": cat, "sampleSize": int(len(arr)),
                "min": int(inliers.min()) if len(inliers) else int(arr.min()),
                "Q1": int(q1), "median": int(med), "Q3": int(q3),
                "max": int(inliers.max()) if len(inliers) else int(arr.max()),
                "mean": int(arr.mean()), "std": int(arr.std()),
                "outliers": [int(o) for o in outliers[:8]],
                "outlierRate": round(len(outliers) / len(arr) * 100, 1),
            })

        result.sort(key=lambda x: x["median"], reverse=True)
        result = result[:25]
        set_cache(cache_key, result, CACHE_TTL)
        return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────
# 接口2：城市薪资对比 (核心修改：数学层面剔除极端值)
# ─────────────────────────────────────────
@router.get("/city-comparison")
async def get_salary_city_comparison(
    category: str = Query(..., min_length=1),
    min_samples: int = Query(5, ge=1), 
) -> List[Dict[str, Any]]:
    broad_name, keywords = get_broad_category(category)
    cache_key = f"salary:city-compare:cleaned:{broad_name}:{min_samples}"
    cached = get_cache(cache_key)
    if cached is not None: return cached

    try:
        or_clauses = []
        params = []
        for kw in keywords:
            or_clauses.append("(LOWER(j.title) LIKE %s OR LOWER(j.job_category) LIKE %s OR LOWER(j.skill_tags) LIKE %s)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
        
        where_sql = f"({ ' OR '.join(or_clauses) })"

        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT {_salary_select()} FROM jobs j 
                WHERE {BASE_WHERE} AND {where_sql}
            """, params)
            rows = cursor.fetchall()

        # 第一步：收集本板块所有的有效薪资数据
        raw_records = []
        all_salaries = []
        
        for row in rows:
            city = normalize_city(row["city"])
            if not city: continue
            monthly = normalize_to_monthly(row["salary_min"], row["salary_max"], row["salary_unit"], row["salary_months"])
            if monthly: 
                raw_records.append((city, monthly))
                all_salaries.append(monthly)

        if not raw_records:
            raise HTTPException(status_code=404, detail=f"数据库暂无「{broad_name}」在各城市的有效数据")

        # 第二步：计算全局阈值 (Global Outlier Filter) 
        # 目的是彻底阻断某些年薪按月薪填写的超级高薪破坏整个城市的均值
        arr_all = np.array(all_salaries)
        q1, q3 = np.percentile(arr_all, [25, 75])
        iqr = q3 - q1
        
        # 宽容剔除：仅剔除严重离群点 (Q3 + 2.5 * IQR) 并且最高不允许超过 80000(8万/月，即百万年薪级距上限)
        # 例如市场均值 1.5万，Q3 2.5万，那么超过 2.5w + 2.5万(IQR)*2.5 = 8万 左右的数据将被直接丢弃
        upper_bound = min(q3 + 2.5 * iqr, 80000)

        # 第三步：按城市分配已过滤的健康数据
        city_data: dict[str, list[float]] = defaultdict(list)
        for city, val in raw_records:
            if val <= upper_bound:
                city_data[city].append(val)

        result = []
        for city, salaries in city_data.items():
            if len(salaries) < min_samples: continue
            arr = np.array(salaries)
            result.append({
                "city": city, "sampleSize": int(len(arr)),
                "salaryMedian": int(np.median(arr)),
                "avgSalary": int(arr.mean()),
                "salaryP25": int(np.percentile(arr, 25)),
                "salaryP75": int(np.percentile(arr, 75)),
                "salaryStd": int(arr.std()),
            })

        result.sort(key=lambda x: x["salaryMedian"], reverse=True)
        set_cache(cache_key, result[:20], CACHE_TTL)
        return result[:20]
    except HTTPException: raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────
# 接口3：学历溢价
# ─────────────────────────────────────────
@router.get("/education-premium")
async def get_education_premium(
    category: str = Query(default=""),
) -> List[Dict[str, Any]]:
    broad_name, keywords = get_broad_category(category)
    cache_key = f"salary:edu-premium:cleaned:{broad_name}"
    cached = get_cache(cache_key)
    if cached is not None: return cached

    try:
        or_clauses = []
        params = []
        for kw in keywords:
            or_clauses.append("(LOWER(j.title) LIKE %s OR LOWER(j.job_category) LIKE %s OR LOWER(j.skill_tags) LIKE %s)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
        
        where_sql = f"({ ' OR '.join(or_clauses) })"

        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT {_salary_select()} FROM jobs j 
                WHERE {BASE_WHERE} AND {where_sql}
            """, params)
            rows = cursor.fetchall()

        # 为保证均值与中位数的科学性，在这里也拦截掉离群值(同上，上限8万)
        valid_records = []
        all_salaries = []
        for row in rows:
            monthly = normalize_to_monthly(row["salary_min"], row["salary_max"], row["salary_unit"], row["salary_months"])
            edu = normalize_edu(row["education"])
            if monthly and edu:
                valid_records.append((row, edu, monthly))
                all_salaries.append(monthly)

        if not valid_records:
            raise HTTPException(status_code=404, detail="无数据")
            
        arr_all = np.array(all_salaries)
        upper_bound = min(np.percentile(arr_all, 75) + 2.5 * (np.percentile(arr_all, 75) - np.percentile(arr_all, 25)), 80000)

        grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        
        for row, edu, monthly in valid_records:
            if monthly > upper_bound: continue

            text_pool = f"{row['title']} {row['job_category']} {row['skill_tags']}".lower()
            matched_subs = []
            for kw in keywords:
                if kw in text_pool:
                    matched_subs.append(format_sub_name(kw))
            
            grouped[f"🌟 {broad_name} (大盘)"][edu].append(monthly)
            for sub in matched_subs:
                grouped[sub][edu].append(monthly)

        result = []
        for c, edu_dict in grouped.items():
            b_arr = np.array(edu_dict.get("本科", []))
            m_arr = np.array(edu_dict.get("硕士", []))
            p_arr = np.array(edu_dict.get("博士", []))

            if len(b_arr) < 3 or len(m_arr) < 3: continue

            b_med, m_med = int(np.median(b_arr)), int(np.median(m_arr))
            p_med = int(np.median(p_arr)) if len(p_arr) >= 2 else 0

            premium_m = m_med - b_med
            result.append({
                "category": c,
                "bachelorMedian": b_med, "masterMedian": m_med, "phdMedian": p_med,
                "premiumMaster": premium_m, "premiumPhd": p_med - m_med if p_med else 0,
                "masterRoi": round(premium_m / b_med * 100, 1) if b_med else 0,
                "bachelorSampleSize": int(len(b_arr)),
                "masterSampleSize": int(len(m_arr)),
                "phdSampleSize": int(len(p_arr)),
            })

        if not result:
            raise HTTPException(status_code=404, detail=f"暂无「{broad_name}」相关的学历溢价数据")

        result.sort(key=lambda x: (x["category"].startswith("🌟"), x["premiumMaster"]), reverse=True)
        set_cache(cache_key, result[:12], CACHE_TTL)
        return result[:12]

    except HTTPException: raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear-cache")
async def clear_salary_cache():
    clear_cache_pattern("salary:*")
    return {"message": "缓存已清理"}