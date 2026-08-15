from fastapi import APIRouter, Query, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import os
import tempfile
import json
import time
from pathlib import Path
from collections import Counter

from db import get_db_cursor
from cache import get_cache, set_cache

router = APIRouter(prefix="/api/analysis/match", tags=["resume-match"])

# ============================================
# 配置常量
# ============================================

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

VECTOR_INDEX_PATH = DATA_DIR / "job_vectors.index"
VECTOR_META_PATH = DATA_DIR / "job_vectors_meta.json"

CACHE_TTL = 3600
SKILL_CACHE_KEY = "resume_match:skills"

_embedding_model = None

# ============================================
# 技能归一化系统
# ============================================

# 同义词映射表（小写去空格 → 标准名称）
SKILL_ALIASES = {
    # Spring 系列
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
    "spring-boot": "Spring Boot",
    "springcloud": "Spring Cloud",
    "spring cloud": "Spring Cloud",
    "spring-cloud": "Spring Cloud",
    "springmvc": "Spring MVC",
    "spring mvc": "Spring MVC",
    "spring-mvc": "Spring MVC",
    "spring": "Spring",
    
    # JavaScript/TypeScript
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "node": "Node.js",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "next": "Next.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "vue": "Vue.js",
    "reactjs": "React",
    "react.js": "React",
    "react": "React",
    "angular": "Angular",
    "angularjs": "Angular",
    
    # 数据库
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "es": "Elasticsearch",
    "oracle": "Oracle",
    "sqlserver": "SQL Server",
    "sql server": "SQL Server",
    "mssql": "SQL Server",
    
    # 语言
    "python": "Python",
    "java": "Java",
    "golang": "Go",
    "go": "Go",
    "c++": "C++",
    "cpp": "C++",
    "cplusplus": "C++",
    "c#": "C#",
    "csharp": "C#",
    "rust": "Rust",
    "php": "PHP",
    "ruby": "Ruby",
    "swift": "Swift",
    "kotlin": "Kotlin",
    "scala": "Scala",
    
    # DevOps & 云
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "linux": "Linux",
    "git": "Git",
    "jenkins": "Jenkins",
    "gitlab": "GitLab",
    "github": "GitHub",
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "GCP",
    "阿里云": "阿里云",
    "腾讯云": "腾讯云",
    
    # AI/ML
    "机器学习": "机器学习",
    "深度学习": "深度学习",
    "nlp": "NLP",
    "自然语言处理": "NLP",
    "大模型": "大模型",
    "llm": "大模型",
    "chatgpt": "ChatGPT",
    "aigc": "AIGC",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "keras": "Keras",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scikit-learn": "Scikit-learn",
    "scikitlearn": "Scikit-learn",
    "sklearn": "Scikit-learn",
    
    # Java 框架
    "mybatis": "MyBatis",
    "mybatis-plus": "MyBatis-Plus",
    "mybatisplus": "MyBatis-Plus",
    "hibernate": "Hibernate",
    "jpa": "JPA",
    "dubbo": "Dubbo",
    "zookeeper": "ZooKeeper",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "rocketmq": "RocketMQ",
    
    # Python 框架
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "tornado": "Tornado",
    "celery": "Celery",
    
    # 前端工具
    "webpack": "Webpack",
    "vite": "Vite",
    "gulp": "Gulp",
    "babel": "Babel",
    "sass": "Sass",
    "less": "Less",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "bootstrap": "Bootstrap",
    
    # 通用技能
    "web开发": "Web开发",
    "web 开发": "Web开发",
    "web": "Web开发",
    "数据库设计": "数据库设计",
    "数据库": "数据库",
    "restful": "RESTful",
    "rest": "RESTful",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "微服务": "微服务",
    "分布式": "分布式",
    "高并发": "高并发",
    "架构设计": "架构设计",
}


