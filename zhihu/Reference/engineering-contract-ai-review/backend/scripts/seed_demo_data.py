"""
工程合同 AI 审查助手 - 演示数据种子脚本
"""

import sys
import os
from pathlib import Path
from uuid import uuid4

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from passlib.hash import bcrypt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from app.core.config import settings, settings_upload_path
from app.db.session import SessionLocal, Base
from app.models import (
    User, Role, UserRole, ReviewRule,
    ContractFile, ContractParseResult, ContractReviewResult,
    ReviewVersion, ReviewLog,
)
from app.services.contract_review_service import review_contract_parse_result


# --- Helpers ---

def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def make_pdf(filename: str, title: str, content: str) -> str:
    settings_upload_path.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid4().hex}.pdf"
    filepath = settings_upload_path / stored
    doc = SimpleDocTemplate(str(filepath), pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ContractTitle", fontSize=16, alignment=1,
        spaceAfter=12, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="ContractBody", fontSize=10, spaceAfter=6,
        leading=14, fontName="Helvetica"))
    styles.add(ParagraphStyle(name="SectionTitle", fontSize=12, spaceBefore=10,
        spaceAfter=6, fontName="Helvetica-Bold"))
    story = [Paragraph(title, styles["ContractTitle"])]
    story.append(Spacer(1, 6))
    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue
        if line.startswith("第") and "条" in line:
            story.append(Paragraph(line, styles["SectionTitle"]))
        else:
            story.append(Paragraph(line, styles["ContractBody"]))
    doc.build(story)
    return stored


CONTRACT_1_TEXT = """

合同名称：某市滨江大桥施工总承包合同
合同编号：BJ-2026-001
项目名称：某市滨江大桥工程
合同类型：施工合同
签订日期：2026年1月15日
合同金额：人民币贰仟佰万元整（￥25,000,000.00）

甲方：某市交通投资建设集团有限公司
乙方：中建第五工程局有限公司

一、工程概况
本工程位于某市滨江新区，全长3.2公里，包含主桥及引桥施工。

二、工作内容
详见附件工程量清单及施工图纸。乙方须按照甲方要求完成全部施工任务。

三、工期
总工期为360日历天。工期不得顺延，每延误一日，乙方须向甲方支付合同总价万分之五的违约金，且自行承担起工费用。

四、付款方式
本工稌无预付款。工程进度款按月支付，甲方审核后三十日内支付。工程竣工后全部结清，竣工验收合格后支付至97%。

五、质保金
本工稌质保金为结算总价的3%，质保期自竣工验收合格之日起24个月。质保期满后经甲方验收合格后无息返还。

六、变更与签证
工稌变更须经甲方书面确认，签证程序详见附件。

七、发票与税务
乙方须按甲方要求提供增值税专用发票。

八、违约责任
乙方逾期交付的，甲方有权按日收取违约金。因乙方原因造成工程质量不合格的，乙方承担全部责任。

九、争议解决
因本合同引起的争议，提交甲方所在地人民法院管辖。

十、合同解除
甲方有权在乙方严重违约时单方解除合同，解除后已完成工程量由甲方审定后结算。
"""

CONTRACT_2_TEXT = """

合同名称：城南片区市政道路工程分包合同
合同编号：CN-2026-002
项目名称：城南片区市政道路工程
合同类型：分包合同
签订日期：2026年2月20日
合同金额：人民币捷佰万元整（￥8,000,000.00）

甲方：中建第三工程局有限公司
乙方：某省路桥工程有限公司

一、工程概况
本工程为城南片区市政道路工程，包含道路工程、排水工程、照明工程等。

二、工作内容
承包范围：K0+000至K3+500段道路及附属工程。

三、工期
总工期180日历天。因不可抗力或甲方原因导致延误的，工期可相应顺延。

四、付款方式
预付款为合同总价的10%，按月进度支付工程款。最终结算以双方协商为准。

五、质保金
工稌质保金为2%，质保期12个月。

六、违约责任
双方应严格按合同约定履行义务。任何一方违约的，应承担相应的违约责任。

九、争议解决
争议应优先协商解决。

十、合同解除
任何一方严重违约的，守约方有权书面通知后解除合同。
"""

