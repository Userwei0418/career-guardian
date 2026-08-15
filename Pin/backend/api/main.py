import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
import psutil
from fastapi.middleware.cors import CORSMiddleware
import os
import threading
import logging
import sys
from pathlib import Path
import httpx
from collections import deque
import time
from datetime import datetime
api_dir = Path(__file__).parent
sys.path.insert(0, str(api_dir))
from ws_manager import manager

# 添加项目根目录到Python路径

from routers import jobs, companies, analysis, home
from routers import skills, salary, city, clustering, match, company_lists
from routers import company_sources
from cache import get_cache, set_cache
from db import get_db_cursor

logger = logging.getLogger(__name__)

# 服务配置
CRAWLER_SERVICE_URL = os.getenv("CRAWLER_SERVICE_URL", "http://localhost:8001")

# 监控历史数据（内存环形缓冲区，保留最近360条 = 1小时 @ 10s间隔）
_metrics_history = deque(maxlen=360)
_metrics_history_lock = threading.Lock()
_start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    t = threading.Thread(target=_run_cache_warmer, daemon=True)
    t.start()
    logger.info("[缓存预热] 后台线程已启动，每30分钟自动预热")
    yield
    # Shutdown
    await http_client.aclose()

app = FastAPI(
    title="Pin - 招聘数据聚合平台",
    description="统一API服务，提供数据分析、爬虫管理和系统监控",
    version="3.0.0",
    lifespan=lifespan
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP客户端
http_client = httpx.AsyncClient(timeout=30.0)

# 路由注册 - 原有功能
app.include_router(home.router)
app.include_router(jobs.router)
app.include_router(companies.router)
app.include_router(analysis.router)
app.include_router(skills.router)
app.include_router(salary.router)
app.include_router(city.router)
app.include_router(clustering.router)
app.include_router(match.router)
app.include_router(company_lists.router)
app.include_router(company_sources.router)

# ==========================================
# 爬虫管理API - 代理到爬虫服务
# ==========================================

@app.get("/api/crawler/status", tags=["爬虫管理"])
async def get_crawler_status():
    """获取爬虫运行状态"""
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/status")
        return response.json()
    except Exception as e:
        logger.error(f"获取爬虫状态失败: {e}")
        return {
            "status": "disconnected",
            "active_tasks": 0,
            "completed_tasks": 0,
            "last_run": None,
            "error": str(e)
        }

@app.get("/api/crawler/tasks", tags=["爬虫管理"])
async def get_crawler_tasks():
    """获取爬虫任务列表"""
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/tasks")
        return response.json()
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        return {"tasks": [], "error": str(e)}

@app.get("/api/crawler/tasks/{task_id}", tags=["爬虫管理"])
async def get_crawler_task(task_id: str):
    """获取单个任务详情"""
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/tasks/{task_id}")
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="任务不存在")
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crawler/tasks/{task_id}/logs", tags=["爬虫管理"])
async def get_crawler_task_logs(task_id: str, limit: int = 100):
    """获取任务日志"""
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/tasks/{task_id}/logs", params={"limit": limit})
        return response.json()
    except Exception as e:
        return {"logs": [], "error": str(e)}

class StartTaskRequest:
    task_type: str = "company"  # company/full/process
    config_file: str = "99"

@app.post("/api/crawler/start", tags=["爬虫管理"])
async def start_crawler(task_type: str = "company", company_ids: str = ""):
    """启动爬虫任务"""
    try:
        response = await http_client.post(
            f"{CRAWLER_SERVICE_URL}/start",
            json={"task_type": task_type, "company_ids": company_ids},
            timeout=15.0
        )
        return response.json()
    except Exception as e:
        logger.error(f"启动爬虫失败: {e}")
        err_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
        raise HTTPException(status_code=500, detail=f"启动爬虫失败: {err_msg}")

@app.post("/api/crawler/stop/{task_id}", tags=["爬虫管理"])
async def stop_crawler(task_id: str):
    """停止爬虫任务"""
    try:
        response = await http_client.post(f"{CRAWLER_SERVICE_URL}/stop/{task_id}")
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="任务不存在")
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/crawler/tasks/{task_id}", tags=["爬虫管理"])
async def delete_crawler_task(task_id: str):
    """删除任务记录"""
    try:
        response = await http_client.delete(f"{CRAWLER_SERVICE_URL}/tasks/{task_id}")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crawler/config", tags=["爬虫管理"])
