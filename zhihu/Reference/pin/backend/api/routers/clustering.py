from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, List, Optional
from db import get_db_cursor
from cache import get_cache, set_cache
from collections import Counter, defaultdict
import re

router = APIRouter(prefix="/api/analysis/clustering", tags=["clustering"])

CACHE_TTL = 1800

# ============================================
# 停用词表
# ============================================
STOP_WORDS = set([
    # 基础停用词
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
    '自己', '这', '那', '她', '他', '它', '们', '什么', '这个', '那个', '可以',
    '以及', '等', '与', '或', '及', '为', '将', '被', '向', '从', '对', '把', '由',
    '且', '而', '但', '却', '因', '所以', '如果', '虽然', '然而', '因此', '所',
    
    # 职位描述高频词
    '进行', '相关', '具备', '负责', '能力', '经验', '工作', '岗位', '职位', 
    '优先', '熟悉', '了解', '掌握', '良好', '较强', '优秀', '一定', '对应',
    '包括', '以上', '以下', '具有', '能够', '需要', '使用', '通过', '根据',
    '完成', '参与', '协助', '支持', '配合', '推动', '跟进', '落地', '执行',
    '优化', '改进', '提升', '建设', '发展', '业务', '团队', '公司', '部门',
    '项目', '产品', '客户', '用户', '数据', '系统', '平台', '技术', '方案',
    
    # 学历噪音词（扩展）
    '本科', '硕士', '博士', '学历', '学位', '专业', '应届', '毕业生', '在校',
    '本科及以上', '硕士及以上', '博士及以上', '学历不限', '专业不限',
    '本科以上', '硕士以上', '大专及以上', '统招本科', '本科及以',
    '大专及以', '专科及以', '高中及以', '大专以上', '专科以上', '高中以上',
    
    # JD 标题类
    '岗位职责', '任职要求', '岗位要求', '加分项', '任职资格', '工作职责',
    '职位描述', '职位要求', '岗位描述', '岗位说明', '招聘要求',
    '工作要求', '工作内容', '主要工作', '工作地点', '工作时间', '薪资待遇',
    '根据业务发展需要', '根据公司安排', '完成上级交办', '培训',
    
    # 时间/数量相关
    '年以上', '年及以上', '年工作经验', '年相关', '年及',
    
    # 无意义形容词
    '非常', '特别', '比较', '相对', '绝对', '完全', '基本', '主要', '重要',
    '核心', '关键', '必须', '应该', '可能', '大概', '基本上', '一般', '较为',
    
    # 英文/符号类噪音
    'and', 'or', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
    'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
    'through', 'during', 'before', 'after', 'above', 'below', 'between',
    'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when',
    'where', 'why', 'how', 'all', 'each', 'few', 'more', 'most', 'other',
    'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
    'too', 'very', 'just', 'also', 'now', 'about', 'up', 'out', 'if',
    '&', '%', '#', '@', '*', '!', '~', '`', '^', '|', '\\', '/', '...',
    
    # 其他无意义碎片
    '如下', '如上', '上述', '如下所示', '包括但不限于', '其他', '其它',
    '各种', '各类型', '各类', '各种类型', '者优先', '可优先', '亦可',
    '或以上', '及以上', '以及上', '以下经验', '以上经验', '含以上',
])


def _clean_token(token: str) -> Optional[str]:
    """
    超级严格的分词清洗
    """
    token = token.strip()
    
    # 长度过滤（2-10个字符）
    if len(token) < 2 or len(token) > 10:
        return None
    
    # === 数字相关过滤 ===
    # 过滤纯数字
    if re.match(r'^\d+$', token):
        return None
    
    # 过滤"有1""有2""有3"这类（有+数字）
    if re.match(r'^有\d+', token):
        return None
    
    # 过滤以数字开头的（如"1年""2个"）
    if re.match(r'^\d', token):
        return None
    
    # 过滤以数字结尾的短词（如"工作1""项目2"）
    if re.search(r'\d$', token) and len(token) < 6:
        return None
    
    # 过滤包含多个数字的（如"5年以上"）
    if len(re.findall(r'\d', token)) >= 2:
        return None
    
    # === 特殊字符过滤 ===
    # 过滤包含空格/制表符/换行的
    if any(c in token for c in [' ', '\t', '\n', '\r']):
        return None
    
    # 过滤纯符号
    if re.match(r'^[^\w\u4e00-\u9fa5]+$', token):
        return None
    
    # === 学历/软技能过滤（基于关键词） ===
    # 过滤包含"及以"的词（如"本科及以上"的残留）
    if '及以' in token:
        return None
    
    # 过滤包含"能力"的词（太通用）
    if '能力' in token:
        return None
    
    # 过滤以"有"开头的短词（如"有责任心"）
    if token.startswith('有') and len(token) <= 5:
        return None
    
    # === 停用词过滤 ===
    if token in STOP_WORDS:
        return None
    
    # === 单字母/单字过滤 ===
    if len(token) == 1:
        return None
    
    return token


