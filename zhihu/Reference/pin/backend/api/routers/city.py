from fastapi import APIRouter, Query
from typing import Dict, Any, List, Optional
from db import get_db_cursor
from cache import get_cache, set_cache, delete_cache
from collections import defaultdict
import re

router = APIRouter(prefix="/api/analysis/city", tags=["city-analysis"])

CACHE_TTL = 600

# ─────────────────────────────────────────
# 数据清洗套件
# ─────────────────────────────────────────

PROVINCES_TO_EXCLUDE = {
    "江苏", "广东", "浙江", "山东", "河南", "四川", "湖北", "湖南", 
    "河北", "福建", "安徽", "辽宁", "陕西", "江西", "广西", "山西", 
    "云南", "吉林", "黑龙江", "内蒙古", "新疆", "贵州", "甘肃", "海南", 
    "宁夏", "青海", "西藏", "台湾", "香港", "澳门"
}

INVALID_CITY_KEYWORDS = {
    "不限", "全国", "多地", "待定", "其他", "其它", "全省", "各地",
    "线上", "远程", "在家", "SOHO", "自由", "弹性"
}

INVALID_CATEGORY_KEYWORDS = {
    "全职", "实习", "兼职", "校招", "社招", "应届", "往届", "届", 
    "通用", "类别", "职能", "大类", "其他", "其它", "不限", "待定",
    "校园招聘", "社会招聘", "春季", "秋季", "暑期", "寒假", "专场", "批次"
}


def normalize_city(raw: str) -> str:
    """智能提取城市名"""
    if not raw: 
        return ""
    
    c = str(raw).strip()
    for sep in ['-', '·', '/', ',', '，', '、']:
        c = c.split(sep)[0].strip()
    
    # 移除行政后缀
    c = re.sub(r'(省|回族自治区|维吾尔自治区|壮族自治区|自治区|特别行政区)$', '', c)
    
    # 处理"XX市"格式
    if c.endswith('市') and len(c) > 2:
        c_without_shi = c[:-1]
        if c_without_shi not in PROVINCES_TO_EXCLUDE:
            c = c_without_shi
    
    if not c:
        return ""
    
    # 黑名单过滤
    if c in INVALID_CITY_KEYWORDS:
        return ""
    
    if c in PROVINCES_TO_EXCLUDE and c not in {"北京", "上海", "天津", "重庆"}:
        return ""
    
    if re.search(r'[a-zA-Z]', c):
        return ""
    
    if len(c) < 2 or len(c) > 6:
        return ""
    
    if not re.fullmatch(r'[\u4e00-\u9fa5]+', c):
        return ""
    
    # 排除职能词
    职能词 = {"技术", "研发", "销售", "运营", "测试", "管理", "市场", "产品"}
    if c in 职能词:
        return ""
    
    return c


def is_valid_category(category: str) -> bool:
    """判断职类是否有效"""
    if not category or len(category) > 20 or len(category) < 2:
        return False
    
    for keyword in INVALID_CATEGORY_KEYWORDS:
        if keyword in category:
            return False
    
    if re.search(r'\d', category):
        return False
    
    char_counts = {}
    for char in category:
        char_counts[char] = char_counts.get(char, 0) + 1
    
    max_count = max(char_counts.values()) if char_counts else 0
    if max_count > len(category) * 0.5:
        return False
    
    return True


