"""
Pipeline 编排器：抓取 → 解析 → 入库 全流程
"""
import os
import sys
import time
import subprocess
from pathlib import Path

CRAWLER_DIR = Path(__file__).resolve().parent
MAIN_PY = str(CRAWLER_DIR / "main.py")


def run_cmd(cmd: list[str], description: str = "") -> dict:
    """执行命令并返回结果"""
    if description:
        print(f"[Pipeline] {description}")
    print(f"  命令: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(CRAWLER_DIR),
    )

    output_lines = []
    for line in iter(proc.stdout.readline, ""):
        line = line.strip()
        if line:
            output_lines.append(line)
            print(f"  {line}")

    proc.wait()
    return {
        "returncode": proc.returncode,
        "output": output_lines,
        "success": proc.returncode == 0,
    }


def crawl_companies(config_file: str = "", company_ids: list[str] = None) -> dict:
    """步骤1: 抓取公司页面（数据库驱动）"""
    cmd = [sys.executable, MAIN_PY, "-m", "cp"]
    if company_ids:
        cmd.extend(["--company-ids", ",".join(company_ids)])
    return run_cmd(cmd, f"抓取公司: {company_ids or '全部'}")


def process_jobs(config_file: str = "", company_ids: list[str] = None) -> dict:
    """步骤2: LLM 解析（数据库驱动）"""
    cmd = [sys.executable, MAIN_PY, "-m", "cjob"]
    if company_ids:
        cmd.extend(["--company-ids", ",".join(company_ids)])
    return run_cmd(cmd, f"LLM 解析: {company_ids or '全部'}")


def ingest_data() -> dict:
    """步骤3: 入库"""
    backend_dir = str(CRAWLER_DIR.parent / "backend")
    ingest_script = os.path.join(backend_dir, "ingest_cjob.py")
    cmd = [sys.executable, ingest_script]
    return run_cmd(cmd, "数据入库 MySQL")


def run_pipeline(config_file: str = "50", company_ids: list[str] = None) -> dict:
    """运行完整 Pipeline"""
    results = {
        "crawl": None,
        "process": None,
        "ingest": None,
        "success": False,
    }

    # Step 1: Crawl
    print("=" * 60)
    print("Pipeline 步骤 1/3: 抓取公司页面")
    print("=" * 60)
    results["crawl"] = crawl_companies(config_file, company_ids)
    if not results["crawl"]["success"]:
        print("[Pipeline] 抓取失败，中止")
        return results

    time.sleep(2)

    # Step 2: Process
    print("\n" + "=" * 60)
    print("Pipeline 步骤 2/3: LLM 解析")
    print("=" * 60)
    results["process"] = process_jobs(config_file, company_ids)
    if not results["process"]["success"]:
        print("[Pipeline] LLM 解析失败，中止")
        return results

    time.sleep(2)

    # Step 3: Ingest
    print("\n" + "=" * 60)
    print("Pipeline 步骤 3/3: 数据入库")
    print("=" * 60)
    results["ingest"] = ingest_data()

    results["success"] = all([
        results["crawl"]["success"],
        results["process"]["success"],
        results["ingest"]["success"],
    ])

    print("\n" + "=" * 60)
    if results["success"]:
        print("✅ Pipeline 执行成功!")
    else:
        print("❌ Pipeline 执行失败!")
    print("=" * 60)

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", default="50")
    parser.add_argument("--company-ids", default="")
    args = parser.parse_args()

    company_ids = [c.strip() for c in args.company_ids.split(",") if c.strip()] or None
    run_pipeline(args.file, company_ids)