def _simple_tokenize(text: str) -> List[str]:
    """智能分词（超级版）"""
    # 预处理：统一空白字符
    text = re.sub(r'\s+', ' ', text)
    
    # 移除常见的 JD 标题（避免被分词）
    title_patterns = [
        r'岗位职责[:：]\s*',
        r'任职要求[:：]\s*',
        r'职位描述[:：]\s*',
        r'工作内容[:：]\s*',
        r'加分项[:：]\s*',
    ]
    for pattern in title_patterns:
        text = re.sub(pattern, ' ', text)
    
    try:
        import jieba
        jieba.setLogLevel(jieba.logging.INFO)
        
        raw_words = jieba.lcut(text)
        
        cleaned_words = []
        for w in raw_words:
            cleaned = _clean_token(w)
            if cleaned:
                cleaned_words.append(cleaned)
        
        return cleaned_words
        
    except ImportError:
        text = re.sub(r'[，。、；：！？""''（）【】《》\s]+', ' ', text)
        words = text.split()
        return [_clean_token(w) for w in words if _clean_token(w)]


def _get_cluster_label(keywords: List[str], category: str, cluster_size: int) -> str:
    """
    智能标签生成（增强版）
    优先识别技术栈 > 业务领域 > 职能关键词
    """
    if not keywords:
        return f"{category}(未识别)"
    
    # 技术栈关键词（全小写匹配）
    tech_keywords = {
        'python': 'Python', 'java': 'Java', 'javascript': 'JS', 
        'react': 'React', 'vue': 'Vue', 'spring': 'Spring', 
        'mysql': 'MySQL', 'redis': 'Redis', 'kafka': 'Kafka',
        'kubernetes': 'K8s', 'docker': 'Docker', 'aws': 'AWS',
        'tensorflow': 'TF', 'pytorch': 'PyTorch', 'golang': 'Go',
        'rust': 'Rust', 'typescript': 'TS', 'nodejs': 'Node',
        'angular': 'Angular', 'flutter': 'Flutter', 'android': 'Android',
        'ios': 'iOS', 'swift': 'Swift', 'kotlin': 'Kotlin',
    }
    
    # 业务领域关键词
    domain_keywords = {
        '金融科技': ['风控', '支付', '理财', '保险', '信贷', '银行', '证券'],
        '电商零售': ['供应链', '物流', '采购', '选品', '商品', '店铺'],
        '在线教育': ['课程', '教学', '培训', '辅导', '学员', '教研'],
        '医疗健康': ['诊断', '患者', '临床', '医药', '医院', '护理'],
        '游戏娱乐': ['玩家', '关卡', '数值策划', 'unity', 'ue4', '游戏'],
        '社交内容': ['内容运营', '社区', '用户增长', '推荐算法', '互动'],
        '企业服务': ['saas', 'crm', 'erp', '企业级', '解决方案'],
    }
    
    # 职能关键词
    function_keywords = {
        '前端开发': ['前端', '页面', '组件', 'ui', 'css', 'html'],
        '后端开发': ['后端', '接口', 'api', '服务端', '微服务'],
        '算法工程': ['算法', '模型', '机器学习', '深度学习', '推荐'],
        '数据分析': ['数据分析', '数据挖掘', 'sql', '报表', 'bi'],
        '测试质量': ['测试', '自动化', '质量', 'qa', 'bug'],
        '运维部署': ['运维', '部署', '监控', 'devops', 'ci/cd'],
        '产品设计': ['产品', '需求', '原型', 'prd', '用户体验'],
        '项目管理': ['项目管理', 'pmp', '敏捷', 'scrum', '进度'],
    }
    
    # 1. 优先识别技术栈
    found_tech = []
    for kw in keywords[:5]:
        kw_lower = kw.lower()
        if kw_lower in tech_keywords:
            found_tech.append(tech_keywords[kw_lower])
    
    if found_tech:
        tech_str = '+'.join(found_tech[:2])
        return f"{category}·{tech_str}"
    
    # 2. 识别业务领域
    for domain, kws in domain_keywords.items():
        if any(kw in keywords[:8] for kw in kws):
            return f"{domain}·{category}"
    
    # 3. 识别职能关键词
    for func, kws in function_keywords.items():
        if any(kw in keywords[:8] for kw in kws):
            return f"{func}·{category}"
    
    # 4. 使用第一个有意义的关键词
    for kw in keywords[:3]:
        # 过滤太通用的词
        if kw not in ['计算机', '工作', '学习', '开发', '管理']:
            return f"{category}·{kw[:4]}"
    
    # 5. 兜底方案
    return f"{category}·通用({cluster_size})"


