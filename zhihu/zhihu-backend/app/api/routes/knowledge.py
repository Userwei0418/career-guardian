"""知识学堂 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.services.knowledge_service import get_article_list, get_article, search_by_keyword

router = APIRouter()


@router.get("/")
def list_articles(
    category: str = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取文章列表"""
    return get_article_list(db, category)


@router.get("/search")
def search_article(
    keyword: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """根据关键词匹配文章"""
    result = search_by_keyword(db, keyword)
    if not result:
        raise HTTPException(status_code=404, detail="未找到相关文章")
    return result


@router.get("/{slug}")
def get_article_detail(
    slug: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单篇文章详情"""
    article = get_article(db, slug)
    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")
    return article
