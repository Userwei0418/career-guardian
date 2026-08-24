from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mysql_test_support import MYSQL_TEST_DATABASE_URL, mysql_test

from app.models.knowledge_article import KnowledgeArticle
from app.services.knowledge_service import (
    CASHFLOW_ARTICLES,
    CASHFLOW_ARTICLES_0053,
    CASHFLOW_GUIDE_ARTICLES_0055,
    CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055,
    get_article,
    get_article_list,
    recommend_cashflow_knowledge,
)


class CashflowKnowledgeArticleCatalogTest(unittest.TestCase):
    def test_cashflow_article_catalog_keeps_legacy_topics_and_adds_six_user_guides(self) -> None:
        legacy_slugs = {
            "cashflow-internal-transfer",
            "cashflow-refund-reimbursement",
            "cashflow-credit-card-repayment",
            "cashflow-payslip-gross-net",
            "cashflow-screenshot-review",
            "cashflow-confirmed-budget",
        }
        guide_slugs = {
            "cashflow-spending-spike-review",
            "cashflow-fixed-cost-subscriptions",
            "cashflow-weekly-paycheck-plan",
            "cashflow-month-end-review",
            "cashflow-emergency-fund-plan",
            "cashflow-paycheck-drop-check",
        }

        self.assertEqual(6, len(CASHFLOW_ARTICLES_0053))
        self.assertEqual(legacy_slugs, {article["slug"] for article in CASHFLOW_ARTICLES_0053})
        self.assertEqual(6, len(CASHFLOW_GUIDE_ARTICLES_0055))
        self.assertEqual(guide_slugs, {article["slug"] for article in CASHFLOW_GUIDE_ARTICLES_0055})
        self.assertTrue(legacy_slugs.isdisjoint(guide_slugs))
        self.assertEqual(12, len(CASHFLOW_ARTICLES))
        self.assertEqual(
            legacy_slugs | guide_slugs,
            {article["slug"] for article in CASHFLOW_ARTICLES},
        )
        self.assertEqual(
            {
                "cashflow-internal-transfer",
                "cashflow-refund-reimbursement",
                "cashflow-screenshot-review",
                "cashflow-confirmed-budget",
            },
            set(CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055),
        )
        self.assertTrue(all(article["summary"].strip() for article in CASHFLOW_ARTICLES))
        self.assertTrue(all(article["content"].strip() for article in CASHFLOW_ARTICLES))

    def test_cashflow_articles_are_user_facing_and_actionable(self) -> None:
        articles = {article["slug"]: article for article in CASHFLOW_ARTICLES}
        expected_guidance = {
            "cashflow-internal-transfer": ["两端都是你本人的账户吗", "把手续费拆出来"],
            "cashflow-refund-reimbursement": ["实际个人承担", "报销尚未到账"],
            "cashflow-credit-card-repayment": ["还款本金", "利息与费用"],
            "cashflow-payslip-gross-net": ["工资通常每月集中到账", "实际到账"],
            "cashflow-screenshot-review": ["确认前检查五件事", "先抽样"],
            "cashflow-confirmed-budget": ["第一份预算，先分四类", "收入往往集中到账"],
            "cashflow-spending-spike-review": ["相同进度对比", "一次性大额", "频次变多"],
            "cashflow-fixed-cost-subscriptions": ["用近 12 个月找齐周期扣款", "最晚取消日"],
            "cashflow-weekly-paycheck-plan": ["每周弹性额度", "发薪周期剩余周数"],
            "cashflow-month-end-review": ["先把数字核清", "给超支分类", "1‑3 个下月动作"],
            "cashflow-emergency-fund-plan": ["最低必要支出", "应急金放在哪里"],
            "cashflow-paycheck-drop-check": ["六个优先核对项", "实发与到账"],
        }
        internal_explanations = [
            "系统怎样处理",
            "程序先按",
            "交给 AI",
            "OCR 看清",
            "切片位置",
            "可信账本",
            "识别片段",
            "算法判断",
        ]

        for slug, phrases in expected_guidance.items():
            article = articles[slug]
            visible_copy = f"{article['summary']}\n{article['content']}"
            for phrase in phrases:
                self.assertIn(phrase, visible_copy, slug)
            for phrase in internal_explanations:
                self.assertNotIn(phrase, visible_copy, slug)
            self.assertEqual("职护收支守护用户指南", article["source_title"])
            self.assertEqual("2026.8.1", article["content_version"])

        self.assertEqual(
            {article["slug"] for article in CASHFLOW_ARTICLES_0053},
            set(articles) - {article["slug"] for article in CASHFLOW_GUIDE_ARTICLES_0055},
        )
        self.assertNotEqual(
            {article["slug"]: article["content"] for article in CASHFLOW_ARTICLES_0053},
            {
                slug: article["content"]
                for slug, article in articles.items()
                if slug in {item["slug"] for item in CASHFLOW_ARTICLES_0053}
            },
        )


@mysql_test
class CashflowKnowledgeArticlesMySQLTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(MYSQL_TEST_DATABASE_URL, pool_pre_ping=True)
        KnowledgeArticle.__table__.create(self.engine, checkfirst=True)
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.db = sessionmaker(bind=self.connection, expire_on_commit=False)()
        self.addCleanup(self._cleanup)

        slugs = [article["slug"] for article in CASHFLOW_ARTICLES]
        self.db.query(KnowledgeArticle).filter(KnowledgeArticle.slug.in_(slugs)).delete(
            synchronize_session=False
        )
        for index, article in enumerate(CASHFLOW_ARTICLES):
            self.db.add(
                KnowledgeArticle(
                    slug=article["slug"],
                    title=article["title"],
                    category=article["category"],
                    tags=article["tags"],
                    keywords=article["keywords"],
                    summary=article["summary"],
                    content=article["content"].strip(),
                    applicable_issues=article["applicable_issues"],
                    applicable_regions=article["applicable_regions"],
                    source_title=article["source_title"],
                    source_url=article["source_url"],
                    content_version=article["content_version"],
                    effective_from=article["effective_from"],
                    effective_to=article["effective_to"],
                    reviewed_at=article["reviewed_at"],
                    sort_order=60 + index,
                    is_published=article["slug"] not in CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055,
                )
            )
        self.db.flush()

    def _cleanup(self) -> None:
        self.db.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()
        self.engine.dispose()

    def test_cashflow_articles_are_listed_and_can_open_in_the_article_drawer(self) -> None:
        visible = get_article_list(self.db)
        slugs = {article["slug"] for article in visible}
        expected_visible = {
            article["slug"]
            for article in CASHFLOW_ARTICLES
            if article["slug"] not in CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055
        }
        self.assertTrue(expected_visible.issubset(slugs))
        self.assertTrue(set(CASHFLOW_HIDDEN_ARTICLE_SLUGS_0055).isdisjoint(slugs))

        detail = get_article(self.db, "cashflow-weekly-paycheck-plan")
        self.assertIsNotNone(detail)
        self.assertIn("每周弹性额度", detail["content"])
        self.assertEqual("reference_only", detail["ai_citation_status"])

    def test_internal_product_articles_do_not_enter_authoritative_ai_context(self) -> None:
        context, references = recommend_cashflow_knowledge(
            self.db,
            question="银行卡转到微信为什么不算收入？",
        )

        self.assertEqual([], context)
        self.assertEqual({}, references)


if __name__ == "__main__":
    unittest.main()
