"""数据库操作 stub（兼容 cjob_model.py 导入）"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "api"))
from db import get_db_cursor

def record_parsed_file(com_id, file_hash, model_file_path):
    """记录解析完成的文件"""
    with get_db_cursor() as cursor:
        cursor.execute(
            "UPDATE crawl_jobs SET status = \'parsed\', model_json_path = %s, parsed_at = NOW() WHERE com_id = %s AND file_hash = %s",
            (model_file_path, com_id, file_hash)
        )
    return True

def update_parse_status(com_id, status="parsed"):
    """更新解析状态"""
    pass
