from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any
import logging

from db import get_db_cursor
from cache import get_cache, set_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])

CACHE_TTL = 300


# ==================== 原有接口 ====================

@router.get("/overview")
async def get_overview() -> Dict[str, Any]:
    cached = get_cache("analysis:overview")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM jobs WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP) AS open_jobs,
                (SELECT COUNT(*) FROM jobs WHERE is_active = 1) AS total_jobs,
                (SELECT COUNT(*) FROM companies WHERE status = 1) AS companies,
                (SELECT COUNT(*) FROM jobs WHERE is_campus = 1 AND is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP) AS campus_jobs,
                (SELECT COUNT(*) FROM jobs WHERE is_intern = 1 AND is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP) AS intern_jobs
        """)
        stats = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(DISTINCT city) AS city_count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND city IS NOT NULL AND city != ''
        """)
        city_count = cursor.fetchone()["city_count"]

    result = {
        "open_jobs": stats["open_jobs"],
        "total_jobs": stats["total_jobs"],
        "companies": stats["companies"],
        "campus_jobs": stats["campus_jobs"],
        "intern_jobs": stats["intern_jobs"],
        "city_count": city_count,
    }
    set_cache("analysis:overview", result, CACHE_TTL)
    return result


@router.get("/jobs-by-city")
async def get_jobs_by_city(limit: int = Query(20, ge=1, le=100)) -> List[Dict[str, Any]]:
    cache_key = f"analysis:jobs-by-city:{limit}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT city, COUNT(*) AS count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND city IS NOT NULL AND city != ''
            GROUP BY city
            ORDER BY count DESC
            LIMIT %s
        """, (limit,))
        result = list(cursor.fetchall())

    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.get("/jobs-by-education")
async def get_jobs_by_education() -> List[Dict[str, Any]]:
    cached = get_cache("analysis:jobs-by-education")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT education_level AS name, COUNT(*) AS value
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND education_level IS NOT NULL AND education_level != ''
            GROUP BY education_level
            ORDER BY value DESC
        """)
        result = list(cursor.fetchall())

    set_cache("analysis:jobs-by-education", result, CACHE_TTL)
    return result


@router.get("/jobs-by-employment-type")
async def get_jobs_by_employment_type() -> List[Dict[str, Any]]:
    cached = get_cache("analysis:jobs-by-employment-type")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT employment_type AS name, COUNT(*) AS value
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND employment_type IS NOT NULL AND employment_type != ''
            GROUP BY employment_type
            ORDER BY value DESC
        """)
        result = list(cursor.fetchall())

    set_cache("analysis:jobs-by-employment-type", result, CACHE_TTL)
    return result


@router.get("/jobs-by-category")
async def get_jobs_by_category(limit: int = Query(15, ge=1, le=100)) -> List[Dict[str, Any]]:
    cache_key = f"analysis:jobs-by-category:{limit}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT job_category AS name, COUNT(*) AS value
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND job_category IS NOT NULL AND job_category != ''
            GROUP BY job_category
            ORDER BY value DESC
            LIMIT %s
        """, (limit,))
        result = list(cursor.fetchall())

    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.get("/jobs-trend")
async def get_jobs_trend(days: int = Query(30, ge=1, le=365)) -> List[Dict[str, Any]]:
    cache_key = f"analysis:jobs-trend:{days}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT DATE(published_at) AS date, COUNT(*) AS count
            FROM jobs
            WHERE is_active = 1
              AND status = 'open'
              AND published_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
              AND DATE(published_at) <= CURDATE() 
            GROUP BY DATE(published_at)
            ORDER BY date ASC
        """, (days,))
        result = list(cursor.fetchall())

    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.get("/campus-vs-intern")
async def get_campus_vs_intern() -> Dict[str, int]:
    cached = get_cache("analysis:campus-vs-intern")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                SUM(CASE WHEN is_campus = 1 THEN 1 ELSE 0 END) AS campus,
                SUM(CASE WHEN is_intern = 1 THEN 1 ELSE 0 END) AS intern,
                SUM(CASE WHEN is_campus = 0 AND is_intern = 0 THEN 1 ELSE 0 END) AS fulltime
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP
        """)
        row = cursor.fetchone()

    result = {
        "campus": int(row["campus"] or 0),
        "intern": int(row["intern"] or 0),
        "fulltime": int(row["fulltime"] or 0),
    }
    set_cache("analysis:campus-vs-intern", result, CACHE_TTL)
    return result


