#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
from pathlib import Path
import shutil
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from market_data.adapters.company_channel import validate_compat_parser_source
from market_data.school_channel_catalog import ASSET_ROOT, CATALOG_PATH


PUBLIC_FIELDS = {
    "clawler_type",
    "click_type",
    "detail_hd_ann_full",
    "detail_hd_company",
    "detail_hd_company_full",
    "detail_iframe",
    "detail_rm_classes",
    "detail_rm_ids",
    "detail_rm_oth_classes",
    "detail_selector",
    "detail_selectors",
    "detail_tuning_classes",
    "detail_tuning_classes_full",
    "fix_hd_company",
    "func_name",
    "html_to_markdown",
    "index_url_func",
    "index_url_selector",
    "json_domain",
    "pre_open_url",
    "redirect_url",
    "sch_name",
    "sch_webname",
    "search_wx_file",
    "status",
    "table_func_name",
    "table_selector",
    "table_selectors",
    "template",
    "text_to_markdown",
    "urls",
    "use_bs4",
}

# These original crawler hooks need imperative browser/API behavior that the
# declarative Career Guardian adapter intentionally does not execute yet.
UNSUPPORTED_ACTION_FIELDS = {
    "clawler_type",
    "click_type",
    "index_url_func",
    "pre_open_url",
    "redirect_url",
    "search_wx_file",
    "table_func_name",
    "use_bs4",
}


def _read_config(paths: list[Path]) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    loaded = parser.read(paths, encoding="utf-8")
    if len(loaded) != len(paths):
        missing = sorted(str(path) for path in paths if str(path) not in loaded)
        raise RuntimeError(f"Unable to read crawler configuration: {missing}")
    return parser


def _json_option(parser: configparser.ConfigParser, section: str, key: str) -> object:
    try:
        return json.loads(parser.get(section, key))
    except (configparser.Error, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid JSON in [{section}] {key}") from exc


def build_catalog(source_root: Path, output_root: Path = ASSET_ROOT) -> dict:
    source_root = source_root.resolve()
    data_root = source_root / "data"
    parser_root = source_root / "auto_gen" / "gen"
    school_files = sorted(data_root.glob("setting_sch_*.ini"))
    if not school_files:
        raise RuntimeError("No setting_sch_*.ini files were found")

    # Reading all files into one ConfigParser deliberately matches the original
    # crawler's last-definition-wins behavior for duplicate school codes.
    school_config = _read_config(school_files)
    template_config = _read_config(
        [data_root / "setting_default.ini", data_root / "setting_template.ini"]
    )

    schools: list[dict] = []
    parser_names: set[str] = set()
    for school_code, raw_value in school_config.items("School"):
        try:
            rows = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid school definition: {school_code}") from exc
        if not isinstance(rows, list):
            raise RuntimeError(f"School definition must be a list: {school_code}")
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            template_name = str(row.get("template") or "").strip()
            template = (
                _json_option(template_config, "Template", template_name)
                if template_name
                else {}
            )
            if not isinstance(template, dict):
                raise RuntimeError(f"Template must be an object: {template_name}")
            merged = {**template, **row}
            public = {
                key: value
                for key, value in merged.items()
                if key in PUBLIC_FIELDS and value not in (None, "", [], {})
            }
            parser_name = str(public.get("func_name") or "").strip()
            if parser_name:
                parser_names.add(parser_name)
            unsupported = sorted(
                field
                for field in UNSUPPORTED_ACTION_FIELDS
                if public.get(field) not in (None, "", False, [], {})
            )
            effective_code = school_code if row_index == 0 else f"{school_code}_{row_index + 1}"
            schools.append(
                {
                    "school_code": effective_code,
                    "legacy_school_code": school_code,
                    "school_name": str(public.get("sch_name") or "").strip(),
                    "school_webname": str(public.get("sch_webname") or "").strip(),
                    "configuration": public,
                    "compatibility": {
                        "declarative_supported": not unsupported,
                        "unsupported_action_fields": unsupported,
                    },
                }
            )

    parser_output = output_root / "compat_parsers"
    parser_output.mkdir(parents=True, exist_ok=True)
    for parser_name in sorted(parser_names):
        source_path = parser_root / f"{parser_name}.py"
        if not source_path.is_file():
            raise RuntimeError(f"Referenced parser is missing: {parser_name}")
        validate_compat_parser_source(source_path)
        shutil.copyfile(source_path, parser_output / source_path.name)

    payload = {
        "schema_version": "career-guardian-school-channels-v1",
        "source": {
            "project": "qzclawler",
            "config_files": [path.name for path in school_files],
            "import_policy": "public-rules-only-no-secrets-no-runtime-dependency",
        },
        "schools": schools,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / CATALOG_PATH.name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "schools": len(schools),
        "sources": sum(
            len((school.get("configuration") or {}).get("urls") or {})
            for school in schools
        ),
        "parsers": len(parser_names),
        "needs_review": sum(
            not (school.get("compatibility") or {}).get("declarative_supported", False)
            for school in schools
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the self-contained Career Guardian school-channel catalog"
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ASSET_ROOT)
    args = parser.parse_args()
    result = build_catalog(args.source_root, args.output_root)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
