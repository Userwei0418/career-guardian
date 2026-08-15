#!/usr/bin/env python3
"""Read-only streaming audit for a Pin mysqldump.

The script never connects to MySQL and never prints source rows. It emits only
aggregate JSON suitable for the FP-02 historical-data quality report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


INSERT_PREFIX = re.compile(r"INSERT INTO `([^`]+)` VALUES ")
CREATE_TABLE = re.compile(
    r"CREATE TABLE `(?P<table>[^`]+)` \((?P<body>.*?)\) ENGINE=", re.DOTALL | re.IGNORECASE
)
COLUMN = re.compile(r"^\s*`([^`]+)`\s+", re.MULTILINE)


def load_columns(schema_path: Path) -> dict[str, list[str]]:
    text = schema_path.read_text(encoding="utf-8-sig")
    return {
        match.group("table"): COLUMN.findall(match.group("body"))
        for match in CREATE_TABLE.finditer(text)
    }


def decode_mysql_string(token: str) -> str:
    if len(token) < 2 or token[0] != "'" or token[-1] != "'":
        return token
    replacements = {
        "0": "\0",
        "b": "\b",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "Z": "\x1a",
        "'": "'",
        '"': '"',
        "\\": "\\",
    }
    output: list[str] = []
    escaped = False
    for char in token[1:-1]:
        if escaped:
            output.append(replacements.get(char, char))
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            output.append(char)
    if escaped:
        output.append("\\")
    return "".join(output)


def decode_value(token: str):
    token = token.strip()
    if token.upper() == "NULL":
        return None
    if token.startswith("'"):
        return decode_mysql_string(token)
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError:
            return token


class DumpInsertParser:
    def __init__(self, on_row: Callable[[str, list], None]):
        self.on_row = on_row
        self.mode = "search"
        self.search_buffer = ""
        self.table = ""
        self.in_tuple = False
        self.in_string = False
        self.escaped = False
        self.field_buffer: list[str] = []
        self.fields: list = []

    def feed(self, text: str) -> None:
        pending = text
        while pending:
            if self.mode == "search":
                self.search_buffer += pending
                match = INSERT_PREFIX.search(self.search_buffer)
                if match is None:
                    self.search_buffer = self.search_buffer[-128:]
                    return
                self.table = match.group(1)
                pending = self.search_buffer[match.end() :]
                self.search_buffer = ""
                self.mode = "values"
            else:
                pending = self._feed_values(pending)

    def _feed_values(self, text: str) -> str:
        for index, char in enumerate(text):
            if not self.in_tuple:
                if char == "(":
                    self.in_tuple = True
                    self.fields = []
                    self.field_buffer = []
                elif char == ";":
                    self.mode = "search"
                    self.table = ""
                    return text[index + 1 :]
                continue

            self.field_buffer.append(char)
            if self.in_string:
                if self.escaped:
                    self.escaped = False
                elif char == "\\":
                    self.escaped = True
                elif char == "'":
                    self.in_string = False
                continue
            if char == "'":
                self.in_string = True
            elif char == ",":
                token = "".join(self.field_buffer[:-1])
                self.fields.append(decode_value(token))
                self.field_buffer = []
            elif char == ")":
                token = "".join(self.field_buffer[:-1])
                self.fields.append(decode_value(token))
                self.on_row(self.table, self.fields)
                self.in_tuple = False
                self.fields = []
                self.field_buffer = []
        return ""


class DumpSchemaParser:
    """Captures only CREATE TABLE column names; row content is discarded."""

    def __init__(self, columns: dict[str, list[str]]):
        self.columns = columns
        self.buffer = ""

    def feed(self, text: str) -> None:
        self.buffer += text
        while True:
            match = CREATE_TABLE.search(self.buffer)
            if match is not None:
                self.columns[match.group("table")] = COLUMN.findall(match.group("body"))
                self.buffer = self.buffer[match.end() :]
                continue
            marker = self.buffer.rfind("CREATE TABLE `")
            if marker >= 0:
                self.buffer = self.buffer[marker:]
            else:
                self.buffer = self.buffer[-128:]
            return


def parse_time(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class QualityAudit:
    TRACKED_NULLS = {
        "jobs": [
            "normalized_title",
            "city",
            "salary_min",
            "salary_max",
            "job_description",
            "published_at",
            "first_seen_at",
            "last_seen_at",
            "dedupe_key",
            "source_site",
            "source_job_id",
            "apply_url",
            "detail_url",
        ],
        "raw_job_records": [
            "source_url",
            "source_job_id",
            "content_hash",
            "raw_title",
            "raw_text",
            "raw_html",
            "raw_json",
        ],
        "job_sources": ["source_job_id", "source_url", "published_at", "last_seen_at"],
        "companies": ["website_url", "career_page_url", "industry", "description"],
    }

    def __init__(self, columns: dict[str, list[str]], reference_time: datetime):
        self.columns = columns
        self.reference_time = reference_time.replace(tzinfo=None)
        self.row_counts: Counter[str] = Counter()
        self.column_mismatches: Counter[str] = Counter()
        self.null_counts: dict[str, Counter[str]] = defaultdict(Counter)
        self.distributions: dict[str, Counter[str]] = defaultdict(Counter)
        self.date_ranges: dict[str, dict[str, datetime]] = defaultdict(dict)
        self.seen_keys: dict[str, set] = defaultdict(set)
        self.duplicate_counts: Counter[str] = Counter()
        self.anomalies: Counter[str] = Counter()

    def on_row(self, table: str, values: list) -> None:
        self.row_counts[table] += 1
        names = self.columns.get(table)
        if not names or len(names) != len(values):
            self.column_mismatches[table] += 1
            return
        if table not in {"jobs", "raw_job_records", "job_sources", "companies", "crawl_tasks"}:
            return
        row = dict(zip(names, values))
        for field in self.TRACKED_NULLS.get(table, []):
            if row.get(field) in (None, ""):
                self.null_counts[table][field] += 1
        self._track_table(table, row)

    def _track_table(self, table: str, row: dict) -> None:
        if table == "jobs":
            self._distribution("jobs.source_site", row.get("source_site"))
            self._distribution("jobs.status", row.get("status"))
            self._range("jobs.published_at", row.get("published_at"))
            self._range("jobs.first_seen_at", row.get("first_seen_at"))
            self._range("jobs.last_seen_at", row.get("last_seen_at"))
            self._duplicate("jobs.dedupe_key", row.get("dedupe_key"))
            self._duplicate("jobs.apply_url", row.get("apply_url"))
            self._duplicate("jobs.detail_url", row.get("detail_url"))
            if row.get("company_id") and row.get("title"):
                self._duplicate(
                    "jobs.company_id+title+city",
                    (row["company_id"], row["title"], row.get("city")),
                )
            if row.get("source_site") and row.get("source_job_id"):
                self._duplicate(
                    "jobs.source_site+source_job_id",
                    (row["source_site"], row["source_job_id"]),
                )
            salary_min, salary_max = row.get("salary_min"), row.get("salary_max")
            if isinstance(salary_min, (int, float)) and isinstance(salary_max, (int, float)):
                if salary_min < 0 or salary_max < 0:
                    self.anomalies["jobs.negative_salary"] += 1
                if salary_min > salary_max:
                    self.anomalies["jobs.salary_min_gt_max"] += 1
                if salary_max > 1_000_000:
                    self.anomalies["jobs.salary_max_gt_1000000"] += 1
        elif table == "raw_job_records":
            self._distribution("raw_job_records.source_site", row.get("source_site"))
            self._distribution("raw_job_records.parse_status", row.get("parse_status"))
            self._range("raw_job_records.fetch_time", row.get("fetch_time"))
            self._duplicate("raw_job_records.content_hash", row.get("content_hash"))
            self._duplicate("raw_job_records.source_url", row.get("source_url"))
        elif table == "job_sources":
            self._distribution("job_sources.source_site", row.get("source_site"))
            self._range("job_sources.last_seen_at", row.get("last_seen_at"))
            self._duplicate("job_sources.source_url", row.get("source_url"))
            if row.get("source_site") and row.get("source_job_id"):
                self._duplicate(
                    "job_sources.source_site+source_job_id",
                    (row["source_site"], row["source_job_id"]),
                )
        elif table == "companies":
            self._duplicate("companies.name", row.get("name"))
            self._distribution("companies.status", row.get("status"))
        elif table == "crawl_tasks":
            self._distribution("crawl_tasks.status", row.get("status"))
            self._distribution("crawl_tasks.task_type", row.get("task_type"))
            self._range("crawl_tasks.started_at", row.get("started_at"))

    def _distribution(self, key: str, value) -> None:
        self.distributions[key][str(value) if value not in (None, "") else "<null>"] += 1

    def _range(self, key: str, value) -> None:
        parsed = parse_time(value)
        if parsed is None:
            return
        current = self.date_ranges[key]
        current["min"] = min(current.get("min", parsed), parsed)
        current["max"] = max(current.get("max", parsed), parsed)
        if parsed.replace(tzinfo=None) > self.reference_time:
            self.anomalies[f"{key}.future"] += 1

    def _duplicate(self, key: str, value) -> None:
        if value in (None, ""):
            return
        if value in self.seen_keys[key]:
            self.duplicate_counts[key] += 1
        else:
            self.seen_keys[key].add(value)

    def result(self) -> dict:
        null_rates: dict[str, dict[str, dict]] = {}
        for table, fields in self.TRACKED_NULLS.items():
            total = self.row_counts[table]
            if not total:
                continue
            counts = self.null_counts[table]
            null_rates[table] = {
                field: {
                    "count": counts[field],
                    "rate": round(counts[field] / total, 6),
                }
                for field in sorted(fields)
            }
        return {
            "table_counts": dict(sorted(self.row_counts.items())),
            "column_count_mismatches": dict(sorted(self.column_mismatches.items())),
            "null_rates": null_rates,
            "duplicate_rows_after_first": dict(sorted(self.duplicate_counts.items())),
            "date_ranges": {
                key: {name: value.isoformat(sep=" ") for name, value in bounds.items()}
                for key, bounds in sorted(self.date_ranges.items())
            },
            "distributions": {
                key: dict(counter.most_common(20))
                for key, counter in sorted(self.distributions.items())
            },
            "anomalies": dict(sorted(self.anomalies.items())),
        }


def audit_dump(dump_path: Path, schema_path: Path, reference_time: datetime) -> dict:
    columns = load_columns(schema_path)
    audit = QualityAudit(columns, reference_time)
    parser = DumpInsertParser(audit.on_row)
    schema_parser = DumpSchemaParser(columns)
    digest = hashlib.sha256()
    with dump_path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            decoded = chunk.decode("utf-8", errors="replace")
            schema_parser.feed(decoded)
            parser.feed(decoded)
    stat = dump_path.stat()
    return {
        "audit_version": "pin-backup-audit-v1",
        "mode": "read_only_streaming_no_import",
        "dump": {
            "basename": dump_path.name,
            "size_bytes": stat.st_size,
            "sha256": digest.hexdigest(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        },
        "schema_source": f"dump DDL with {schema_path.name} fallback",
        "reference_time": reference_time.isoformat(),
        **audit.result(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument(
        "--reference-time",
        type=datetime.fromisoformat,
        default=datetime.now(timezone.utc),
        help="ISO timestamp used only for future-date checks",
    )
    args = parser.parse_args()
    result = audit_dump(args.dump, args.schema, args.reference_time)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
