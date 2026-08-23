"""版本化的中国法定节假日工作日判断。

节假日调休每年变化，因此这里不把“周一到周五”伪装成完整工作日。
只有在已收录的国务院办公厅年度通知范围内才声明日历已覆盖；
其他年份仅提供周末参考，不自动作出节假日顺延结论。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


def _date_range(start: date, end: date) -> frozenset[date]:
    return frozenset(start + timedelta(days=offset) for offset in range((end - start).days + 1))


@dataclass(frozen=True)
class ChinaWorkdayCalendar:
    version: str
    source_title: str
    source_url: str
    holidays: frozenset[date]
    adjusted_workdays: frozenset[date]


@dataclass(frozen=True)
class WorkdayEvaluation:
    value: date
    is_workday: bool
    calendar_covered: bool
    calendar_version: str | None
    source_title: str | None
    source_url: str | None


CALENDARS: dict[int, ChinaWorkdayCalendar] = {
    2025: ChinaWorkdayCalendar(
        version="cn-workday-2025-gbfmd-2024-12",
        source_title="国务院办公厅关于2025年部分节假日安排的通知",
        source_url="https://www.gov.cn/zhengce/zhengceku/202411/content_6986383.htm",
        holidays=frozenset({date(2025, 1, 1)})
        | _date_range(date(2025, 1, 28), date(2025, 2, 4))
        | _date_range(date(2025, 4, 4), date(2025, 4, 6))
        | _date_range(date(2025, 5, 1), date(2025, 5, 5))
        | _date_range(date(2025, 5, 31), date(2025, 6, 2))
        | _date_range(date(2025, 10, 1), date(2025, 10, 8)),
        adjusted_workdays=frozenset({
            date(2025, 1, 26),
            date(2025, 2, 8),
            date(2025, 4, 27),
            date(2025, 9, 28),
            date(2025, 10, 11),
        }),
    ),
    2026: ChinaWorkdayCalendar(
        version="cn-workday-2026-gbfmd-2025-7",
        source_title="国务院办公厅关于2026年部分节假日安排的通知",
        source_url="https://www.gov.cn/zhengce/content/202511/content_7047090.htm",
        holidays=_date_range(date(2026, 1, 1), date(2026, 1, 3))
        | _date_range(date(2026, 2, 15), date(2026, 2, 23))
        | _date_range(date(2026, 4, 4), date(2026, 4, 6))
        | _date_range(date(2026, 5, 1), date(2026, 5, 5))
        | _date_range(date(2026, 6, 19), date(2026, 6, 21))
        | _date_range(date(2026, 9, 25), date(2026, 9, 27))
        | _date_range(date(2026, 10, 1), date(2026, 10, 7)),
        adjusted_workdays=frozenset({
            date(2026, 1, 4),
            date(2026, 2, 14),
            date(2026, 2, 28),
            date(2026, 5, 9),
            date(2026, 9, 20),
            date(2026, 10, 10),
        }),
    ),
}


def evaluate_workday(value: date) -> WorkdayEvaluation:
    calendar = CALENDARS.get(value.year)
    if calendar is None:
        return WorkdayEvaluation(
            value=value,
            is_workday=value.weekday() < 5,
            calendar_covered=False,
            calendar_version=None,
            source_title=None,
            source_url=None,
        )
    if value in calendar.adjusted_workdays:
        is_workday = True
    elif value in calendar.holidays:
        is_workday = False
    else:
        is_workday = value.weekday() < 5
    return WorkdayEvaluation(
        value=value,
        is_workday=is_workday,
        calendar_covered=True,
        calendar_version=calendar.version,
        source_title=calendar.source_title,
        source_url=calendar.source_url,
    )


def adjacent_workday(value: date, direction: int) -> WorkdayEvaluation:
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")
    current = value
    for _ in range(31):
        current += timedelta(days=direction)
        evaluation = evaluate_workday(current)
        if evaluation.is_workday:
            return evaluation
    raise ValueError("无法在 31 天内找到工作日")
