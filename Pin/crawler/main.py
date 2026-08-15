"""main.py - 招聘数据爬虫（数据库驱动）"""
import sys, os, time, argparse

# 确保 crawler 和 services 目录在路径中
_crawler_dir = os.path.dirname(os.path.abspath(__file__))
_services_dir = os.path.join(_crawler_dir, "..", "services")
for p in [_crawler_dir, _services_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

from playwright.sync_api import sync_playwright
from spider_com import SpiderCom
from spider_data import SpiderData
from utils import ner_logger

parser = argparse.ArgumentParser(description="招聘JD爬虫（DB驱动）")
parser.add_argument("-m", "--method", default="cp", help="cp=crawl, process=LLM解析, ingest=入库")
parser.add_argument("--company-ids", default="", help="指定公司ID(逗号分隔)")
parser.add_argument("--all", action="store_true", help="所有活跃公司")
parser.add_argument("-p", "--proxy", default="", help="代理")

args = parser.parse_args()

def crawl_companies(company_ids=None):
    """1. 抓取公司页面"""
    if not company_ids:
        from crawl_db import get_active_companies
        company_ids = [c["com_id"] for c in get_active_companies()[:50]]

    sc = SpiderCom(use_db=True)
    executable_path = sc.get_browser_path()
    nodes = sc.get_nodes(company_ids)

    if not nodes:
        print("ERROR: 未找到公司节点", flush=True)
        return

    print(f"找到 {len(nodes)} 个公司节点", flush=True)

    with sync_playwright() as p:
        from utils_playwright import get_browser
        browser = get_browser(p, executable_path, args.proxy)
        sc.browser = browser
        page = browser.new_page()

        for i, (com_id, node_list) in enumerate(nodes.items()):
            print(f"[{i+1}/{len(nodes)}] 抓取: {com_id}", flush=True)
            for info in node_list:
                for url_type, url in info.get("urls", {}).items():
                    try:
                        sc.run(page, com_id, {**info, "_k": url_type, "_url": url}, {})
                    except Exception as e:
                        print(f"  错误: {e}", flush=True)
                        try:
                            page = browser.new_page()
                        except:
                            pass

        browser.close()

def process_jobs(company_ids=None):
    """2. LLM解析"""
    sc = SpiderCom(use_db=True)
    sd = SpiderData(sc)
    processed = sd.process_pending_jobs(company_ids=company_ids, limit=100)
    print(f"解析完成: {processed} 条", flush=True)

def ingest_jobs():
    """3. 数据入库"""
    from ingest_cjob import run_ingest
    result = run_ingest()
    print(f"入库: {result}", flush=True)


if __name__ == "__main__":
    company_ids = None
    if args.company_ids:
        company_ids = [c.strip() for c in args.company_ids.split(",") if c.strip()]
    elif args.all:
        from crawl_db import get_active_companies
        company_ids = [c["com_id"] for c in get_active_companies()]
        print(f"全量模式: {len(company_ids)} 家公司", flush=True)

    if args.method == "cp":
        crawl_companies(company_ids)
    elif args.method in ["process", "cjob"]:
        process_jobs(company_ids)
    elif args.method == "ingest":
        ingest_jobs()