def _normalize_skill(skill: str) -> str:
    """
    技能名称归一化
    1. 去首尾空格
    2. 转小写去空格查同义词表
    3. 命中则返回标准名称，否则返回原始值（首尾trim）
    """
    skill = skill.strip()
    if not skill:
        return skill
    
    # 先精确查（保留空格的小写版本）
    lower_skill = skill.lower().strip()
    if lower_skill in SKILL_ALIASES:
        return SKILL_ALIASES[lower_skill]
    
    # 再模糊查（去除空格/横杠/下划线的版本）
    lookup_key = lower_skill.replace(" ", "").replace("-", "").replace("_", "")
    
    # 遍历别名表做同样的归一化匹配
    for alias_key, standard_name in SKILL_ALIASES.items():
        normalized_alias = alias_key.replace(" ", "").replace("-", "").replace("_", "")
        if lookup_key == normalized_alias:
            return standard_name
    
    # 都没匹配上，返回原始值（保持原有大小写）
    return skill


def _normalize_skill_list(skills: List[str]) -> List[str]:
    """
    对技能列表做归一化 + 去重
    """
    seen = set()
    result = []
    
    for skill in skills:
        if not isinstance(skill, str):
            continue
            
        normalized = _normalize_skill(skill)
        # 用小写版本做去重判断
        dedup_key = normalized.lower().replace(" ", "").replace("-", "").replace("_", "")
        
        if dedup_key and dedup_key not in seen:
            seen.add(dedup_key)
            result.append(normalized)
    
    return result


def _skill_to_dedup_key(skill: str) -> str:
    """将技能转为去重key（小写去空格去横杠）"""
    return skill.lower().replace(" ", "").replace("-", "").replace("_", "")


# ============================================
# 辅助函数
# ============================================

def _get_text_from_pdf(file_path: str) -> str:
    """PDF文本提取"""
    try:
        import fitz
    except ImportError:
        raise HTTPException(
            status_code=500, 
            detail="PyMuPDF未安装。请运行: pip install PyMuPDF"
        )
    
    try:
        doc = fitz.open(file_path)
        text_parts = []
        
        for page in doc:
            text_parts.append(page.get_text())
        
        doc.close()
        text = "\n".join(text_parts).strip()
        
        if len(text) < 100:
            raise HTTPException(
                status_code=400, 
                detail="PDF内容过短（<100字符），请确保PDF包含可复制的文本"
            )
        
        return text
        
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"PDF解析失败: {str(e)}"
        )


def _extract_skills(text: str) -> List[str]:
    """技能提取 + 归一化"""
    cached_keywords = get_cache(SKILL_CACHE_KEY)
    
    if cached_keywords:
        tech_keywords = json.loads(cached_keywords)
    else:
        tech_keywords = _load_skill_keywords_from_db()
        set_cache(SKILL_CACHE_KEY, json.dumps(tech_keywords, ensure_ascii=False), CACHE_TTL)
    
    text_lower = text.lower()
    found_skills = set()
    
    for kw in tech_keywords:
        if kw.lower() in text_lower or kw in text:
            found_skills.add(kw)
    
    # ✅ 归一化 + 去重
    return _normalize_skill_list(list(found_skills))


def _load_skill_keywords_from_db() -> List[str]:
    """从数据库加载热门技能"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT skill 
                FROM skill_stats_cache 
                ORDER BY total_count DESC 
                LIMIT 500
            """)
            rows = cursor.fetchall()
        
        keywords = [row["skill"] for row in rows]
    except Exception as e:
        print(f"⚠️ 从数据库加载技能失败: {e}")
        keywords = []
    
    fallback_keywords = [
        "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
        "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch",
        "React", "Vue", "Angular", "Next.js", "Node.js", "Django", "Flask", "Spring",
        "Docker", "Kubernetes", "Linux", "Git", "AWS", "Azure", "GCP",
        "机器学习", "深度学习", "NLP", "大模型", "LLM", "ChatGPT", "AIGC",
        "TensorFlow", "PyTorch", "Pandas", "NumPy",
        "Spring Boot", "MyBatis", "Web开发", "数据库设计",
    ]
    
    return list(set(keywords + fallback_keywords))


