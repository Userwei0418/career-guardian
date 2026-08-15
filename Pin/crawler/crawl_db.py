"""crawler/db.py - 数据库操作（新 schema）"""
import pymysql, json, uuid, os
from dbutils.pooled_db import PooledDB
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CRAWL_DB_POOL = PooledDB(
    creator=pymysql, maxconnections=5,
    host=os.getenv("CRAWL_DB_HOST", "127.0.0.1"),
    port=int(os.getenv("CRAWL_DB_PORT", "3306")),
    user=os.getenv("CRAWL_DB_USER", "root"),
    password=os.getenv("CRAWL_DB_PASSWORD", ""),
    database=os.getenv("CRAWL_DB_NAME", "zhaogebanshang"),
    charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
)

def get_active_companies():
    """获取所有活跃公司"""
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT com_id, com_name, json_config FROM crawl_companies WHERE is_active = 1 ORDER BY com_id")
            rows = cur.fetchall()
    for r in rows:
        if isinstance(r.get("json_config"), str):
            r["json_config"] = json.loads(r["json_config"])
    return rows

def get_companies_by_ids(company_ids: list) -> dict:
    """通过 com_id 列表获取公司"""
    if not company_ids:
        return {}
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(company_ids))
            cur.execute(f"SELECT com_id, com_name, json_config FROM crawl_companies WHERE com_id IN ({placeholders})", company_ids)
            rows = cur.fetchall()
    result = {}
    for r in rows:
        if isinstance(r.get("json_config"), str):
            r["json_config"] = json.loads(r["json_config"])
        result[r["com_id"]] = r
    return result

def save_crawled_job(com_id, job_title, job_type, source_url, raw_html, raw_json):
    """保存抓取的职位数据"""
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO crawl_jobs (crawl_job_id, com_id, job_title, job_type, source_url, raw_html, raw_json, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, \"crawled\")
            """, (str(uuid.uuid4()), com_id, job_title, job_type, source_url, raw_html,
                  json.dumps(raw_json, ensure_ascii=False) if raw_json else None))
            conn.commit()
    return cur.lastrowid

def get_pending_parse(company_ids=None, limit=100):
    """获取待解析的职位"""
    sql = "SELECT * FROM crawl_jobs WHERE status = \"crawled\""
    params = []
    if company_ids:
        sql += " AND com_id IN (" + ",".join(["%s"] * len(company_ids)) + ")"
        params.extend(company_ids)
    sql += " LIMIT %s"
    params.append(limit)
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def update_parsed(crawl_job_id, model_json):
    """更新为已解析"""
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE crawl_jobs SET status = \"parsed\", model_json = %s, parsed_at = NOW()
                WHERE crawl_job_id = %s
            """, (json.dumps(model_json, ensure_ascii=False), crawl_job_id))
            conn.commit()

def get_pending_ingest(limit=100):
    """获取待入库的职位"""
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM crawl_jobs WHERE status = \"parsed\" LIMIT %s", (limit,))
            return cur.fetchall()

def update_ingested(crawl_job_id, job_id):
    """更新为已入库"""
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE crawl_jobs SET status = \"ingested\", job_id = %s, ingested_at = NOW()
                WHERE crawl_job_id = %s
            """, (job_id, crawl_job_id))
            conn.commit()

def update_company_last_crawl(com_id):
    """更新公司最后抓取时间"""
    with CRAWL_DB_POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE crawl_companies SET last_crawl_at = NOW(), crawl_count = crawl_count + 1
                WHERE com_id = %s
            """, (com_id,))
            conn.commit()
