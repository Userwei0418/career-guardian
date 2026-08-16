from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.routes import auth, profiles, cases, offers, offer_comparisons, contracts, findings, journey, health, documents, reports, payslips, finance, knowledge, salary_calcs, review_rules, events, guardian, market, market_admin, resumes, opportunity_guard, opportunity_targets, mock_interviews, ai_admin, attachments

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
    }.get(status_code, "request_error")


@app.exception_handler(HTTPException)
async def http_error_handler(_request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": _error_code(exc.status_code),
                "message": message,
                "status": exc.status_code,
            }
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    fields = []
    for error in exc.errors():
        safe_error = dict(error)
        location = [str(item).lower() for item in safe_error.get("loc", ())]
        if any(any(token in part for token in ("password", "api_key", "secret", "token")) for part in location):
            safe_error.pop("input", None)
            safe_error.pop("ctx", None)
        fields.append(safe_error)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "请求数据不符合要求",
                "status": 422,
                "fields": fields,
            }
        },
    )

app.include_router(health.router, prefix="/api", tags=["健康检查"])
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(profiles.router, prefix="/api/profiles", tags=["用户档案"])
app.include_router(cases.router, prefix="/api/cases", tags=["职场任务"])
app.include_router(offers.router, prefix="/api/offers", tags=["Offer"])
app.include_router(offer_comparisons.router, prefix="/api/offer-comparisons", tags=["Offer 对比"])
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
app.include_router(events.router, prefix="/api/events", tags=["职业事件"])
app.include_router(guardian.router, prefix="/api/guardian", tags=["守护状态"])
app.include_router(market.router, prefix="/api/market", tags=["市场洞察"])
app.include_router(market_admin.router, prefix="/api/admin/market", tags=["市场采集管理"])
app.include_router(resumes.router, prefix="/api/resumes", tags=["简历版本"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["个人附件版本"])
app.include_router(opportunity_guard.router, prefix="/api/opportunity", tags=["机会守护分析"])
app.include_router(opportunity_targets.router, prefix="/api/opportunity", tags=["目标岗位"])
app.include_router(mock_interviews.router, prefix="/api/opportunity", tags=["模拟面试"])
app.include_router(ai_admin.router, prefix="/api/admin/ai", tags=["AI 配置管理"])