def normalize_to_monthly(min_val, max_val, unit: str, months) -> Optional[float]:
    """智能换算薪资"""
    try:
        if min_val is None:
            return None
            
        try:
            months_int = int(months) if months else 12
            months_int = max(1, min(24, months_int))
        except (ValueError, TypeError):
            months_int = 12
        
        unit = (unit or "月").strip()
        
        try:
            min_v = float(min_val)
            max_v = float(max_val) if max_val is not None else min_v
        except (ValueError, TypeError):
            return None
        
        if unit in ('月', '') and 0 < min_v <= 300 and 0 < max_v <= 500:
            min_v *= 1000
            max_v *= 1000
            
        if unit == '年' and 0 < min_v <= 500 and 0 < max_v <= 1000:
            min_v *= 10000
            max_v *= 10000

        if unit == '年':
            lo, hi = min_v / months_int, max_v / months_int
        elif unit in ('日', '天'):
            lo, hi = min_v * 21.75, max_v * 21.75
        elif unit == '小时':
            lo, hi = min_v * 8 * 21.75, max_v * 8 * 21.75
        else:
            lo, hi = min_v, max_v
        
        if 1500 <= lo <= 300000 and 1500 <= hi <= 300000 and hi >= lo:
            return (lo + hi) / 2
            
    except Exception as e:
        print(f"normalize_to_monthly error: {e}")
        return None
        
    return None


