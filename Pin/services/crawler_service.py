"""
爬虫管理服务 - 完全重构为同步执行 + 线程池
"""
import asyncio
import json
import os
import sys
import time
import uuid
import subprocess
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from enum import Enum

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psutil

CRAWLER_DIR = Path(__file__).parent.parent / "crawler"
sys.path.insert(0, str(CRAWLER_DIR))

app = FastAPI(title="爬虫管理服务", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"

class TaskType(str, Enum):
    COMPANY = "company"
    PROCESS = "process"
    FULL = "full"

@dataclass
class CrawlerTask:
    id: str
    type: str
    status: TaskStatus
    progress: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    items_processed: int = 0
    items_total: int = 0
    current_target: str = ""
    log_file: str = ""

@dataclass
class SystemMetrics:
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    active_tasks: int
    crawler_processes: int

tasks: dict[str, CrawlerTask] = {}
task_logs: dict[str, list[str]] = {}
crawler_processes: dict[str, subprocess.Popen] = {}

LOG_DIR = CRAWLER_DIR / "log"
LOG_DIR.mkdir(exist_ok=True)

# ==========================================
# 爬虫控制函数
# ==========================================

def get_crawler_command(task_type: str, task_id: str, company_ids: list = None) -> list[str]:
    """生成爬虫命令（数据库驱动）"""
    python_exe = sys.executable
    crawler_main = str(CRAWLER_DIR / "main.py")
    method = "cp"
    if task_type == TaskType.PROCESS:
        method = "process"
    cmd = [python_exe, "-u", crawler_main, "-m", method]
    if company_ids:
        cmd.extend(["--company-ids", ",".join(company_ids)])
    return cmd


def _run_crawler_task_sync(task_id: str, task_type: str, company_ids_str: str = ""):
    """同步执行爬虫任务（在线程池中运行）"""
    task = tasks[task_id]
    task.status = TaskStatus.RUNNING
    task.started_at = datetime.now().isoformat()
    task.log_file = str(LOG_DIR / f"task_{task_id}.log")
    
    try:
        # Parse company_ids
        company_ids = [c.strip() for c in company_ids_str.split(",") if c.strip()] if company_ids_str else None
        cmd = get_crawler_command(task_type, task_id, company_ids)
        
        with open(task.log_file, "w", encoding="utf-8") as log_f:
            log_f.write(f"[{datetime.now()}] 启动爬虫任务: {task_id}\n")
            log_f.write(f"[{datetime.now()}] 命令: {' '.join(cmd)}\n")
            log_f.flush()
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(CRAWLER_DIR),
                env={**os.environ, "PYTHONPATH": str(CRAWLER_DIR), "PYTHONIOENCODING": "utf-8"}
            )
            crawler_processes[task_id] = process
            
            for line in iter(process.stdout.readline, ''):
                if task.status == TaskStatus.STOPPED:
                    process.terminate()
                    break
                line = line.strip()
                if line:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    log_f.write(f"[{timestamp}] {line}\n")
                    log_f.flush()
                    if "开始爬取" in line:
                        task.current_target = line.split("开始爬取:")[-1].strip()
                    elif "完成" in line:
                        task.items_processed += 1
                        task.progress = min(95, task.progress + 5)
                    elif "错误" in line or "Error" in line:
                        task_logs.setdefault(task_id, []).append(f"[ERROR] {line}")
            
            return_code = process.wait()
            if task.status != TaskStatus.STOPPED:
                if return_code == 0:
                    task.status = TaskStatus.COMPLETED
                    task.progress = 100
                    task.completed_at = datetime.now().isoformat()
                else:
                    task.status = TaskStatus.FAILED
                    task.error = f"进程退出码: {return_code}"
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)
    finally:
        if task_id in crawler_processes:
            del crawler_processes[task_id]


# Thread pool for running crawl tasks
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)

async def run_crawler_task(task_id: str, task_type: str, company_ids_str: str = ""):
    """异步包装：在线程池中运行"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_thread_pool, _run_crawler_task_sync, task_id, task_type, company_ids_str)


def stop_crawler_process(task_id: str):
    if task_id in crawler_processes:
        process = crawler_processes[task_id]
        try:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except Exception as e:
            print(f"停止进程失败: {e}")
    if task_id in tasks:
        tasks[task_id].status = TaskStatus.STOPPED
        tasks[task_id].completed_at = datetime.now().isoformat()

# ==========================================
# API
# ==========================================

class StartTaskRequest(BaseModel):
    task_type: str = "company"
    company_ids: str = ""

@app.post("/start")
async def start_task(request: StartTaskRequest):
    running_tasks = [t for t in tasks.values() if t.status == TaskStatus.RUNNING]
    if len(running_tasks) >= 3:
        raise HTTPException(status_code=400, detail="已有3个任务运行中")
    
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = CrawlerTask(
        id=task_id, type=request.task_type, status=TaskStatus.PENDING, progress=0
    )
    task_logs[task_id] = []
    
    # Fire and forget - run in thread pool
    asyncio.ensure_future(run_crawler_task(task_id, request.task_type, request.company_ids))
    
    return {"task_id": task_id, "status": "started", "message": f"任务已启动: {request.task_type}"}

@app.get("/status")
async def get_status():
    active = sum(1 for t in tasks.values() if t.status == TaskStatus.RUNNING)
    completed = sum(1 for t in tasks.values() if t.status == TaskStatus.COMPLETED)
    return {"status": "running" if active > 0 else "idle", "active_tasks": active, "completed_tasks": completed, "total_tasks": len(tasks)}

@app.get("/tasks")
async def get_tasks():
    return {"tasks": [asdict(t) for t in tasks.values()]}

@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return asdict(tasks[task_id])

@app.get("/tasks/{task_id}/logs")
async def get_task_logs(task_id: str, limit: int = 100):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    task = tasks[task_id]
    logs = []
    if task.log_file and os.path.exists(task.log_file):
        try:
            with open(task.log_file, "r", encoding="utf-8") as f:
                logs = [line.strip() for line in f.readlines()[-limit:]]
        except Exception as e:
            logs = [f"读取日志失败: {e}"]
    if task_id in task_logs:
        logs.extend(task_logs[task_id][-limit:])
    return {"logs": logs}

@app.post("/stop/{task_id}")
async def stop_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    if tasks[task_id].status != TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="任务未运行")
    stop_crawler_process(task_id)
    return {"task_id": task_id, "status": "stopped", "message": "任务已停止"}

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    if tasks[task_id].status == TaskStatus.RUNNING:
        stop_crawler_process(task_id)
    del tasks[task_id]
    if task_id in task_logs:
        del task_logs[task_id]
    return {"message": "任务已删除"}

@app.get("/metrics")
async def get_metrics():
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    crawler_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and 'main.py' in ' '.join(cmdline):
                crawler_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {
        "cpu_percent": cpu, "memory_percent": mem.percent,
        "memory_used_mb": round(mem.used / 1024 / 1024, 2),
        "memory_total_mb": round(mem.total / 1024 / 1024, 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
        "active_tasks": sum(1 for t in tasks.values() if t.status == TaskStatus.RUNNING),
        "crawler_processes": crawler_count,
    }

@app.get("/")
async def root():
    return {"message": "爬虫管理服务 v2.0", "mode": "数据库驱动"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