async def get_crawler_config():
    """获取爬虫配置"""
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/config")
        return response.json()
    except Exception as e:
        return {"configs": [], "error": str(e)}

@app.get("/api/crawler/browser", tags=["爬虫管理"])
async def get_browser_status():
    """获取浏览器状态"""
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/browser/status")
        return response.json()
    except Exception as e:
        return {"playwright_running": False, "error": str(e)}

@app.get("/api/crawler/metrics", tags=["爬虫管理"])
async def get_crawler_metrics():
    """获取爬虫系统指标"""
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/metrics")
        return response.json()
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 系统监控API - 本地采集 (psutil) + 历史存储 + 爬虫健康
# ============================================================

def _get_local_metrics():
    """采集本地系统指标"""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    cpu_percent = psutil.cpu_percent(interval=0.1)
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu_percent": cpu_percent,
        "memory_percent": mem.percent,
        "memory_used_mb": round(mem.used / 1024 / 1024, 1),
        "memory_total_mb": round(mem.total / 1024 / 1024, 1),
        "memory_available_mb": round(mem.available / 1024 / 1024, 1),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 1),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
        "net_sent_mb": round(net.bytes_sent / 1024 / 1024, 1),
        "net_recv_mb": round(net.bytes_recv / 1024 / 1024, 1),
    }