def _get_embedding(text: str) -> Optional[List[float]]:
    """文本向量化"""
    global _embedding_model
    
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            print("⏳ 加载向量模型...")
            _embedding_model = SentenceTransformer('shibing624/text2vec-base-chinese')
            print("✅ 模型加载完成")
        except ImportError:
            print("❌ sentence-transformers未安装")
            return None
        except Exception as e:
            print(f"❌ 向量模型加载失败: {e}")
            return None
    
    try:
        vector = _embedding_model.encode(text, normalize_embeddings=True)
        return vector.tolist()
    except Exception as e:
        print(f"❌ 向量生成失败: {e}")
        return None


def _fetch_job_details(job_ids: List[int]) -> List[Dict]:
    """批量查询职位详情"""
    if not job_ids:
        return []
    
    placeholders = ",".join(["%s"] * len(job_ids))
    
    with get_db_cursor() as cursor:
        cursor.execute(f"""
            SELECT 
                j.id, j.title, j.job_category, j.city, j.education_level,
                j.employment_type, j.salary_text, j.salary_min, j.salary_max,
                c.name AS company_name, c.short_name, c.logo_url AS company_logo_url,
                j.published_at, j.skill_tags
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.id IN ({placeholders})
              AND j.is_active = 1 
              AND j.status = 'open'
              AND j.published_at <= CURRENT_TIMESTAMP
        """, job_ids)
        
        results = []
        for r in cursor.fetchall():
            d = dict(r)
            tags = d.get("skill_tags")
            
            if isinstance(tags, str):
                try:
                    tag_list = json.loads(tags)
                except:
                    tag_list = []
            else:
                tag_list = tags or []
            
            # ✅ 归一化职位技能
            d["skillTags"] = _normalize_skill_list(tag_list)
            results.append(d)
        
        return results


async def _run_ai_analysis(
    resume_skills: List[str], 
    top_jobs: List[Dict], 
    resume_summary: str
) -> Dict[str, Any]:
    """AI Gap分析（修复版 - 归一化比较）"""
    gap_analysis = {
        "skillGaps": [],
        "strengths": [],
        "recommendations": [],
        "citySuggestions": [],
    }
    
    # ✅ 归一化简历技能（已经归一化过，但再做一次确保）
    normalized_resume = _normalize_skill_list(resume_skills)
    
    # 用于比较的 set（去重key）
    resume_dedup_keys = set(_skill_to_dedup_key(s) for s in normalized_resume)
    
    # ✅ 归一化所有职位技能后统计
    all_job_skills = []
    for job in top_jobs:
        tags = job.get("skillTags") or job.get("matchedSkills") or []
        # 每个职位的技能也做归一化
        normalized_tags = _normalize_skill_list(tags)
        all_job_skills.extend(normalized_tags)
    
    demand_counter = Counter(all_job_skills)
    
    # ✅ 用归一化后的key做比较
    gaps = []
    for skill, count in demand_counter.most_common(20):  # 多取一些再筛选
        skill_key = _skill_to_dedup_key(skill)
        
        if skill_key not in resume_dedup_keys:
            gaps.append({
                "skill": skill,
                "demandCount": count,
                "status": "missing"
            })
        else:
            gap_analysis["strengths"].append({
                "skill": skill,
                "demandCount": count
            })
    
    gap_analysis["skillGaps"] = gaps[:10]
    
    # 城市建议
    cities = [j.get("city") for j in top_jobs if j.get("city")]
    city_counter = Counter(cities)
    gap_analysis["citySuggestions"] = [
        {"city": city, "matchCount": count} 
        for city, count in city_counter.most_common(5)
    ]
    
    # 方向建议
    categories = [j.get("category") for j in top_jobs if j.get("category")]
    cat_counter = Counter(categories)
    gap_analysis["recommendations"] = [
        {"direction": cat, "jobCount": count} 
        for cat, count in cat_counter.most_common(5)
    ]
    
    return gap_analysis


class AIChatMessage(BaseModel):
    role: str
    content: str

class AIChatRequest(BaseModel):
    resumeSkills: List[str]
    aiAnalysis: Dict[str, Any]
    messages: List[AIChatMessage] = []