CONTRACT_3_TEXT = """

合同名称：高新区智能制造基地建设工程施工合同
合同编号：GQ-2026-003
项目名称：高新区智能制造基地建设工程
合同类型：施工合同
签订日期：2026年3月10日
合同金额：人民币壹亿贰仟万元整（￥120,000,000.00）

甲方：高新区科技产业发展有限公司
乙方：中铁建工集团有限公司

一、工程概况
本工程位于高新区创新产业园，总建笑面积85,000平方米。

二、工作内容
乙方负责施工图纸范围内全部土建、安装及装饰装修工程。

三、工期
总工期540日历天。

四、付款方式
预付款为合同总价的15%，按工程节点支付。

五、质保金
质保金为结算总价的3%，质保期24个月。

八、违约责任
双方违约责任对等。

十、合同解除
合同解除须满足以下条件：一方严重违约经书面催告后30日内仍未纠正的。
"""

CONTRACTS = [
    {
        "filename": "某市滨江大桥施工总承包合同.pdf",
        "title": "某市滨江大桥施工总承包合同",
        "content": CONTRACT_1_TEXT,
        "category": "施工合同",
        "tags": ["重点项目", "桥梁工程"],
        "owner_id": 1,
    },
    {
        "filename": "城南片区市政道路工程分包合同.pdf",
        "title": "城南片区市政道路工程分包合同",
        "content": CONTRACT_2_TEXT,
        "category": "分包合同",
        "tags": ["市政道路", "城南片区"],
        "owner_id": 1,
    },
    {
        "filename": "高新区智能制造基地建设工程施工合同.pdf",
        "title": "高新区智能制造基地建设工程施工合同",
        "content": CONTRACT_3_TEXT,
        "category": "施工合同",
        "tags": ["智能制造", "高新区"],
        "owner_id": 1,
    },
]

SAMPLE_RULES = [
    {
        "name": "付款条款风险",
        "rule_code": "payment_terms_risk",
        "risk_type": "付款条件偏严",
        "condition_type": "contains_any",
        "condition_value": "[\"结清\",\"无预付款\"]",
        "risk_level": "high",
        "suggestion": "补充预付款",
        "priority": 10,
        "contract_type_scope": None,
    },
    {
        "name": "工期责任风险",
        "rule_code": "schedule_liability_risk",
        "risk_type": "工期责任偏重",
        "condition_type": "keyword",
        "condition_value": "每延误一日",
        "risk_level": "high",
        "suggestion": "增加顺延条件",
        "priority": 15,
        "contract_type_scope": None,
    },
    {
        "name": "质保金风险",
        "rule_code": "retention_money_risk",
        "risk_type": "质保金返还条件不明",
        "condition_type": "keyword",
        "condition_value": "质保金",
        "risk_level": "medium",
        "suggestion": "明确质保金比例",
        "priority": 25,
        "contract_type_scope": None,
    },
]