def _get_crawler_processes():
    """获取爬虫进程信息"""
    processes = []
    total_cpu = 0.0
    total_mem = 0.0
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_percent"]):
        try:
            cmdline = proc.info.get("cmdline", [])
            cmd_str = " ".join(cmdline) if cmdline else ""
            if "main.py" in cmd_str and any(x in cmd_str for x in ["-m", "--method"]):
                cpu = proc.info.get("cpu_percent", 0) or 0
                mem = proc.info.get("memory_percent", 0) or 0
                total_cpu += cpu
                total_mem += mem
                processes.append({
                    "pid": proc.info["pid"],
                    "name": proc.info.get("name", ""),
                    "cmdline": cmd_str[:200],
                    "cpu_percent": round(cpu, 1),
                    "memory_percent": round(mem, 1),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return processes, round(total_cpu, 1), round(total_mem, 1)

def _collect_metrics_loop():
    """后台采集线程"""
    while True:
        try:
            metrics = _get_local_metrics()
            with _metrics_history_lock:
                _metrics_history.append(metrics)
        except Exception as e:
            logger.error(f"metric collect failed: {e}")
        time.sleep(10)

@app.get("/api/monitor/dashboard", tags=["monitor"])
async def get_monitor_dashboard():
    metrics = _get_local_metrics()
    processes, crawler_cpu, crawler_mem = _get_crawler_processes()
    uptime = int(time.time() - _start_time)
    with _metrics_history_lock:
        history_count = len(_metrics_history)
    return {
        "current": {
            "system": metrics,
            "crawler": {
                "process_count": len(processes),
                "cpu_percent": crawler_cpu,
                "memory_percent": crawler_mem,
            },
        },
        "history_count": history_count,
        "history_capacity": _metrics_history.maxlen,
        "uptime_seconds": uptime,
    }

@app.get("/api/monitor/metrics/current", tags=["monitor"])
async def get_current_metrics():
    return _get_local_metrics()

@app.get("/api/monitor/metrics/history")
async def get_metrics_history(minutes: int = 60):
    with _metrics_history_lock:
        history = list(_metrics_history)
    if minutes > 0 and history:
        cutoff_ts = datetime.now().timestamp() - minutes * 60
        history = [h for h in history if datetime.strptime(h["timestamp"], "%Y-%m-%d %H:%M:%S").timestamp() > cutoff_ts]
    return {"metrics": history, "count": len(history)}

@app.get("/api/monitor/logs")
async def get_monitor_logs(level: str = "all", limit: int = 100):
    logs = _read_monitor_logs(level=level, limit=limit)
    return {"logs": logs, "count": len(logs)}

@app.get("/api/monitor/alerts")
async def get_monitor_alerts(limit: int = 50):
    metrics = _get_local_metrics()
    alerts = []
    aid = 0
    if metrics["cpu_percent"] > 80:
        aid += 1
        alerts.append({"id": f"a{aid}", "type": "warning", "message": f"CPU high: {metrics['cpu_percent']}%", "timestamp": metrics["timestamp"], "value": metrics["cpu_percent"], "threshold": 80})
    if metrics["memory_percent"] > 85:
        aid += 1
        alerts.append({"id": f"a{aid}", "type": "warning", "message": f"Memory high: {metrics['memory_percent']}%", "timestamp": metrics["timestamp"], "value": metrics["memory_percent"], "threshold": 85})
    if metrics["disk_percent"] > 90:
        aid += 1
        alerts.append({"id": f"a{aid}", "type": "error", "message": f"Disk low: {metrics['disk_percent']}%", "timestamp": metrics["timestamp"], "value": metrics["disk_percent"], "threshold": 90})
    return {"alerts": alerts[:limit]}

@app.delete("/api/monitor/alerts")
async def clear_monitor_alerts():
    return {"message": "ok"}

@app.get("/api/monitor/processes")
async def get_monitor_processes():
    processes, _, _ = _get_crawler_processes()
    return {"processes": processes}

@app.get("/api/monitor/health")
async def monitor_health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/monitor/crawler-health")
async def get_crawler_health():
    return _get_crawler_health()

def _read_monitor_logs(level="all", limit=100):
    logs = []
    monitor_log_dir = Path(__file__).resolve().parent.parent / "crawler" / "data" / "monitor" / "logs"
    if not monitor_log_dir.exists():
        return logs
    today_str = datetime.now().strftime("%Y%m%d")
    log_file = monitor_log_dir / f"{today_str}.json"
    if not log_file.exists():
        return logs
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, company in data.get("companies", {}).items():
            c_name = company.get("company_name", key)
            for detail in company.get("crawl", {}).get("details", [])[-10:]:
                status = detail.get("status", "")
                msg = f"[{c_name}] crawl {detail.get('type', '')} {status}"
                if detail.get("error"):
                    msg += f" | {detail['error'][:60]}"
                logs.append({"timestamp": detail.get("time", ""), "level": "ERROR" if status == "failed" else "INFO", "message": msg, "source": "crawler"})
            for detail in company.get("clean", {}).get("details", [])[-10:]:
                status = detail.get("status", "")
                msg = f"[{c_name}] clean {status}"
                if detail.get("error"):
                    msg += f" | {detail['error'][:60]}"
                logs.append({"timestamp": detail.get("time", ""), "level": "ERROR" if status == "failed" else "INFO", "message": msg, "source": "cleaner"})
    except Exception as e:
        logger.warning(f"read monitor logs failed: {e}")
    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    if level != "all":
        logs = [l for l in logs if l["level"] == level]
    return logs[:limit]

def _get_crawler_health():
    monitor_log_dir = Path(__file__).resolve().parent.parent / "crawler" / "data" / "monitor" / "logs"
    today_str = datetime.now().strftime("%Y%m%d")
    log_file = monitor_log_dir / f"{today_str}.json"
    if not log_file.exists():
        return {"has_data": False, "message": "no crawler activity today"}
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        summary = data.get("summary", {})
        performance = data.get("performance", {})
        companies = data.get("companies", {})
        total_crawled = summary.get("total_crawled", 0)
        crawl_errors = summary.get("errors", {}).get("crawl_errors", 0)
        total_cleaned = summary.get("total_cleaned", 0)
        clean_errors = summary.get("errors", {}).get("clean_errors", 0)
        return {
            "has_data": True,
            "date": data.get("date"),
            "start_time": data.get("start_time"),
            "companies_total": len(companies),
            "companies_active": summary.get("active_companies", 0),
            "crawl_total": total_crawled,
            "crawl_success": total_crawled - crawl_errors,
            "crawl_failed": crawl_errors,
            "crawl_success_rate": round((total_crawled - crawl_errors) / total_crawled * 100, 1) if total_crawled > 0 else 0,
            "clean_total": total_cleaned,
            "clean_success": total_cleaned - clean_errors,
            "clean_failed": clean_errors,
            "pending_clean": summary.get("pending_clean", 0),
            "avg_crawl_time": performance.get("avg_crawl_time", 0),
            "avg_clean_time": performance.get("avg_clean_time", 0),
        }
    except Exception as e:
        return {"has_data": False, "message": str(e)}

# ==========================================
# 数据接入API
# ==========================================

@app.post("/api/ingest/jobs", tags=["数据接入"])
async def ingest_jobs(data: dict):
    """接收爬虫数据"""
    # TODO: 实现数据写入数据库
    return {
        "status": "accepted",
        "count": len(data.get("jobs", [])),
        "message": "数据已接收并处理"
    }

@app.post("/api/ingest/companies", tags=["数据接入"])
async def ingest_companies(data: dict):
    """接收公司数据"""
    return {
        "status": "accepted",
        "count": len(data.get("companies", [])),
        "message": "数据已接收并处理"
    }

# ==========================================
# 原有功能
# ==========================================

@app.get("/")
async def root():
    return {
        "message": "Pin - 招聘数据聚合平台",
        "version": "3.0.0",
        "description": "统一API服务，提供数据分析、爬虫管理和系统监控",
        "services": {
            "backend": "http://localhost:8000",
            "crawler": CRAWLER_SERVICE_URL,
        },
        "endpoints": {
            "docs": "/docs",
            "jobs": "/api/jobs",
            "companies": "/api/companies",
            "analysis": "/api/analysis",
            "crawler": "/api/crawler/status",
            "monitor": "/api/monitor/dashboard"
        }
    }

@app.get("/api/stats")
async def get_stats():
    """全局统计数据"""
    cached = get_cache("stats:v2")
    if cached is not None:
        return cached

    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as count FROM jobs WHERE is_active = 1 AND status = 'open'")
        job_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM companies WHERE status = 1")
        company_count = cursor.fetchone()["count"]

        cursor.execute("""
            SELECT COUNT(DISTINCT city) as count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND city IS NOT NULL AND city != ''
        """)
        city_count = cursor.fetchone()["count"]

        cursor.execute("""
            SELECT COUNT(DISTINCT province) as count
            FROM jobs
            WHERE is_active = 1 AND status = 'open' AND province IS NOT NULL AND province != ''
        """)
        province_count = cursor.fetchone()["count"]

    result = {
        "job_count": job_count,
        "company_count": company_count,
        "city_count": city_count,
        "province_count": province_count,
        "last_updated": "实时"
    }
    set_cache("stats:v2", result, 300)
    return result

@app.get("/health")
async def health_check():
    """健康检查"""
    # 检查各服务状态
    services_status = {}
    
    try:
        response = await http_client.get(f"{CRAWLER_SERVICE_URL}/", timeout=2.0)
        services_status["crawler"] = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        services_status["crawler"] = "disconnected"
    
    
    return {
        "status": "healthy",
        "version": "3.0.0",
        "services": services_status
    }

def _run_cache_warmer():
    import time
    import requests as req

    BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
    INTERVAL = int(os.getenv("WARM_INTERVAL_MINUTES", 30)) * 60

    ENDPOINTS = [
        "/api/stats", "/api/home/",
        "/api/analysis/overview", "/api/analysis/jobs-by-city",
        "/api/analysis/jobs-by-education", "/api/analysis/jobs-by-employment-type",
        "/api/analysis/jobs-by-category", "/api/analysis/jobs-trend",
        "/api/analysis/campus-vs-intern", "/api/analysis/dashboard",
        "/api/analysis/map-stats",
        "/api/analysis/skills/top-skills", "/api/analysis/skills/category-skill-matrix",
        "/api/analysis/skills/ai-trend", "/api/analysis/skills/skill-by-city",
        "/api/analysis/salary/category-boxplot", "/api/analysis/salary/education-premium",
        "/api/analysis/city/bubble-data", "/api/analysis/city/category-heatmap",
        "/api/analysis/city/campus-rank",
        "/api/analysis/city/valid-categories",
    ]

    def warm():
        logger.info(f"[缓存预热] 开始预热 {len(ENDPOINTS)} 个接口 ...")
        ok = fail = 0
        for ep in ENDPOINTS:
            try:
                r = req.get(f"{BASE_URL}{ep}", timeout=30)
                if r.status_code == 200:
                    ok += 1
                else:
                    fail += 1
                    logger.warning(f"[缓存预热] {ep} → HTTP {r.status_code}")
            except Exception as e:
                fail += 1
                logger.error(f"[缓存预热] {ep} → {e}")
            time.sleep(0.3)
        logger.info(f"[缓存预热] 完成 成功={ok} 失败={fail}")

    warm()
    while True:
        time.sleep(INTERVAL)
        warm()



# ==========================================
# 数据入库 API
# ==========================================

@app.post("/api/ingest/trigger", tags=["数据管理"])
async def trigger_ingest(payload: dict = None):
    """触发数据入库。可选传入 {"com_ids": [...]} 或 {"crawl_job_ids": [...]} 指定范围"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from ingest_cjob import run_ingest
        p = payload or {}
        result = run_ingest(
            crawl_job_ids=p.get("crawl_job_ids"),
            com_ids=p.get("com_ids"),
        )
        result["message"] = f"入库完成: {result.get('ingested', 0)}条新增, {result.get('skipped_dup', 0)}条重复, {result.get('failed', 0)}条失败"
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")


@app.get("/api/ingest/stats", tags=["数据管理"])
async def get_ingest_stats():
    """获取数据统计"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM jobs WHERE is_active = 1")
            jobs_count = cursor.fetchone()["total"]
            cursor.execute("SELECT COUNT(*) as total FROM companies WHERE status = 1")
            companies_count = cursor.fetchone()["total"]
            cursor.execute("""
                SELECT source_site, COUNT(*) as cnt 
                FROM jobs WHERE is_active = 1 
                GROUP BY source_site 
                ORDER BY cnt DESC 
                LIMIT 10
            """)
            sources = cursor.fetchall()
        return {
            "jobs_count": jobs_count,
            "companies_count": companies_count,
            "top_sources": [
                {"source": s["source_site"], "count": s["cnt"]} for s in sources
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


# ==========================================
# WebSocket 实时推送
# ==========================================

@app.websocket("/ws/crawl-status")
async def websocket_endpoint(websocket: WebSocket):
    """实时推送爬虫任务状态"""
    await manager.connect(websocket)
    try:
        while True:
            # 接收客户端消息（可以是订阅/取消订阅）
            data = await websocket.receive_text()
            msg = json.loads(data) if data else {}

            action = msg.get("action", "")
            if action == "subscribe":
                await websocket.send_json({"type": "subscribed", "message": "已订阅爬虫状态"})
            elif action == "get_tasks":
                # 返回当前任务状态
                async with httpx.AsyncClient(timeout=15.0) as client:
                    try:
                        resp = await client.get(f"{CRAWLER_SERVICE_URL}/tasks")
                        tasks_data = resp.json()
                        await websocket.send_json({"type": "tasks_update", "data": tasks_data})
                    except:
                        await websocket.send_json({"type": "error", "message": "无法连接爬虫服务"})
            elif action == "get_metrics":
                async with httpx.AsyncClient(timeout=15.0) as client:
                    try:
                        resp = await client.get(f"{CRAWLER_SERVICE_URL}/metrics")
                        metrics_data = resp.json()
                        await websocket.send_json({"type": "metrics_update", "data": metrics_data})
                    except:
                        await websocket.send_json({"type": "error", "message": "无法连接爬虫服务"})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


def broadcast_task_update(task_data: dict):
    """广播任务状态变化"""
    asyncio.create_task(manager.broadcast({"type": "task_update", "data": task_data}))



# ============================================================
# 解析与入库 API
# ============================================================

CRAWLER_DATA_DIR = Path(__file__).resolve().parent.parent / "crawler" / "data"

@app.get("/api/process/pending-files", tags=["数据管理"])
async def get_pending_files():
    """获取待 LLM 解析的文件列表"""
    tmp_dir = CRAWLER_DATA_DIR / "tmp"
    ardata_dir = CRAWLER_DATA_DIR / "ardata"

    pending = []
    if tmp_dir.exists() and ardata_dir.exists():
        for key_dir in tmp_dir.iterdir():
            if not key_dir.is_dir():
                continue
            ar_key_dir = ardata_dir / key_dir.name
            for f in key_dir.iterdir():
                if f.name.startswith("detail_") and f.suffix == ".json" and ".model." not in f.name:
                    model_file = ar_key_dir / f.name.replace(".json", ".model.json") if ar_key_dir.exists() else None
                    if not model_file or not model_file.exists():
                        pending.append({"key": key_dir.name, "file": f.name, "path": str(f)})

    return {"total": len(pending), "files": pending[:50]}
# 文件浏览 API（文件系统版）
# ============================================================

@app.get("/api/files/browse")
async def browse_files_db(com_id: str = "", file_type: str = "html"):
    """浏览公司数据（从数据库查询）"""
    if not com_id:
        raise HTTPException(status_code=400, detail="缺少 com_id")

    if file_type == "html":
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, crawl_job_id, job_title, job_type, raw_html IS NOT NULL as has_data
                FROM crawl_jobs
                WHERE com_id = %s AND raw_html IS NOT NULL
                ORDER BY crawled_at DESC
                LIMIT 100
            """, (com_id,))
            files = []
            for r in cursor.fetchall():
                files.append({
                    "id": r["id"],
                    "crawl_job_id": r["crawl_job_id"],
                    "name": r["job_title"] or r["crawl_job_id"][:16],
                    "type": r["job_type"] or "",
                    "has_data": r["has_data"],
                })
        return {"com_id": com_id, "files": files, "total": len(files)}
    else:  # parsed data (model_json)
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT id, crawl_job_id, job_title, model_json IS NOT NULL as has_model
                FROM crawl_jobs
                WHERE com_id = %s AND model_json IS NOT NULL AND status = 'parsed'
                ORDER BY parsed_at DESC
                LIMIT 100
            """, (com_id,))
            files = []
            for r in cursor.fetchall():
                files.append({
                    "id": r["id"],
                    "crawl_job_id": r["crawl_job_id"],
                    "name": r["job_title"] or r["crawl_job_id"][:16],
                    "type": "parsed",
                    "has_model": r["has_model"],
                })
        return {"com_id": com_id, "files": files, "total": len(files)}


@app.get("/api/files/content")
async def get_file_content_db(crawl_job_id: str = ""):
    """获取文件内容（从数据库）"""
    if not crawl_job_id:
        raise HTTPException(status_code=400, detail="缺少 crawl_job_id")

    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM crawl_jobs WHERE crawl_job_id = %s", (crawl_job_id,))
        job = cursor.fetchone()
    
    if not job:
        raise HTTPException(status_code=404, detail="未找到")
    
    raw_json = job.get("raw_json", {})
    model_json = job.get("model_json", {})
    if isinstance(raw_json, str):
        raw_json = json.loads(raw_json)
    if isinstance(model_json, str):
        model_json = json.loads(model_json)
    
    return {
        "crawl_job_id": job["crawl_job_id"],
        "com_id": job["com_id"],
        "job_title": job.get("job_title", "") or "",
        "html_content": job.get("raw_html", "") or "",
        "json_content": raw_json,
        "model_content": model_json,
        "status": job["status"],
    }
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))
from crawl_db import CRAWL_DB_POOL