def _get_feature_names(vectorizer):
    """兼容不同版本的 scikit-learn"""
    try:
        return vectorizer.get_feature_names_out()
    except AttributeError:
        return vectorizer.get_feature_names()


@router.get("/clusters")
async def get_job_clusters(
    n_clusters: int = Query(10, ge=3, le=20),
    sample_size: int = Query(3000, ge=500, le=10000),
    top_words: int = Query(15, ge=5, le=30),  # 增加到15个关键词用于标签生成
) -> Dict[str, Any]:
    """K-Means 聚类分析"""
    cache_key = f"clustering:clusters:{n_clusters}:{sample_size}:{top_words}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    # 数据采样
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT 
                id, 
                title, 
                job_category,
                CONCAT_WS(' ', 
                    COALESCE(job_description, ''), 
                    COALESCE(job_requirements, ''), 
                    COALESCE(job_responsibilities, '')
                ) AS full_text
            FROM jobs
            WHERE is_active = 1 
              AND status = 'open'
              AND published_at <= CURRENT_TIMESTAMP
              AND (
                  (job_description IS NOT NULL AND LENGTH(job_description) > 50)
                  OR (job_requirements IS NOT NULL AND LENGTH(job_requirements) > 30)
              )
            ORDER BY RAND()
            LIMIT %s
        """, (sample_size,))
        rows = cursor.fetchall()

    if len(rows) < 100:
        raise HTTPException(status_code=400, detail=f"数据不足：仅 {len(rows)} 条")

    # 文本预处理
    corpus = []
    job_ids = []
    titles = []
    categories = []
    
    for r in rows:
        text = (r["full_text"] or "").strip()
        if len(text) < 30:
            continue
        
        tokens = _simple_tokenize(text)
        if len(tokens) < 5:
            continue
        
        corpus.append(" ".join(tokens))
        job_ids.append(r["id"])
        titles.append(r["title"])
        categories.append(r["job_category"] or "未分类")

    if len(corpus) < 100:
        raise HTTPException(status_code=400, detail=f"有效文档仅 {len(corpus)} 条")

    # 聚类
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
        import numpy as np

        vectorizer = TfidfVectorizer(
            max_features=500,
            max_df=0.80,   # 降低到80%，更激进地过滤高频词
            min_df=5,      # 提高到5，过滤罕见词
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        X = vectorizer.fit_transform(corpus)

        actual_k = min(n_clusters, len(corpus) // 20, 15)
        
        kmeans = KMeans(
            n_clusters=actual_k, 
            random_state=42, 
            n_init=10, 
            max_iter=300,
            algorithm='auto'
        )
        labels = kmeans.fit_predict(X)

        feature_names = _get_feature_names(vectorizer)

        # 聚类结果分析
        clusters = []
        for cluster_id in range(actual_k):
            mask = labels == cluster_id
            cluster_indices = np.where(mask)[0]
            cluster_size = int(mask.sum())

            center = kmeans.cluster_centers_[cluster_id]
            top_indices = center.argsort()[-top_words:][::-1]
            top_keywords = [
                {
                    "word": str(feature_names[i]), 
                    "weight": round(float(center[i]), 4)
                } 
                for i in top_indices
            ]

            cluster_titles = [titles[i] for i in cluster_indices[:5]]

            cluster_categories = [categories[i] for i in cluster_indices]
            cat_counter = Counter(cluster_categories)
            dominant_cat, cat_count = cat_counter.most_common(1)[0] if cat_counter else ("未知", 0)

            # 计算簇内一致性
            if cluster_size > 1:
                cluster_docs = X[mask]
                centroid = center.reshape(1, -1)
                from sklearn.metrics.pairwise import cosine_similarity
                similarities = cosine_similarity(cluster_docs, centroid).flatten()
                coherence = float(np.mean(similarities))
            else:
                coherence = 1.0

            # 生成智能标签
            top_words_list = [kw["word"] for kw in top_keywords]
            cluster_label = _get_cluster_label(top_words_list, dominant_cat, cluster_size)

            clusters.append({
                "clusterId": int(cluster_id),
                "label": cluster_label,
                "size": cluster_size,
                "dominantCategory": dominant_cat,
                "categoryPurity": round(cat_count / cluster_size, 3),
                "coherence": round(coherence, 3),
                "topKeywords": top_keywords[:10],  # 只返回前10个
                "sampleTitles": cluster_titles,
            })

        clusters.sort(key=lambda x: x["size"], reverse=True)

        # 计算质量指标
        try:
            from sklearn.metrics import silhouette_score, calinski_harabasz_score
            silhouette = float(silhouette_score(X, labels, sample_size=min(1000, len(corpus))))
            calinski = float(calinski_harabasz_score(X.toarray(), labels))
        except:
            silhouette = calinski = 0.0

        result = {
            "totalDocuments": len(corpus),
            "nClusters": actual_k,
            "featureCount": X.shape[1],
            "qualityMetrics": {
                "silhouetteScore": round(silhouette, 3),
                "calinskiScore": round(calinski, 2),
            },
            "clusters": clusters,
        }
        
        set_cache(cache_key, result, CACHE_TTL)
        return result

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"缺少依赖: {str(e)}")
    except Exception as e:
        import traceback
        print(f"聚类错误: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"聚类失败: {str(e)}")


@router.get("/cluster-detail")
async def get_cluster_detail(
    cluster_id: int = Query(..., ge=0, description="聚类ID"),
    limit: int = Query(20, ge=5, le=50, description="返回职位数量"),
    n_clusters: int = Query(10, ge=3, le=20),
    sample_size: int = Query(3000, ge=500, le=10000),
) -> Dict[str, Any]:
    """获取指定聚类的详细信息"""
    cache_key = f"cluster:detail:{cluster_id}:{limit}:{n_clusters}:{sample_size}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    clusters_data = await get_job_clusters(
        n_clusters=n_clusters, 
        sample_size=sample_size, 
        top_words=15
    )

    if cluster_id >= clusters_data["nClusters"]:
        raise HTTPException(
            status_code=404, 
            detail=f"聚类 {cluster_id} 不存在（最大: {clusters_data['nClusters'] - 1}）"
        )

    cluster_info = clusters_data["clusters"][cluster_id]

    with get_db_cursor() as cursor:
        dominant_cat = cluster_info["dominantCategory"]
        keywords = [kw["word"] for kw in cluster_info["topKeywords"][:5]]
        
        like_conditions = " OR ".join([
            f"(j.job_description LIKE %s OR j.job_requirements LIKE %s OR j.title LIKE %s)"
            for _ in keywords
        ])
        
        like_params = []
        for kw in keywords:
            pattern = f"%{kw}%"
            like_params.extend([pattern, pattern, pattern])
        
        cursor.execute(f"""
            SELECT 
                j.id, j.title, j.job_category, j.city, j.education_level,
                j.employment_type, j.salary_text, c.name AS company_name,
                j.published_at
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.is_active = 1 AND j.status = 'open'
              AND j.published_at <= CURRENT_TIMESTAMP
              AND ({like_conditions})
            ORDER BY j.published_at DESC
            LIMIT %s
        """, like_params + [limit])
        
        jobs = cursor.fetchall()

    result_jobs = []
    for j in jobs:
        result_jobs.append({
            "id": j["id"],
            "title": j["title"],
            "category": j["job_category"],
            "city": j["city"],
            "education": j["education_level"],
            "salaryText": j["salary_text"],
            "companyName": j["company_name"],
            "publishedAt": j["published_at"].isoformat() if j["published_at"] else None,
        })

    result = {
        "clusterId": cluster_id,
        "label": cluster_info["label"],
        "totalInCluster": cluster_info["size"],
        "dominantCategory": cluster_info["dominantCategory"],
        "categoryPurity": cluster_info["categoryPurity"],
        "coherence": cluster_info["coherence"],
        "topKeywords": cluster_info["topKeywords"],
        "jobs": result_jobs,
    }

    set_cache(cache_key, result, CACHE_TTL)
    return result


@router.get("/category-distribution")
async def get_cluster_category_distribution(
    n_clusters: int = Query(10, ge=3, le=20),
    sample_size: int = Query(3000, ge=500, le=10000),
) -> List[Dict[str, Any]]:
    """分析聚类结果与原始职类的分布关系"""
    cache_key = f"clustering:cat-dist:{n_clusters}:{sample_size}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached

    clusters_data = await get_job_clusters(
        n_clusters=n_clusters, 
        sample_size=sample_size, 
        top_words=5
    )

    distribution = []
    for cluster in clusters_data["clusters"]:
        distribution.append({
            "clusterId": cluster["clusterId"],
            "label": cluster["label"],
            "size": cluster["size"],
            "dominantCategory": cluster["dominantCategory"],
            "categoryPurity": cluster["categoryPurity"],
            "coherence": cluster["coherence"],
            "topKeywords": [kw["word"] for kw in cluster["topKeywords"][:5]],
        })

    set_cache(cache_key, distribution, CACHE_TTL)
    return distribution


@router.get("/quality-report")
async def get_clustering_quality_report(
    n_clusters: int = Query(10, ge=3, le=20),
    sample_size: int = Query(3000, ge=500, le=10000),
) -> Dict[str, Any]:
    """聚类质量评估报告"""
    clusters_data = await get_job_clusters(
        n_clusters=n_clusters, 
        sample_size=sample_size, 
        top_words=10
    )

    purities = [c["categoryPurity"] for c in clusters_data["clusters"]]
    coherences = [c["coherence"] for c in clusters_data["clusters"]]
    sizes = [c["size"] for c in clusters_data["clusters"]]

    import numpy as np
    
    avg_purity = float(np.mean(purities))
    avg_coherence = float(np.mean(coherences))
    size_std = float(np.std(sizes))
    
    recommendations = _get_clustering_recommendations(
        clusters_data["qualityMetrics"]["silhouetteScore"],
        avg_purity,
        size_std,
    )
    
    return {
        "overallQuality": {
            "silhouetteScore": clusters_data["qualityMetrics"]["silhouetteScore"],
            "calinskiScore": clusters_data["qualityMetrics"]["calinskiScore"],
            "avgPurity": round(avg_purity, 3),
            "avgCoherence": round(avg_coherence, 3),
        },
        "sizeDistribution": {
            "min": int(np.min(sizes)),
            "max": int(np.max(sizes)),
            "mean": round(float(np.mean(sizes)), 1),
            "std": round(size_std, 1),
        },
        "recommendations": recommendations
    }


def _get_clustering_recommendations(silhouette: float, avg_purity: float, size_std: float) -> List[str]:
    """根据质量指标生成优化建议"""
    recommendations = []
    
    if silhouette < 0.3:
        recommendations.append("⚠️ 轮廓系数较低，建议调整聚类数量（增加或减少）")
    elif silhouette > 0.6:
        recommendations.append("✓ 聚类效果优秀，簇间区分度高")
    else:
        recommendations.append("聚类效果中等，可尝试调整参数优化")
    
    if avg_purity < 0.5:
        recommendations.append("💡 职类纯度较低，说明聚类跨越了多个原始职类，可能发现了新的职位族群")
    elif avg_purity > 0.8:
        recommendations.append("✓ 职类纯度很高，聚类结果与原始分类高度一致")
    else:
        recommendations.append("职类纯度中等，聚类发现了部分跨职类模式")
    
    if size_std > 100:
        recommendations.append("⚠️ 簇大小分布不均衡，存在超大簇，建议增加聚类数量")
    else:
        recommendations.append("✓ 簇大小分布较为均衡")
    
    return recommendations