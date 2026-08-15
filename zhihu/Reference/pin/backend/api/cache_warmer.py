import os
import sys
import time
import logging
import requests
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# API 基础地址，可通过环境变量配置（Docker 部署时使用容器名）
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
# 缓存预热间隔（分钟）
WARM_INTERVAL_MINUTES = int(os.getenv("WARM_INTERVAL_MINUTES", 30))

# 需要预热的 API 端点列表
# 注意：所有路径必须与实际 API 路由一致，以 /api 开头
ENDPOINTS = [
    # ==================== 基础统计接口 ====================
    {"method": "GET", "path": "/api/stats"},           # 全局统计数据
    {"method": "GET", "path": "/api/home/"},           # 首页数据

    # ==================== 职位相关接口 ====================
    {"method": "GET", "path": "/api/jobs/"},           # 职位列表
    {"method": "GET", "path": "/api/jobs/cities"},     # 城市列表
    {"method": "GET", "path": "/api/jobs/categories"}, # 职位类别列表

    # ==================== 企业相关接口 ====================
    {"method": "GET", "path": "/api/companies/"},      # 企业列表
    {"method": "GET", "path": "/api/companies/hot"},   # 热门企业

    # ==================== 分析模块 - 概览统计 ====================
    {"method": "GET", "path": "/api/analysis/overview"},           # 概览统计
    {"method": "GET", "path": "/api/analysis/jobs-by-city"},      # 城市分布
    {"method": "GET", "path": "/api/analysis/jobs-by-education"}, # 学历分布
    {"method": "GET", "path": "/api/analysis/jobs-by-employment-type"}, # 工作类型分布
    {"method": "GET", "path": "/api/analysis/jobs-by-category"},  # 职位类别分布
    {"method": "GET", "path": "/api/analysis/jobs-trend"},        # 职位发布趋势
    {"method": "GET", "path": "/api/analysis/campus-vs-intern"},  # 校招 vs 实习
    {"method": "GET", "path": "/api/analysis/dashboard"},         # 仪表盘聚合数据
    {"method": "GET", "path": "/api/analysis/map-stats"},         # 地图统计数据

    # ==================== 分析模块 - 技能分析 ====================
    {"method": "GET", "path": "/api/analysis/skills/top-skills"},              # 热门技能
    {"method": "GET", "path": "/api/analysis/skills/category-skill-matrix"},   # 类别技能矩阵
    {"method": "GET", "path": "/api/analysis/skills/ai-trend"},                # AI 技能趋势
    {"method": "GET", "path": "/api/analysis/skills/category-top-skills"},     # 各类别热门技能
    {"method": "GET", "path": "/api/analysis/skills/skill-salary"},            # 技能薪资分析
    {"method": "GET", "path": "/api/analysis/skills/skill-combinations"},      # 技能组合分析
    {"method": "GET", "path": "/api/analysis/skills/skill-by-city"},           # 城市技能分布

    # ==================== 分析模块 - 薪资分析 ====================
    {"method": "GET", "path": "/api/analysis/salary/category-boxplot"},   # 类别薪资箱线图
    {"method": "GET", "path": "/api/analysis/salary/city-comparison"},    # 城市薪资对比
    {"method": "GET", "path": "/api/analysis/salary/education-premium"},  # 学历薪资溢价

    # ==================== 分析模块 - 城市分析 ====================
    {"method": "GET", "path": "/api/analysis/city/bubble-data"},          # 城市气泡图数据
    {"method": "GET", "path": "/api/analysis/city/category-heatmap"},     # 城市类别热力图
    {"method": "GET", "path": "/api/analysis/city/salary-comparison"},   # 城市薪资对比
    {"method": "GET", "path": "/api/analysis/city/campus-rank"},          # 校招城市排名
    {"method": "GET", "path": "/api/analysis/city/valid-categories"},    # 有效类别列表

    # ==================== 分析模块 - 聚类分析 ====================
    {"method": "GET", "path": "/api/analysis/clustering/clusters"},              # 聚类结果
    {"method": "GET", "path": "/api/analysis/clustering/category-distribution"}, # 聚类类别分布
    {"method": "GET", "path": "/api/analysis/clustering/quality-report"},       # 聚类质量报告
]


def warm_endpoint(endpoint: dict) -> bool:
    """
    预热单个 API 端点
    
    Args:
        endpoint: 包含 method 和 path 的字典
        
    Returns:
        bool: 预热是否成功
    """
    url = f"{BASE_URL}{endpoint['path']}"
    method = endpoint["method"]
    try:
        start = time.time()
        if method == "GET":
            resp = requests.get(url, timeout=30)
        else:
            resp = requests.post(url, timeout=30)
        elapsed = time.time() - start
        if resp.status_code == 200:
            logger.info(f"  ✅ {endpoint['path']} ({elapsed:.2f}s)")
            return True
        else:
            logger.warning(f"  ⚠️ {endpoint['path']} → HTTP {resp.status_code}")
            return False
    except Exception as e:
        logger.error(f"  ❌ {endpoint['path']} → {e}")
        return False


def warm_all():
    """
    预热所有配置的 API 端点
    
    遍历 ENDPOINTS 列表，依次请求每个接口，
    触发后端缓存机制，提升首次访问速度
    """
    logger.info("=" * 50)
    logger.info(f"🔥 缓存预热开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   共 {len(ENDPOINTS)} 个接口待预热")
    logger.info("=" * 50)

    success = 0
    fail = 0
    for i, ep in enumerate(ENDPOINTS, 1):
        logger.info(f"[{i}/{len(ENDPOINTS)}] 预热: {ep['path']}")
        if warm_endpoint(ep):
            success += 1
        else:
            fail += 1
        time.sleep(0.3)  # 请求间隔，避免压垮服务器

    logger.info("-" * 50)
    logger.info(
        f"🏁 预热完成: 成功 {success}/{len(ENDPOINTS)}, 失败 {fail}, 耗时统计见上方"
    )
    logger.info(f"⏰ 下次预热: {WARM_INTERVAL_MINUTES} 分钟后")
    return success, fail


def run_loop():
    """
    持续运行缓存预热服务
    
    先执行一次全量预热，然后按配置间隔循环执行
    """
    logger.info(
        f"🚀 缓存预热服务启动 | 目标: {BASE_URL} | 间隔: {WARM_INTERVAL_MINUTES} 分钟"
    )

    warm_all()

    while True:
        time.sleep(WARM_INTERVAL_MINUTES * 60)
        warm_all()


def warm_once():
    """执行单次缓存预热（用于手动触发或测试）"""
    warm_all()


if __name__ == "__main__":
    # 支持命令行参数：--once 表示只执行一次
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        warm_once()
    else:
        run_loop()