@router.get("/dashboard")
async def get_analysis_dashboard() -> Dict[str, Any]:
    cache_key = "analysis:dashboard:v2"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM jobs WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP) AS open_jobs,
                (SELECT COUNT(*) FROM jobs WHERE is_active = 1) AS total_jobs,
                (SELECT COUNT(*) FROM companies WHERE status = 1) AS companies,
                (SELECT COUNT(*) FROM jobs WHERE is_campus = 1 AND is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP) AS campus_jobs,
                (SELECT COUNT(*) FROM jobs WHERE is_intern = 1 AND is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP) AS intern_jobs
        """)
        stats = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(DISTINCT city) AS city_count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND city IS NOT NULL AND city != ''
        """)
        city_count = cursor.fetchone()["city_count"]

        overview = {
            "open_jobs": stats["open_jobs"],
            "total_jobs": stats["total_jobs"],
            "companies": stats["companies"],
            "campus_jobs": stats["campus_jobs"],
            "intern_jobs": stats["intern_jobs"],
            "city_count": city_count,
        }

        cursor.execute("""
            SELECT city, COUNT(*) AS count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND city IS NOT NULL AND city != ''
            GROUP BY city
            ORDER BY count DESC
            LIMIT 15
        """)
        jobs_by_city = list(cursor.fetchall())

        cursor.execute("""
            SELECT education_level AS name, COUNT(*) AS value
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND education_level IS NOT NULL AND education_level != ''
            GROUP BY education_level
            ORDER BY value DESC
        """)
        jobs_by_education = list(cursor.fetchall())

        cursor.execute("""
            SELECT employment_type AS name, COUNT(*) AS value
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND employment_type IS NOT NULL AND employment_type != ''
            GROUP BY employment_type
            ORDER BY value DESC
        """)
        jobs_by_employment_type = list(cursor.fetchall())

        cursor.execute("""
            SELECT job_category AS name, COUNT(*) AS value
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP AND job_category IS NOT NULL AND job_category != ''
            GROUP BY job_category
            ORDER BY value DESC
            LIMIT 12
        """)
        jobs_by_category = list(cursor.fetchall())

        cursor.execute("""
            SELECT
                SUM(CASE WHEN is_campus = 1 THEN 1 ELSE 0 END) AS campus,
                SUM(CASE WHEN is_intern = 1 THEN 1 ELSE 0 END) AS intern,
                SUM(CASE WHEN is_campus = 0 AND is_intern = 0 THEN 1 ELSE 0 END) AS fulltime
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND published_at <= CURRENT_TIMESTAMP
        """)
        row = cursor.fetchone()
        campus_vs_intern = {
            "campus": int(row["campus"] or 0),
            "intern": int(row["intern"] or 0),
            "fulltime": int(row["fulltime"] or 0),
        }

        cursor.execute("""
            SELECT DATE(published_at) AS date, COUNT(*) AS count
            FROM jobs
            WHERE is_active = 1
              AND status = 'open'
              AND published_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
              AND DATE(published_at) <= CURDATE() 
            GROUP BY DATE(published_at)
            ORDER BY date ASC
        """)
        jobs_trend = list(cursor.fetchall())

    result = {
        "overview": overview,
        "jobs_by_city": jobs_by_city,
        "jobs_by_education": jobs_by_education,
        "jobs_by_employment_type": jobs_by_employment_type,
        "jobs_by_category": jobs_by_category,
        "campus_vs_intern": campus_vs_intern,
        "jobs_trend": jobs_trend,
    }

    set_cache(cache_key, result, CACHE_TTL)
    return result


# ==================== 新增：地图相关接口 ====================