@router.post("/ai-chat")
async def ai_chat(req: AIChatRequest):
    """流式多轮对话 AI 职业顾问"""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise HTTPException(status_code=500, detail="未安装 openai 库")
        
    providers = [
        ("DASHSCOPE_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("QWEN_API_KEY", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("DEEPSEEK_API_KEY", "https://api.deepseek.com"),
    ]
    api_key, base_url = None, None
    for env_var, url in providers:
        key = os.getenv(env_var)
        if key:
            api_key, base_url = key, url
            break
    if not api_key:
        raise HTTPException(status_code=500, detail="未配置任何可用的 LLM API Key (DASHSCOPE_API_KEY / QWEN_API_KEY / DEEPSEEK_API_KEY)")

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30.0
    )
    
    if "dashscope" in base_url:
        models = [
            "qwen3-max-2026-01-23",
            "qwen3-vl-flash-2026-01-22",
            "qwen3.5-plus",
            "qwen3.5-plus-2026-02-15",
            "qwen3.5-122b-a10b",
            "qwen3.5-flash",
            "qwen3.5-27b",
            "qwen3.5-flash-2026-02-23",
            "qwen3.6-plus-2026-04-02",
            "qwen3.6-plus"
        ]
    else:
        models = ["deepseek-chat", "deepseek-reasoner"]
    
    gaps = ", ".join([f"{g.get('skill', '')}(缺)" for g in req.aiAnalysis.get("skillGaps", [])])
    strengths = ", ".join([s.get('skill', '') for s in req.aiAnalysis.get("strengths", [])])
    recommendations = ", ".join([r.get('direction', '') for r in req.aiAnalysis.get("recommendations", [])])
    
    system_prompt = f"""你是一名资深的职业规划师与招聘专家。
现在有一位求职者，我们解析了他的简历并与市场真实岗位匹配。
简历包含技能：{', '.join(req.resumeSkills) if req.resumeSkills else '未提取到可用技能'}
【他的优势/已掌握的市场热门技能】：{strengths or '较少'}
【他欠缺的市场热门技能】：{gaps or '未知'}
【符合他的主要岗位方向】：{recommendations or '未知'}

请分析目前的竞争力，指出市场当前趋势，并提供推荐的学习路径建议。如果你正在回答用户的特定问题，请结合这些背景信息直接回答。
要求：
1. 格式清晰，直接用Markdown输出。
2. 语气专业、直接、鼓励人，不要过多寒暄废话。"""

    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in req.messages:
        openai_messages.append({"role": msg.role, "content": msg.content})

    async def stream_generator():
        for model_name in models:
            try:
                print(f"⏳ 正在尝试调用 LLM 模型: {model_name}")
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=openai_messages,
                    stream=True,
                )
                print(f"✅ 模型 {model_name} 调用成功，开始流式输出")
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return # 成功，退出迭代
            except Exception as e:
                err_str = str(e)
                print(f"⚠️ 模型 {model_name} 调用失败: {err_str}")
                continue
                
        yield "⚠️ 所有可用大模型均调用失败（可能由于额度耗尽或网络问题），请稍后重试。"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


