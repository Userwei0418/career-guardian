from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import auth, profiles, cases, offers, contracts, findings, journey, health, documents, reports, payslips, finance, knowledge, salary_calcs, review_rules

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["健康检查"])
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(profiles.router, prefix="/api/profiles", tags=["用户档案"])
app.include_router(cases.router, prefix="/api/cases", tags=["职场任务"])
app.include_router(offers.router, prefix="/api/offers", tags=["Offer"])
app.include_router(contracts.router, prefix="/api/contracts", tags=["合同"])
app.include_router(findings.router, prefix="/api/findings", tags=["分析结论"])
app.include_router(journey.router, prefix="/api/journey", tags=["旅程"])
app.include_router(documents.router, prefix="/api/documents", tags=["文档上传与抽取"])
app.include_router(reports.router, prefix="/api/reports", tags=["分析报告"])
app.include_router(payslips.router, prefix="/api/payslips", tags=["工资条"])
app.include_router(finance.router, prefix="/api/finance", tags=["财务规划"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识学堂"])
app.include_router(salary_calcs.router, prefix="/api/salary-calcs", tags=["薪资计算记录"])
app.include_router(review_rules.router, prefix="/api", tags=["审查规则管理"])
