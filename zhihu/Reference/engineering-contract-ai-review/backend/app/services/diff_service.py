"""Contract Diff Service

LCS-based line-level text diff."""


from __future__ import annotations


from dataclasses import dataclass, field




@dataclass
class DiffLine:
    content: str
    status: str
    source_line_no: int | None = None
    target_line_no: int | None = None




@dataclass
class TextDiffResult:
    lines: list[DiffLine] = field(default_factory=list)
    added_count: int = 0
    removed_count: int = 0
    unchanged_count: int = 0
    similarity_ratio: float = 0.0




@dataclass
class FieldChange:
    field: str
    label: str
    before_value: str
    after_value: str




@dataclass
class RiskChange:
    code: str
    title: str
    level: str
    change_type: str
    before_level: str | None = None
    after_level: str | None = None




@dataclass
class ContractDiffResult:
    text_diff: TextDiffResult
    field_changes: list[FieldChange]
    risk_changes: list[RiskChange]
    base_version_no: int
    target_version_no: int




def _tokenize_text(text: str) -> list[str]:
    if not text:
        return []
    lines = text.split(chr(10))
    return [line.strip() for line in lines if line.strip()]




class DiffService:
    FIELD_LABELS: dict[str, str] = {
        "contract_name": "\u5408\u540c\u540d\u79f0",
        "contract_number": "\u5408\u540c\u7f16\u53f7",
        "project_name": "\u9879\u76ee\u540d\u79f0",
        "party_a": "\u7532\u65b9",
        "party_b": "\u4e59\u65b9",
        "contract_type": "\u5408\u540c\u7c7b\u578b",
        "sign_date": "\u7b7e\u8ba2\u65e5\u671f",
        "contract_amount": "\u5408\u540c\u91d1\u989d",
        "construction_period": "\u5de5\u671f",
        "payment_terms": "\u4ed8\u6b3e\u6761\u6b3e",
        "warranty_period": "\u8d28\u4fdd\u671f",
        "dispute_resolution": "\u4e89\u8bae\u89e3\u51b3",
        "breach_liability": "\u8fdd\u7ea6\u8d23\u4efb",
    }

    @classmethod
    def compute_text_diff(cls, before_text: str, after_text: str) -> TextDiffResult:
        lines_a = _tokenize_text(before_text)
        lines_b = _tokenize_text(after_text)
        if not lines_a and not lines_b:
            return TextDiffResult(similarity_ratio=1.0)
        m, n = len(lines_a), len(lines_b)
        matrix = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if lines_a[i - 1] == lines_b[j - 1]:
                    matrix[i][j] = matrix[i - 1][j - 1] + 1
                else:
                    matrix[i][j] = max(matrix[i - 1][j], matrix[i][j - 1])
        diff_lines: list[DiffLine] = []
        added_count = 0
        removed_count = 0
        unchanged_count = 0
        i, j = m, n
        while i > 0 or j > 0:
            if i > 0 and j > 0 and lines_a[i - 1] == lines_b[j - 1]:
                diff_lines.append(DiffLine(content=lines_a[i - 1], status="unchanged", source_line_no=i, target_line_no=j))
                unchanged_count += 1
                i -= 1
                j -= 1
            elif j > 0 and (i == 0 or matrix[i][j - 1] >= matrix[i - 1][j]):
                diff_lines.append(DiffLine(content=lines_b[j - 1], status="added", target_line_no=j))
                added_count += 1
                j -= 1
            else:
                diff_lines.append(DiffLine(content=lines_a[i - 1], status="removed", source_line_no=i))
                removed_count += 1
                i -= 1
        diff_lines.reverse()
        total_lines = max(len(lines_a), len(lines_b), 1)
        similarity = unchanged_count / total_lines if total_lines > 0 else 1.0
        return TextDiffResult(lines=diff_lines, added_count=added_count, removed_count=removed_count, unchanged_count=unchanged_count, similarity_ratio=round(similarity, 4))

    @classmethod
    def compute_field_changes(cls, before_fields: dict, after_fields: dict) -> list[FieldChange]:
        changes: list[FieldChange] = []
        all_keys = set(before_fields.keys()) | set(after_fields.keys())
        for key in sorted(all_keys):
            if key not in cls.FIELD_LABELS:
                continue
            before_val = str(before_fields.get(key) or "-")
            after_val = str(after_fields.get(key) or "-")
            if before_val == after_val:
                continue
            changes.append(FieldChange(field=key, label=cls.FIELD_LABELS[key], before_value=before_val, after_value=after_val))
        return changes


    @classmethod
    def compute_risk_changes(cls, before_risks: list[dict], after_risks: list[dict]) -> list[RiskChange]:
        changes: list[RiskChange] = []
        before_map = {r.get("code", ""): r for r in before_risks if r.get("code")}
        after_map = {r.get("code", ""): r for r in after_risks if r.get("code")}
        all_codes = set(before_map.keys()) | set(after_map.keys())
        for code in sorted(all_codes):
            in_before = code in before_map
            in_after = code in after_map
            if in_before and not in_after:
                changes.append(RiskChange(code=code, title=before_map[code].get("title", code), level=before_map[code].get("level", "unknown"), change_type="removed"))
            elif not in_before and in_after:
                changes.append(RiskChange(code=code, title=after_map[code].get("title", code), level=after_map[code].get("level", "unknown"), change_type="added"))
            else:
                before_level = before_map[code].get("level", "")
                after_level = after_map[code].get("level", "")
                if before_level != after_level:
                    changes.append(RiskChange(code=code, title=after_map[code].get("title", code), level=after_level, change_type="level_changed", before_level=before_level, after_level=after_level))
        return changes


    @classmethod
    def compute_contract_diff(cls, before_text: str, after_text: str, before_fields: dict, after_fields: dict, before_risks: list[dict], after_risks: list[dict], base_version_no: int, target_version_no: int) -> ContractDiffResult:
        return ContractDiffResult(
            text_diff=cls.compute_text_diff(before_text, after_text),
            field_changes=cls.compute_field_changes(before_fields, after_fields),
            risk_changes=cls.compute_risk_changes(before_risks, after_risks),
            base_version_no=base_version_no,
            target_version_no=target_version_no,
        )