def _log_match_history(
    file_name: str,
    file_size: int,
    text_length: int,
    skills: List[str],
    method: str,
    top_k: int,
    result: Dict,
    total_time: int,
    parse_time: int,
    vector_time: int
):
    """记录匹配历史"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO resume_match_history (
                    file_name, file_size, text_length, extracted_skills, skill_count,
                    match_method, top_k, total_candidates, 
                    processing_time_ms, vector_search_time_ms, db_query_time_ms,
                    top_matched_job_ids, avg_match_score
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                file_name, file_size, text_length, 
                json.dumps(skills, ensure_ascii=False), len(skills),
                method, top_k, result.get("totalCandidates", 0),
                total_time, vector_time, total_time - parse_time - vector_time,
                json.dumps([j["id"] for j in result.get("topMatches", [])[:10]]),
                round(sum(j.get("matchScore", 0) for j in result.get("topMatches", [])[:10]) / 10, 2) if result.get("topMatches") else 0
            ))
    except Exception as e:
        print(f"❌ 记录匹配历史失败: {e}")


# ============================================
# API 端点
# ============================================

@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)) -> Dict[str, Any]:
    """简历解析"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持PDF格式")

    content = await file.read()
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start_time = time.time()
        
        text = _get_text_from_pdf(tmp_path)
        skills = _extract_skills(text)  # 已包含归一化
        
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        summary = " ".join(lines[:30]) if lines else text[:500]
        
        processing_time = int((time.time() - start_time) * 1000)
        
        return {
            "fileName": file.filename,
            "fileSize": len(content),
            "textLength": len(text),
            "summary": summary[:800],
            "skills": skills,
            "skillCount": len(skills),
            "processingTimeMs": processing_time,
        }
        
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/match")
async def match_resume(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    top_k: int = Query(50, ge=5, le=100),
) -> Dict[str, Any]:
    """简历匹配"""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持PDF格式")

    content = await file.read()
    
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        start_time = time.time()
        
        text = _get_text_from_pdf(tmp_path)
        resume_skills = _extract_skills(text)  # 已包含归一化
        
        parse_time = int((time.time() - start_time) * 1000)
        
        # 使用关键词匹配
        result = await _keyword_match_fallback(resume_skills, top_k, text[:2000])
        match_method = "keyword"
        vector_time = 0
        
        total_time = int((time.time() - start_time) * 1000)
        
        background_tasks.add_task(
            _log_match_history,
            file.filename,
            len(content),
            len(text),
            resume_skills,
            match_method,
            top_k,
            result,
            total_time,
            parse_time,
            vector_time
        )
        
        return {
            **result,
            "performanceMetrics": {
                "totalTimeMs": total_time,
                "parseTimeMs": parse_time,
                "vectorSearchTimeMs": vector_time,
                "dbQueryTimeMs": total_time - parse_time - vector_time,
            }
        }
        
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def _keyword_match_fallback(
    resume_skills: List[str], 
    top_k: int, 
    resume_summary: str
) -> Dict[str, Any]:
    """关键词匹配（归一化版本）"""
    with get_db_cursor() as cursor:
        conditions = ["j.is_active = 1", "j.status = 'open'", "j.published_at <= CURRENT_TIMESTAMP"]
        params = []
        
        if resume_skills:
            like_parts = []
            for skill in resume_skills[:10]:
                like_parts.append("(j.skill_tags LIKE %s OR j.job_description LIKE %s)")
                pattern = f"%{skill}%"
                params.extend([pattern, pattern])
            
            if like_parts:
                conditions.append(f"({' OR '.join(like_parts)})")
        
        where_clause = " AND ".join(conditions)
        
        cursor.execute(f"""
            SELECT 
                j.id, j.title, j.job_category, j.city, j.education_level,
                j.employment_type, j.salary_text, j.salary_min, j.salary_max,
                c.name AS company_name, c.short_name, c.logo_url AS company_logo_url,
                j.published_at, j.skill_tags
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE {where_clause}
            ORDER BY j.published_at DESC
            LIMIT %s
        """, params + [top_k * 3])
        
        rows = list(cursor.fetchall())
    
    results = []
    
    # ✅ 简历技能的去重key集合
    resume_dedup_keys = set(_skill_to_dedup_key(s) for s in resume_skills)
    
    for r in rows:
        tags = r.get("skill_tags")
        tag_list = []
        
        if tags:
            if isinstance(tags, str):
                try:
                    tag_list = json.loads(tags)
                except:
                    pass
            elif isinstance(tags, list):
                tag_list = tags
        
        # ✅ 归一化职位技能
        normalized_tags = _normalize_skill_list(tag_list)
        
        # ✅ 用归一化后的key做交集
        tag_dedup_map = {_skill_to_dedup_key(t): t for t in normalized_tags}
        
        overlap_keys = resume_dedup_keys & set(tag_dedup_map.keys())
        overlap_names = [tag_dedup_map[k] for k in overlap_keys]
        
        match_score = round(
            len(overlap_keys) / max(len(resume_skills), 1) * 100, 1
        )
        
        results.append({
            "id": r["id"],
            "title": r["title"],
            "category": r["job_category"],
            "city": r["city"],
            "education": r["education_level"],
            "salaryText": r.get("salary_text"),
            "companyName": r["company_name"],
            "companyShortName": r.get("short_name"),
            "companyLogoUrl": r.get("company_logo_url"),
            "publishedAt": str(r["published_at"]) if r.get("published_at") else None,
            "skillTags": normalized_tags,       # ✅ 返回归一化后的
            "matchedSkills": overlap_names,     # ✅ 返回归一化后的
            "matchScore": match_score,
        })
    
    results.sort(key=lambda x: x["matchScore"], reverse=True)
    
    ai_analysis = await _run_ai_analysis(resume_skills, results[:10], resume_summary)
    
    return {
        "method": "keyword",
        "totalCandidates": len(results),
        "topMatches": results[:10],
        "allCandidates": results,
        "resumeSkills": resume_skills,  # 已归一化
        "aiAnalysis": ai_analysis,
    }