def seed_sample_data():
    db = SessionLocal()
    try:
        print("=== Starting seed ===")
        print()

        # 1. Create sample users with idempotency
        print("[1/8] Creating sample users...")
        sample_users = [
            ("zhang_reviewer", "Reviewer123", "reviewer"),
            ("li_viewer", "Viewer12345", "viewer"),
        ]
        for username, password, role_code in sample_users:
            existing = db.query(User).filter_by(username=username).first()
            if existing:
                print(f"  User {username} exists, skipping")
                continue
            user = User(username=username, password_hash=hash_password(password), is_active=True)
            db.add(user)
            db.flush()
            role = db.query(Role).filter_by(code=role_code).first()
            if role:
                db.add(UserRole(user_id=user.id, role_id=role.id))
            print(f"  Created user {username} ({role_code})")
        db.commit()
        admin = db.query(User).filter_by(username="admin").first()
        admin_id = admin.id if admin else None
        print()

        # 2. Create sample rules with idempotency
        print("[2/8] Creating sample rules...")
        for rule_data in SAMPLE_RULES:
            existing = db.query(ReviewRule).filter_by(rule_code=rule_data["rule_code"]).first()
            if existing:
                print(f"  Rule exists, skipping")
                continue
            rule = ReviewRule(**rule_data, is_active=True, created_by=admin_id)
            db.add(rule)
            db.flush()
            print(f"  Created rule")
        db.commit()
        print()

        # 3. Generate PDFs and create contracts
        print("[3/8] Creating sample contracts...")
        contract_files = []
        for i, c in enumerate(CONTRACTS):
            existing = db.query(ContractFile).filter_by(original_filename=c["filename"]).first()
            if existing:
                print(f"  Contract exists, skipping")
                contract_files.append(existing)
                continue
            stored_filename = make_pdf(c["filename"], c["title"], c["content"])
            file_path = settings_upload_path / stored_filename
            file_bytes = file_path.read_bytes()
            contract_file = ContractFile(
                original_filename=c["filename"],
                stored_filename=stored_filename,
                file_path=str(file_path),
                content_type="application/pdf",
                file_size=len(file_bytes),
                owner_id=c["owner_id"],
                category=c["category"],
                tags=c["tags"],
                status="uploaded",
                updated_by=c["owner_id"],
            )
            db.add(contract_file)
            db.flush()
            if contract_file.version_root_id is None:
                contract_file.version_root_id = contract_file.id
                db.flush()
            parse_result = ContractParseResult(
                contract_file_id=contract_file.id,
                page_count=1,
                parse_status="completed",
                parse_mode="text",
                raw_text=c["content"],
            )
            db.add(parse_result)
            contract_files.append(contract_file)
            print(f"  Created contract")
        db.commit()
        print()

        # 4. Run initial reviews
        print("[4/8] Running initial reviews...")
        for cf in contract_files:
            existing_result = db.query(ContractReviewResult).filter_by(contract_file_id=cf.id).first()
            if existing_result:
                continue
            try:
                review_contract_parse_result(db, cf.id, actor=admin, trigger_source="seed")
            except Exception as e:
                print(f"  Review failed: {e}")
        db.commit()
        print()

        # 5. Re-review first contract for version history
        print("[5/8] Creating version history...")
        if contract_files:
            first_cf = contract_files[0]
            try:
                review_contract_parse_result(db, first_cf.id, actor=admin, trigger_source="re-review")
            except Exception as e:
                print(f"  Re-review failed: {e}")
            db.commit()
        print()

        # 6. Upload V2 of first contract
        print("[6/8] Uploading contract V2...")
        if contract_files:
            first_cf = contract_files[0]
            v2_filename = first_cf.original_filename.replace(".pdf", "_v2.pdf")
            existing_v2 = db.query(ContractFile).filter_by(original_filename=v2_filename).first()
            if existing_v2:
                print(f"  V2 exists, skipping")
            else:
                v2_text = CONTRACTS[0]["content"] + "\n\n(supplementary: safety clauses)"
                stored_v2 = make_pdf(v2_filename, CONTRACTS[0]["title"] + " (v2)", v2_text)
                fp = settings_upload_path / stored_v2
                fb = fp.read_bytes()
                cf2 = ContractFile(
                    original_filename=v2_filename,
                    stored_filename=stored_v2,
                    file_path=str(fp),
                    content_type="application/pdf",
                    file_size=len(fb),
                    owner_id=CONTRACTS[0]["owner_id"],
                    category=CONTRACTS[0]["category"],
                    tags=CONTRACTS[0]["tags"],
                    status="uploaded",
                    updated_by=CONTRACTS[0]["owner_id"],
                    version_root_id=first_cf.version_root_id or first_cf.id,
                    upload_version_no=2,
                )
                db.add(cf2)
                db.flush()
                pr2 = ContractParseResult(
                    contract_file_id=cf2.id,
                    page_count=1,
                    parse_status="completed",
                    parse_mode="text",
                    raw_text=v2_text,
                )
                db.add(pr2)
                db.commit()
                try:
                    review_contract_parse_result(db, cf2.id, actor=admin, trigger_source="seed")
                except Exception as e:
                    print(f"  V2 review failed: {e}")
                db.commit()
        print()

        # 7. Complete operation logs
        print("[7/8] Writing operation logs...")
        log_entries = [
            ("system_setting", None, "update_system", "Switch review mode to mock"),
            ("system_setting", None, "update_system", "Set OCR language"),
            ("user", None, "create_sample_user", "Create sample user zhang_reviewer"),
            ("user", None, "create_sample_user", "Create sample user li_viewer"),
            ("review_version", None, "create_version", "Re-review contract for V2"),
        ]
        for target_type, target_id, action_type, detail in log_entries:
            existing_log = db.query(ReviewLog).filter_by(action_detail=detail).first()
            if existing_log:
                continue
            db.add(ReviewLog(
                operator_id=admin_id,
                target_type=target_type,
                target_id=target_id,
                action_type=action_type,
                action_detail=detail,
            ))
        db.commit()
        print("  Written")
        print()

        # 8. Summary
        print("[8/8] Seed complete")
        print(f"  Users: {db.query(User).count()}")
        print(f"  Rules: {db.query(ReviewRule).filter_by(is_deleted=False).count()}")
        print(f"  Contracts: {db.query(ContractFile).count()}")
        print(f"  Review versions: {db.query(ReviewVersion).count()}")
        print(f"  Operation logs: {db.query(ReviewLog).count()}")
        print(f"  Sample: zhang_reviewer/Reviewer123, li_viewer/Viewer12345")
        print(f"  Admin: admin/Admin123456")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    seed_sample_data()