@router.get("/map-stats")
async def get_map_stats():
    """
    获取全国地图统计数据
    返回各省份/城市的岗位数量、企业数量
    """
    cache_key = "analysis:map-stats:v2"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            # 1. 按城市聚合统计
            cursor.execute("""
                SELECT 
                    city AS name,
                    COUNT(*) AS jobs_count,
                    COUNT(DISTINCT company_id) AS companies_count
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND city IS NOT NULL 
                  AND city != ''
                GROUP BY city
                ORDER BY jobs_count DESC
            """)
            city_stats_raw = cursor.fetchall()

            # 2. 按省份聚合统计（优先使用province字段）
            cursor.execute("""
                SELECT 
                    province AS name,
                    COUNT(*) AS jobs_count,
                    COUNT(DISTINCT company_id) AS companies_count
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND province IS NOT NULL 
                  AND province != ''
                GROUP BY province
                ORDER BY jobs_count DESC
            """)
            province_stats_raw = cursor.fetchall()

            # 3. 总体统计
            cursor.execute("""
                SELECT 
                    COUNT(*) AS total_jobs,
                    COUNT(DISTINCT company_id) AS total_companies
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
            """)
            total_stats_raw = cursor.fetchone()

        # 数据处理 - 城市统计
        city_stats = []
        for row in city_stats_raw:
            city_stats.append({
                'name': normalize_city_name(row['name']),
                'jobs_count': int(row['jobs_count']),
                'companies_count': int(row['companies_count'])
            })

        # 数据处理 - 省份统计（基础数据）
        province_dict = {}
        for row in province_stats_raw:
            prov_name = normalize_province_name(row['name'])
            if prov_name and prov_name not in province_dict:
                province_dict[prov_name] = {
                    'jobs_count': int(row['jobs_count']),
                    'companies_count': int(row['companies_count'])
                }
            elif prov_name:
                province_dict[prov_name]['jobs_count'] += int(row['jobs_count'])
                province_dict[prov_name]['companies_count'] += int(row['companies_count'])

        # 将城市数据聚合到省份（补充缺失的省份数据）
        city_to_province_map = get_city_to_province_mapping()
        for city_item in city_stats:
            city_name = city_item['name']
            prov_name = city_to_province_map.get(city_name)
            
            if prov_name and prov_name not in province_dict:
                province_dict[prov_name] = {'jobs_count': 0, 'companies_count': 0}
            
            if prov_name and prov_name in province_dict:
                province_dict[prov_name]['jobs_count'] += city_item['jobs_count']
                province_dict[prov_name]['companies_count'] += city_item['companies_count']

        # ====================== 强制修复：确保江西一定出现 ======================
        if "江西" not in province_dict:
            province_dict["江西"] = {"jobs_count": 0, "companies_count": 0}
        
        # 把南昌的数量强制加到江西
        for city in city_stats:
            if city["name"] in ["南昌", "南昌市", "Nanchang"]:
                province_dict["江西"]["jobs_count"] += city["jobs_count"]
                province_dict["江西"]["companies_count"] += city["companies_count"]
        # ======================================================================

        province_stats = [
            {'name': k, **v} for k, v in sorted(province_dict.items(), key=lambda x: x[1]['jobs_count'], reverse=True)
        ]

        result = {
            'city_stats': city_stats,
            'province_stats': province_stats,
            'total_stats': {
                'total_jobs': int(total_stats_raw['total_jobs']),
                'total_companies': int(total_stats_raw['total_companies'])
            }
        }

        set_cache(cache_key, result, CACHE_TTL)
        return result

    except Exception as e:
        logger.error(f"获取地图统计数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/city-detail/{city_name}")