def calculate_median(values: List[float]) -> float:
    """安全的中位数计算"""
    if not values:
        return 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    else:
        return sorted_vals[n // 2]


def calculate_percentile(values: List[float], percentile: float) -> float:
    """安全的百分位数计算"""
    if not values:
        return 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    index = int((n - 1) * percentile)
    return sorted_vals[index]


def remove_outliers(values: List[float], iqr_multiplier: float = 2.5) -> List[float]:
    """使用 IQR 方法移除异常值"""
    if len(values) < 4:
        return values
        
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[n * 3 // 4]
    iqr = q3 - q1
    
    upper_bound = min(q3 + iqr_multiplier * iqr, 80000)
    lower_bound = max(q1 - iqr_multiplier * iqr, 1500)
    
    return [v for v in values if lower_bound <= v <= upper_bound]


# 基础查询条件
BASE_WHERE_SALARY = "is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND salary_min IS NOT NULL AND salary_min > 0"
BASE_WHERE = "is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP"


# ─────────────────────────────────────────
# 接口实现
# ─────────────────────────────────────────

@router.delete("/clear-cache")
async def clear_city_cache() -> Dict[str, str]:
    """清除城市分析相关的所有缓存"""
    try:
        # 清除所有可能的缓存键
        patterns = [
            "city:bubble:*",
            "city:heatmap:*",
            "city:salary-compare:*",
            "city:campus-rank:*",
            "city:valid-categories:*"
        ]
        
        cleared_count = 0
        for pattern in patterns:
            # 如果你的 cache 模块支持 pattern 删除
            # 这里简化处理：删除常见的键
            for i in range(10, 100, 10):
                try:
                    delete_cache(f"city:bubble:{i}")
                    delete_cache(f"city:heatmap:{i}:12")
                    delete_cache(f"city:campus-rank:20:{i}")
                    delete_cache(f"city:valid-categories:{i}")
                    cleared_count += 1
                except:
                    pass
        
        return {"message": f"Cache cleared successfully, attempted {cleared_count} keys"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/bubble-data")
async def get_city_bubble_data(min_jobs: int = Query(50, ge=10)) -> List[Dict[str, Any]]:
    """城市性价比气泡图数据"""
    cache_key = f"city:bubble:{min_jobs}"
    cached = get_cache(cache_key)
    if cached is not None: 
        return cached

    try:
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT city, salary_min, salary_max, salary_unit, salary_months, is_campus 
                FROM jobs 
                WHERE {BASE_WHERE_SALARY}
            """)
            rows = cursor.fetchall()

        city_data = defaultdict(lambda: {"salaries": [], "campus": 0})
        all_salaries = []
        
        for row in rows:
            city = normalize_city(row["city"])
            if not city: 
                continue
                
            monthly = normalize_to_monthly(
                row["salary_min"], 
                row["salary_max"], 
                row["salary_unit"], 
                row["salary_months"]
            )
            
            if monthly:
                city_data[city]["salaries"].append(monthly)
                all_salaries.append(monthly)
                if row.get("is_campus"):
                    city_data[city]["campus"] += 1
        
        if not all_salaries:
            return []
        
        cleaned_salaries = remove_outliers(all_salaries)
        max_salary = max(cleaned_salaries) if cleaned_salaries else 80000

        result = []
        for city, data in city_data.items():
            valid_salaries = [s for s in data["salaries"] if s <= max_salary]
            
            if len(valid_salaries) < min_jobs: 
                continue
            
            result.append({
                "city": city,
                "job_count": len(valid_salaries),
                "salary_median": round(calculate_median(valid_salaries)),
                "campus_job_count": data["campus"],
            })
        
        result.sort(key=lambda x: x["job_count"], reverse=True)
        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in bubble-data: {e}")
        import traceback
        traceback.print_exc()
        return []


@router.get("/category-heatmap")
async def get_city_category_heatmap(
    top_cities: int = Query(15, ge=5, le=30),
    top_categories: int = Query(12, ge=5, le=20),
) -> Dict[str, Any]:
    """城市×职类热力图数据"""
    cache_key = f"city:heatmap:{top_cities}:{top_categories}"
    cached = get_cache(cache_key)
    if cached is not None: 
        return cached

    try:
        with get_db_cursor() as cursor:
            # 修复：不使用表别名 j
            cursor.execute(f"""
                SELECT city, job_category 
                FROM jobs 
                WHERE {BASE_WHERE}
            """)
            rows = cursor.fetchall()

        city_counts = defaultdict(int)
        cat_counts = defaultdict(int)
        matrix_counts = defaultdict(lambda: defaultdict(int))

        for row in rows:
            city = normalize_city(row["city"])
            cat = str(row["job_category"] or "").strip()
            
            if not city or not is_valid_category(cat): 
                continue
            
            city_counts[city] += 1
            cat_counts[cat] += 1
            matrix_counts[cat][city] += 1

        print(f"[DEBUG Heatmap] 清洗后城市数: {len(city_counts)}, 职类数: {len(cat_counts)}")

        cities = [
            k for k, v in sorted(city_counts.items(), key=lambda item: item[1], reverse=True)
        ][:top_cities]
        
        categories = [
            k for k, v in sorted(cat_counts.items(), key=lambda item: item[1], reverse=True)
        ][:top_categories]

        heatmap_data = []
        for cat_idx, cat in enumerate(categories):
            for city_idx, city in enumerate(cities):
                count = matrix_counts[cat][city]
                heatmap_data.append([city_idx, cat_idx, count])

        result = {
            "cities": cities,
            "categories": categories,
            "data": heatmap_data, 
        }
        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in category-heatmap: {e}")
        import traceback
        traceback.print_exc()
        return {"cities": [], "categories": [], "data": []}


@router.get("/salary-comparison")
async def get_city_salary_comparison(
    category: str = Query(..., min_length=1),
    limit: int = Query(15, ge=3, le=30),
    min_samples: int = Query(5, ge=3, le=20),
) -> List[Dict[str, Any]]:
    """指定职类的城市薪资对比（箱线图数据）"""
    cache_key = f"city:salary-compare:{category}:{limit}:{min_samples}"
    cached = get_cache(cache_key)
    if cached is not None: 
        return cached

    try:
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT city, salary_min, salary_max, salary_unit, salary_months
                FROM jobs
                WHERE {BASE_WHERE_SALARY} AND job_category = %s
            """, (category,))
            rows = cursor.fetchall()

        city_salaries = defaultdict(list)
        all_salaries = []
        
        for row in rows:
            city = normalize_city(row["city"])
            if not city: 
                continue
                
            monthly = normalize_to_monthly(
                row["salary_min"], 
                row["salary_max"], 
                row["salary_unit"], 
                row["salary_months"]
            )
            
            if monthly:
                city_salaries[city].append(monthly)
                all_salaries.append(monthly)
                
        if not all_salaries: 
            return []
        
        cleaned = remove_outliers(all_salaries)
        max_salary = max(cleaned) if cleaned else 80000
        
        result = []
        for city, salaries in city_salaries.items():
            valid_salaries = [s for s in salaries if s <= max_salary]
            n = len(valid_salaries)
            
            if n < min_samples: 
                continue
            
            sorted_sal = sorted(valid_salaries)
            
            result.append({
                "city": city,
                "sample_size": n,
                "salary_min": round(sorted_sal[0]),
                "q1": round(calculate_percentile(sorted_sal, 0.25)),
                "median": round(calculate_median(sorted_sal)),
                "q3": round(calculate_percentile(sorted_sal, 0.75)),
                "salary_max": round(sorted_sal[-1]),
            })
        
        result.sort(key=lambda x: x["median"], reverse=True)
        result = result[:limit]
        
        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in salary-comparison: {e}")
        import traceback
        traceback.print_exc()
        return []


@router.get("/campus-rank")
async def get_city_campus_rank(
    limit: int = Query(20, ge=5, le=50),
    min_total_jobs: int = Query(50, ge=10),
) -> List[Dict[str, Any]]:
    """城市校招友好度排名"""
    cache_key = f"city:campus-rank:{limit}:{min_total_jobs}"
    cached = get_cache(cache_key)
    if cached is not None: 
        return cached

    try:
        with get_db_cursor() as cursor:
            # 修复：不使用表别名 j
            cursor.execute(f"""
                SELECT city, is_campus, is_intern 
                FROM jobs 
                WHERE {BASE_WHERE}
            """)
            rows = cursor.fetchall()

        city_stats = defaultdict(lambda: {"total": 0, "campus": 0, "intern": 0})
        
        for row in rows:
            city = normalize_city(row["city"])
            if not city: 
                continue
            
            city_stats[city]["total"] += 1
            if row.get("is_campus"): 
                city_stats[city]["campus"] += 1
            if row.get("is_intern"): 
                city_stats[city]["intern"] += 1

        print(f"[DEBUG Campus] 清洗后城市数: {len(city_stats)}")

        result = []
        for city, stats in city_stats.items():
            total = stats["total"]
            if total < min_total_jobs: 
                continue
                
            campus = stats["campus"]
            result.append({
                "city": city,
                "total_jobs": total,
                "campus_jobs": campus,
                "campus_rate": round(campus / total * 100, 1) if total > 0 else 0,
                "intern_jobs": stats["intern"],
            })
        
        result.sort(key=lambda x: x["campus_jobs"], reverse=True)
        result = result[:limit]
        
        set_cache(cache_key, result, CACHE_TTL)
        return result
        
    except Exception as e:
        print(f"Error in campus-rank: {e}")
        import traceback
        traceback.print_exc()
        return []


@router.get("/valid-categories")
async def get_valid_categories(min_jobs: int = Query(10, ge=5)) -> List[str]:
    """获取有效的职类列表"""
    cache_key = f"city:valid-categories:{min_jobs}"
    cached = get_cache(cache_key)
    if cached is not None: 
        return cached

    try:
        with get_db_cursor() as cursor:
            cursor.execute(f"""
                SELECT job_category, COUNT(*) as cnt
                FROM jobs 
                WHERE {BASE_WHERE_SALARY} 
                  AND job_category IS NOT NULL 
                  AND job_category != ''
                GROUP BY job_category 
                HAVING cnt >= %s 
                ORDER BY cnt DESC
            """, (min_jobs,))
            
            categories = [
                r["job_category"] 
                for r in cursor.fetchall() 
                if is_valid_category(r["job_category"])
            ]
        
        set_cache(cache_key, categories, CACHE_TTL)
        return categories
        
    except Exception as e:
        print(f"Error in valid-categories: {e}")
        import traceback
        traceback.print_exc()
        return []