"""
spider_data.py - 数据库驱动的数据处理（最终版）
"""
import os, json, tempfile, uuid

# 设置数据库模块路径（确保 crawler/db.py 可被找到）
_db_module_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "crawler")
if _db_module_path not in __import__("sys").path:
    __import__("sys").path.insert(0, _db_module_path)

from crawl_db import get_pending_parse, update_parsed
from parsegpt.cjob_model import parse_cjob

DEFAULT_PCOUNT = 3

class SpiderData:
    """数据处理 - 数据库驱动"""

    def __init__(self, spider_com):
        self.spider_com = spider_com
        self.monitor = spider_com.monitor

    def process_pending_jobs(self, company_ids=None, limit=100):
        """处理待解析的职位"""
        jobs = get_pending_parse(company_ids=company_ids, limit=limit)
        if not jobs:
            return 0

        # 创建临时目录
        tmp_model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tmp_models")
        os.makedirs(tmp_model_dir, exist_ok=True)

        processed = 0
        for job in jobs:
            job_id = job["id"]
            raw_html = job.get("raw_html", "")
            raw_json = job.get("raw_json", {})
            if isinstance(raw_json, str):
                raw_json = json.loads(raw_json)

            if not raw_html or len(raw_html) < 100:
                continue

            try:
                # Write HTML to temp file
                file_hash = job.get("crawl_job_id", str(uuid.uuid4()))[:16]
                tmp_html = os.path.join(tmp_model_dir, f"detail_{file_hash}.html")
                with open(tmp_html, "w", encoding="utf-8") as f:
                    f.write(raw_html)

                # Prepare parameters for parse_cjob
                _info = raw_json if raw_json else {"announcement_name": job.get("job_title", ""),
                                                    "full_url": job.get("source_url", "")}
                com_info = {
                    "com_name": raw_json.get("com_name", job.get("job_title", "")),
                    "com_webname": raw_json.get("com_webname", ""),
                    "com_logo": raw_json.get("com_logo", ""),
                    "urls": raw_json.get("urls", {}),
                    "pre_open_url": raw_json.get("pre_open_url", ""),
                    "json_domain": raw_json.get("json_domain", ""),
                    "func_name": raw_json.get("func_name", ""),
                    "detail_selector": raw_json.get("detail_selector", ""),
                    "detail_selectors": raw_json.get("detail_selectors", ""),
                    "table_selector": raw_json.get("table_selector", ""),
                    "table_selectors": raw_json.get("table_selectors", ""),
                    "template": raw_json.get("template", ""),
                    "hd_all_location": raw_json.get("hd_all_location", ""),
                    "click_text": raw_json.get("click_text"),
                    "click_type": raw_json.get("click_type"),
                    "max_parent_level": raw_json.get("max_parent_level"),
                    "detail_hd": raw_json.get("detail_hd", ""),
                    "job_type": raw_json.get("job_type", ""),
                }
                model_file = os.path.join(tmp_model_dir, f"detail_{file_hash}.model.json")
                stats = {}

                ok, msg = parse_cjob(
                    self, model_file, _info, com_info,
                    os.path.join(tmp_model_dir, f"detail_{file_hash}.json.expired"),
                    tmp_html, stats
                )

                if ok == "ok" and os.path.exists(model_file):
                    with open(model_file, "r", encoding="utf-8") as mf:
                        model_json = json.load(mf)
                    update_parsed(job["crawl_job_id"], model_json)
                    processed += 1
                elif ok == "Err":
                    update_parsed(job["crawl_job_id"], {"_error": msg})

            except Exception as e:
                print(f"parse error job {job_id}: {e}", flush=True)

        return processed

    def process_announcement_data(self, key, sch_info, stat, proc_type="cjob"):
        """兼容旧接口"""
        pass