@app.get("/api/process/companies")
async def get_process_companies(page: int = 1, page_size: int = 50, search: str = ""):
    """获取公司列表及其解析状态"""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))
    from crawl_db import CRAWL_DB_POOL as _pool
    offset = (page - 1) * page_size
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(DISTINCT com_id) as total FROM crawl_jobs")
            total = cur.fetchone()["total"]
            sql = "SELECT com_id, COUNT(*) as total_files, SUM(CASE WHEN status IN ('parsed', 'ingested') THEN 1 ELSE 0 END) as ardata, SUM(CASE WHEN status = 'parsed' THEN 1 ELSE 0 END) as parsed, SUM(CASE WHEN status IN ('crawled', 'failed') THEN 1 ELSE 0 END) as pending FROM crawl_jobs"
            params = []
            if search:
                sql += " WHERE com_id LIKE %s"
                params.append(f"%{search}%")
            sql += " GROUP BY com_id ORDER BY pending DESC LIMIT %s OFFSET %s"
            params.extend([page_size, offset])
            cur.execute(sql, params)
            companies = [dict(r) for r in cur.fetchall()]
    return {"total": total, "page": page, "page_size": page_size, "companies": companies}


@app.get("/api/process/stats")
async def get_process_stats():
    """获取全局统计"""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "crawler"))
    from crawl_db import CRAWL_DB_POOL as _pool
    with _pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as total FROM crawl_jobs")
            total = cur.fetchone()["total"]
            cur.execute("SELECT status, COUNT(*) as cnt FROM crawl_jobs GROUP BY status")
            by_status = {r["status"]: r["cnt"] for r in cur.fetchall()}
    return {
        "total": total,
        "crawled": by_status.get("crawled", 0),
        "parsed": by_status.get("parsed", 0),
        "ingested": by_status.get("ingested", 0),
        "failed": by_status.get("failed", 0),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

