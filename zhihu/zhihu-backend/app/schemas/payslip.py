from pydantic import BaseModel
from typing import Optional, Any, List


class PayslipAnalyzeRequest(BaseModel):
    payslip: dict = {}
    expected_salary: Optional[float] = None
    city: str = "杭州"


class PayslipAnalyzeResponse(BaseModel):
    gross: float
    deductions: dict
    net_salary: float
    expected_net: Optional[float] = None
    diff_from_expected: Optional[float] = None
    insurance_diff: Optional[dict] = None
    findings: List[dict] = []
