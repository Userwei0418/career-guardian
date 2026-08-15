"""工资条 API"""
from fastapi import APIRouter, Depends
from app.api.deps import get_current_user
from app.models.user import User
from app.services.payslip_service import analyze_payslip
from app.schemas.payslip import PayslipAnalyzeRequest, PayslipAnalyzeResponse

router = APIRouter()


@router.post("/analyze", response_model=PayslipAnalyzeResponse)
def analyze(
    data: PayslipAnalyzeRequest,
    user: User = Depends(get_current_user),
):
    result = analyze_payslip(data.payslip, data.expected_salary, data.city)
    return result
