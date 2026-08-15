from fastapi import APIRouter, Query, HTTPException
from typing import Any, Dict, Optional
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from db import get_db_cursor

router = APIRouter(prefix="/api/company-sources", tags=["company-sources"])

@router.get("")
async def get_company_sources(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    conditions = ["is_active = 1"]
    params = []
    if search:
        conditions.append("(com_name LIKE %s OR com_id LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = " AND ".join(conditions)
    offset = (page - 1) * page_size
    with get_db_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) as total FROM crawl_companies WHERE {where}", params)
        total = cursor.fetchone()["total"]
        cursor.execute(f"SELECT com_id, com_name, com_webname, json_config FROM crawl_companies WHERE {where} ORDER BY com_id LIMIT %s OFFSET %s", params + [page_size, offset])
        rows = cursor.fetchall()
    companies = []
    for r in rows:
        c = dict(r)
        jc = c.get("json_config", {}) or {}
        if isinstance(jc, str):
            jc = json.loads(jc)
        c["urls"] = list(jc.get("urls", {}).keys()) if isinstance(jc.get("urls"), dict) else []
        c["template"] = jc.get("template", "")
        c["func_name"] = jc.get("func_name", "")
        c["json_domain"] = jc.get("json_domain", "")
        c["hd_all_location"] = jc.get("hd_all_location", "")
        companies.append(c)
    return {"total": total, "page": page, "page_size": page_size, "companies": companies}

@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as total FROM crawl_companies WHERE is_active = 1")
        total = cursor.fetchone()["total"]
    return {"total": total, "files": []}

@router.get("/{com_id}")
async def get_company_detail(com_id: str) -> Dict[str, Any]:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM crawl_companies WHERE com_id = %s", (com_id,))
        company = cursor.fetchone()
    if not company:
        raise HTTPException(status_code=404)
    result = dict(company)
    if result.get("json_config") and isinstance(result["json_config"], str):
        result["json_config"] = json.loads(result["json_config"])
    return result
@router.put("/{com_id}")
async def update_company_config(com_id: str, body: Dict[str, Any]):
    jc = body.get("json_config")
    if not jc:
        raise HTTPException(status_code=400, detail="json_config required")
    with get_db_cursor() as cursor:
        cursor.execute("UPDATE crawl_companies SET json_config = %s WHERE com_id = %s", (json.dumps(jc, ensure_ascii=False), com_id))
    return {"message": "ok"}