async def get_city_detail(city_name: str):
    """
    获取指定城市的详细数据
    """
    cache_key = f"analysis:city-detail:{city_name}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    try:
        with get_db_cursor() as cursor:
            # 1. 城市基本统计
            cursor.execute("""
                SELECT COUNT(*) AS jobs_count
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND city = %s
            """, (city_name,))
            jobs_count = cursor.fetchone()['jobs_count']

            # 2. 薪资统计
            cursor.execute("""
                SELECT 
                    MIN((salary_min + salary_max) / 2) AS min_salary,
                    MAX((salary_min + salary_max) / 2) AS max_salary,
                    AVG((salary_min + salary_max) / 2) AS avg_salary
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND city = %s
                  AND salary_min IS NOT NULL 
                  AND salary_max IS NOT NULL
            """, (city_name,))
            salary_stats = cursor.fetchone()

            # 3. 学历分布
            cursor.execute("""
                SELECT 
                    COALESCE(education_level, '不限') AS level,
                    COUNT(*) AS count
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND city = %s
                GROUP BY education_level
                ORDER BY count DESC
            """, (city_name,))
            education_dist = cursor.fetchall()

            # 4. 职位类别分布
            cursor.execute("""
                SELECT 
                    job_category AS category,
                    COUNT(*) AS count
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND city = %s
                  AND job_category IS NOT NULL
                GROUP BY job_category
                ORDER BY count DESC
                LIMIT 10
            """, (city_name,))
            category_dist = cursor.fetchall()

            # 5. 热招企业
            cursor.execute("""
                SELECT 
                    c.name,
                    COUNT(j.id) AS jobs_count
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE j.is_active = 1 
                  AND j.status = 'open'
                  AND j.published_at <= CURRENT_TIMESTAMP
                  AND j.city = %s
                GROUP BY c.id, c.name
                ORDER BY jobs_count DESC
                LIMIT 10
            """, (city_name,))
            top_companies = cursor.fetchall()

        result = {
            'city_name': city_name,
            'jobs_count': int(jobs_count),
            'salary_stats': {
                'min': round(float(salary_stats['min_salary']) if salary_stats['min_salary'] else 0, 2),
                'max': round(float(salary_stats['max_salary']) if salary_stats['max_salary'] else 0, 2),
                'avg': round(float(salary_stats['avg_salary']) if salary_stats['avg_salary'] else 0, 2)
            },
            'education_distribution': [
                {'level': row['level'], 'count': int(row['count'])}
                for row in education_dist
            ],
            'category_distribution': [
                {'category': row['category'], 'count': int(row['count'])}
                for row in category_dist
            ],
            'top_companies': [
                {'name': row['name'], 'jobs_count': int(row['jobs_count'])}
                for row in top_companies
            ]
        }

        set_cache(cache_key, result, CACHE_TTL)
        return result

    except Exception as e:
        logger.error(f"获取城市详情失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 辅助函数 ====================

def get_city_to_province_mapping() -> dict:
    """城市到省份的映射表"""
    return {
        # 直辖市
        '北京': '北京', '上海': '上海', '天津': '天津', '重庆': '重庆',
        # 河北省
        '石家庄': '河北', '唐山': '河北', '秦皇岛': '河北', '邯郸': '河北',
        '邢台': '河北', '保定': '河北', '张家口': '河北', '承德': '河北',
        '沧州': '河北', '廊坊': '河北', '衡水': '河北',
        # 山西省
        '太原': '山西', '大同': '山西', '阳泉': '山西', '长治': '山西',
        '晋城': '山西', '朔州': '山西', '晋中': '山西', '运城': '山西',
        '忻州': '山西', '临汾': '山西', '吕梁': '山西',
        # 辽宁省
        '沈阳': '辽宁', '大连': '辽宁', '鞍山': '辽宁', '抚顺': '辽宁',
        '本溪': '辽宁', '丹东': '辽宁', '锦州': '辽宁', '营口': '辽宁',
        '阜新': '辽宁', '辽阳': '辽宁', '盘锦': '辽宁', '铁岭': '辽宁',
        '朝阳': '辽宁', '葫芦岛': '辽宁',
        # 吉林省
        '长春': '吉林', '吉林': '吉林', '四平': '吉林', '辽源': '吉林',
        '通化': '吉林', '白山': '吉林', '松原': '吉林', '白城': '吉林',
        '延边': '吉林',
        # 黑龙江省
        '哈尔滨': '黑龙江', '齐齐哈尔': '黑龙江', '鸡西': '黑龙江',
        '鹤岗': '黑龙江', '双鸭山': '黑龙江', '大庆': '黑龙江',
        '伊春': '黑龙江', '佳木斯': '黑龙江', '七台河': '黑龙江',
        '牡丹江': '黑龙江', '黑河': '黑龙江', '绥化': '黑龙江',
        '大兴安岭': '黑龙江',
        # 江苏省
        '南京': '江苏', '无锡': '江苏', '徐州': '江苏', '常州': '江苏',
        '苏州': '江苏', '南通': '江苏', '连云港': '江苏', '淮安': '江苏',
        '盐城': '江苏', '扬州': '江苏', '镇江': '江苏', '泰州': '江苏',
        '宿迁': '江苏',
        # 浙江省
        '杭州': '浙江', '宁波': '浙江', '温州': '浙江', '嘉兴': '浙江',
        '湖州': '浙江', '绍兴': '浙江', '金华': '浙江', '衢州': '浙江',
        '舟山': '浙江', '台州': '浙江', '丽水': '浙江',
        # 安徽省
        '合肥': '安徽', '芜湖': '安徽', '蚌埠': '安徽', '淮南': '安徽',
        '马鞍山': '安徽', '淮北': '安徽', '铜陵': '安徽', '安庆': '安徽',
        '黄山': '安徽', '滁州': '安徽', '阜阳': '安徽', '宿州': '安徽',
        '六安': '安徽', '亳州': '安徽', '池州': '安徽', '宣城': '安徽',
        # 福建省
        '福州': '福建', '厦门': '福建', '莆田': '福建', '三明': '福建',
        '泉州': '福建', '漳州': '福建', '南平': '福建', '龙岩': '福建',
        '宁德': '福建',
        # 江西省
        '南昌': '江西', '南昌市':'江西',
        '景德镇': '江西', '萍乡': '江西', '九江': '江西',
        '新余': '江西', '鹰潭': '江西', '赣州': '江西', '吉安': '江西',
        '宜春': '江西', '抚州': '江西', '上饶': '江西',
        # 山东省
        '济南': '山东', '青岛': '山东', '淄博': '山东', '枣庄': '山东',
        '东营': '山东', '烟台': '山东', '潍坊': '山东', '济宁': '山东',
        '泰安': '山东', '威海': '山东', '日照': '山东', '临沂': '山东',
        '德州': '山东', '聊城': '山东', '滨州': '山东', '菏泽': '山东',
        # 河南省
        '郑州': '河南', '开封': '河南', '洛阳': '河南', '平顶山': '河南',
        '安阳': '河南', '鹤壁': '河南', '新乡': '河南', '焦作': '河南',
        '濮阳': '河南', '许昌': '河南', '漯河': '河南', '三门峡': '河南',
        '南阳': '河南', '商丘': '河南', '信阳': '河南', '周口': '河南',
        '驻马店': '河南', '济源': '河南',
        # 湖北省
        '武汉': '湖北', '黄石': '湖北', '十堰': '湖北', '宜昌': '湖北',
        '襄阳': '湖北', '鄂州': '湖北', '荆门': '湖北', '孝感': '湖北',
        '荆州': '湖北', '黄冈': '湖北', '咸宁': '湖北', '随州': '湖北',
        '恩施': '湖北', '仙桃': '湖北', '潜江': '湖北', '天门': '湖北',
        '神农架': '湖北',
        # 湖南省
        '长沙': '湖南', '株洲': '湖南', '湘潭': '湖南', '衡阳': '湖南',
        '邵阳': '湖南', '岳阳': '湖南', '常德': '湖南', '张家界': '湖南',
        '益阳': '湖南', '郴州': '湖南', '永州': '湖南', '怀化': '湖南',
        '娄底': '湖南', '湘西': '湖南',
        # 广东省
        '广州': '广东', '韶关': '广东', '深圳': '广东', '珠海': '广东',
        '汕头': '广东', '佛山': '广东', '江门': '广东', '湛江': '广东',
        '茂名': '广东', '肇庆': '广东', '惠州': '广东', '梅州': '广东',
        '汕尾': '广东', '河源': '广东', '阳江': '广东', '清远': '广东',
        '东莞': '广东', '中山': '广东', '潮州': '广东', '揭阳': '广东',
        '云浮': '广东',
        # 海南省
        '海口': '海南', '三亚': '海南', '三沙': '海南', '儋州': '海南',
        # 四川省
        '成都': '四川', '自贡': '四川', '攀枝花': '四川', '泸州': '四川',
        '德阳': '四川', '绵阳': '四川', '广元': '四川', '遂宁': '四川',
        '内江': '四川', '乐山': '四川', '南充': '四川', '眉山': '四川',
        '宜宾': '四川', '广安': '四川', '达州': '四川', '雅安': '四川',
        '巴中': '四川', '资阳': '四川', '阿坝': '四川', '甘孜': '四川',
        '凉山': '四川',
        # 贵州省
        '贵阳': '贵州', '六盘水': '贵州', '遵义': '贵州', '安顺': '贵州',
        '毕节': '贵州', '铜仁': '贵州', '黔西南': '贵州', '黔东南': '贵州',
        '黔南': '贵州',
        # 云南省
        '昆明': '云南', '曲靖': '云南', '玉溪': '云南', '保山': '云南',
        '昭通': '云南', '丽江': '云南', '普洱': '云南', '临沧': '云南',
        '楚雄': '云南', '红河': '云南', '文山': '云南', '西双版纳': '云南',
        '大理': '云南', '德宏': '云南', '怒江': '云南', '迪庆': '云南',
        # 陕西省
        '西安': '陕西', '铜川': '陕西', '宝鸡': '陕西', '咸阳': '陕西',
        '渭南': '陕西', '延安': '陕西', '汉中': '陕西', '榆林': '陕西',
        '安康': '陕西', '商洛': '陕西',
        # 甘肃省
        '兰州': '甘肃', '嘉峪关': '甘肃', '金昌': '甘肃', '白银': '甘肃',
        '天水': '甘肃', '武威': '甘肃', '张掖': '甘肃', '平凉': '甘肃',
        '酒泉': '甘肃', '庆阳': '甘肃', '定西': '甘肃', '陇南': '甘肃',
        '临夏': '甘肃', '甘南': '甘肃',
        # 青海省
        '西宁': '青海', '海东': '青海', '海北': '青海', '黄南': '青海',
        '海南藏': '青海', '果洛': '青海', '玉树': '青海', '海西': '青海',
        # 内蒙古自治区
        '呼和浩特': '内蒙古', '包头': '内蒙古', '乌海': '内蒙古',
        '赤峰': '内蒙古', '通辽': '内蒙古', '鄂尔多斯': '内蒙古',
        '呼伦贝尔': '内蒙古', '巴彦淖尔': '内蒙古', '乌兰察布': '内蒙古',
        '兴安': '内蒙古', '锡林郭勒': '内蒙古', '阿拉善': '内蒙古',
        # 广西壮族自治区
        '南宁': '广西', '柳州': '广西', '桂林': '广西', '梧州': '广西',
        '北海': '广西', '防城港': '广西', '钦州': '广西', '贵港': '广西',
        '玉林': '广西', '百色': '广西', '贺州': '广西', '河池': '广西',
        '来宾': '广西', '崇左': '广西',
        # 西藏自治区
        '拉萨': '西藏', '日喀则': '西藏', '昌都': '西藏', '林芝': '西藏',
        '山南': '西藏', '那曲': '西藏', '阿里': '西藏',
        # 宁夏回族自治区
        '银川': '宁夏', '石嘴山': '宁夏', '吴忠': '宁夏', '固原': '宁夏',
        '中卫': '宁夏',
        # 新疆维吾尔自治区
        '乌鲁木齐': '新疆', '克拉玛依': '新疆', '吐鲁番': '新疆',
        '哈密': '新疆', '昌吉': '新疆', '博尔塔拉': '新疆',
        '巴音郭楞': '新疆', '阿克苏': '新疆', '克孜勒苏': '新疆',
        '喀什': '新疆', '和田': '新疆', '伊犁': '新疆', '塔城': '新疆',
        '阿勒泰': '新疆', '石河子': '新疆', '阿拉尔': '新疆',
        '图木舒克': '新疆', '五家渠': '新疆', '北屯': '新疆',
        '铁门关': '新疆', '双河': '新疆', '可克达拉': '新疆',
        '昆玉': '新疆', '胡杨河': '新疆',
        # 香港特别行政区、澳门特别行政区
        '香港': '香港', '澳门': '澳门',
        # 台湾省（暂列主要城市）
        '台北': '台湾', '高雄': '台湾', '台中': '台湾', '台南': '台湾',
    }


def normalize_city_name(city: str) -> str:
    """标准化城市名称"""
    if not city:
        return city
    
    # 去除后缀
    city = city.strip()
    for suffix in ['市', '自治区', '特别行政区', '省']:
        city = city.replace(suffix, '')
    
    # 强制匹配南昌
    if '南昌' in city:
        return '南昌'
    
    # 特殊映射
    city_map = {
        '北京': '北京',
        '上海': '上海',
        '天津': '天津',
        '重庆': '重庆',
    }
    
    return city_map.get(city, city)


def normalize_province_name(province: str) -> str:
    """标准化省份名称"""
    if not province:
        return province
    
    province = province.strip()
    for suffix in ['省', '自治区', '特别行政区', '维吾尔', '回族', '壮族']:
        province = province.replace(suffix, '')
    
    # 特殊映射
    province_map = {
        '内蒙古': '内蒙古',
        '新疆': '新疆',
        '西藏': '西藏',
        '宁夏': '宁夏',
        '广西': '广西',
        '香港': '香港',
        '澳门': '澳门',
    }
    
    return province_map.get(province, province)