# ============================================
# 索引构建（独立接口）
# ============================================

@router.post("/build-index")
async def build_vector_index(
    sample_size: int = Query(10000, ge=1000, le=100000),
    force_rebuild: bool = Query(False)
):
    """构建向量索引"""
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
        import faiss
    except ImportError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"缺少依赖: {e}. 请运行: pip install sentence-transformers faiss-cpu numpy"
        )
    
    try:
        start_time = time.time()
        
        # 1. 查询数据
        print(f"⏳ 查询 {sample_size} 条职位数据...")
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, 
                    CONCAT_WS(' ', 
                        COALESCE(title,''),
                        COALESCE(job_description,''), 
                        COALESCE(job_requirements,'')
                    ) AS text
                FROM jobs
                WHERE is_active = 1 
                  AND status = 'open'
                  AND published_at <= CURRENT_TIMESTAMP
                  AND (
                      (job_description IS NOT NULL AND job_description != '')
                      OR (job_requirements IS NOT NULL AND job_requirements != '')
                  )
                ORDER BY published_at DESC
                LIMIT %s
            """, (sample_size,))
            
            rows = cursor.fetchall()
        
        # 2. 数据清洗
        texts = []
        job_ids = []
        
        for r in rows:
            t = (r["text"] or "").strip()
            if len(t) >= 20:
                texts.append(t)
                job_ids.append(r["id"])
        
        if len(texts) < 100:
            raise HTTPException(
                status_code=400,
                detail=f"有效职位数量不足（{len(texts)}），需要至少100条"
            )
        
        print(f"✓ 有效职位: {len(texts)} 条")  
        # 3. 批量向量化
        print(f"⏳ 开始向量化...")
        model = SentenceTransformer('shibing624/text2vec-base-chinese')
        embeddings = model.encode(
            texts, 
            normalize_embeddings=True, 
            show_progress_bar=True,
            batch_size=32
        )
        
        print(f"✓ 向量化完成: {embeddings.shape}")
        
        # 4. 构建FAISS索引
        print(f"⏳ 构建FAISS索引...")
        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(np.array(embeddings, dtype=np.float32))
        
        print(f"✓ 索引构建完成: 维度={dim}, 数量={index.ntotal}")
        
        # 5. 保存索引
        faiss.write_index(index, str(VECTOR_INDEX_PATH))
        
        meta = {
            "jobIds": job_ids,
            "dim": int(dim),
            "count": len(job_ids),
            "model": "text2vec-base-chinese",
            "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sampleSize": sample_size,
        }
        
        with open(VECTOR_META_PATH, "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        
        # 6. 更新元数据表
        duration = int(time.time() - start_time)
        
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO vector_index_metadata (
                    index_type, model_name, dimension, total_jobs,
                    index_file_path, meta_file_path, build_duration_seconds, status
                ) VALUES (
                    'faiss', 'text2vec-base-chinese', %s, %s, %s, %s, %s, 'active'
                )
            """, (
                dim, len(job_ids), 
                str(VECTOR_INDEX_PATH), str(VECTOR_META_PATH), 
                duration
            ))
        
        print(f"✅ 索引构建完成，耗时 {duration} 秒")
        
        return {
            "status": "success",
            "indexSize": len(job_ids),
            "dimension": int(dim),
            "buildDurationSeconds": duration,
            "indexPath": str(VECTOR_INDEX_PATH),
            "metaPath": str(VECTOR_META_PATH),
        }
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"❌ 构建失败:\n{error_detail}")
        raise HTTPException(
            status_code=500,
            detail=f"构建失败: {str(e)}"
        )