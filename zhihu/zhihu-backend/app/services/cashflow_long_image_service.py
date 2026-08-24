from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import fitz
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cashflow_import import (
    FinancialImportBatch,
    FinancialRecognitionArtifact,
    FinancialTransactionCandidate,
)
from app.models.personal_attachment import PersonalAttachmentVersion
from app.schemas.cashflow_import import FinancialImportBatchReviewResolutionRequest
from app.services.cashflow_ai_intake_service import (
    _local_ocr,
    _program_date_from_text,
    _validate_image_dimensions,
    _validated_image_type,
    parse_ocr_text_intake_complete as parse_ocr_text_intake,
)
from app.services.cashflow_import_service import (
    ACTIONABLE_CANDIDATE_STATUSES,
    _active_sibling_fingerprint_matches,
    _candidate_validation,
    _find_possible_duplicate_fact_targets_for_candidate,
    _find_possible_duplicates_for_candidate,
    _populate_candidates,
    batch_payload,
    candidate_payloads,
    get_owned_batch,
    import_error,
    refresh_batch_counts,
)
from app.services.cashflow_import_parser import (
    ParsedCandidate,
    build_candidate_fingerprint,
    duplicate_text_is_similar,
)
from app.services.cashflow_recognition_artifact_service import (
    persist_ocr_text_artifact,
)
from app.services.cashflow_service import get_available_category, lock_financial_ledger_owner
from app.services.cashflow_privacy import redact_cashflow_text
from app.services.cashflow_tencent_ocr_service import (
    TencentOCRError,
    TencentOCRLine,
    recognize_with_tencent_cloud,
)
from app.services.personal_attachment_service import (
    resolve_attachment_path,
    save_personal_attachment,
)


LONG_IMAGE_PARSER_VERSION = "cashflow-long-image-v13"
TRANSACTION_ROW_DETECTOR_VERSION = "colored-icon-v1"
NORMALIZED_IMAGE_WIDTH = 1440
MAX_IMAGE_UPSCALE = 1.5
MIN_NORMALIZED_IMAGE_WIDTH = 960
SLICE_HEIGHT = 2400
SLICE_OVERLAP = 320
MIN_TRAILING_SLICE_HEIGHT = 640
MAX_IMAGE_SLICES = 40
MAX_SEQUENCE_IMAGES = 10
ADAPTIVE_CUT_SEARCH_RADIUS = 160
ADAPTIVE_MIN_GAP_HEIGHT = 10
ADAPTIVE_GAP_GUARD_ROWS = 3
ADAPTIVE_MIN_OVERLAP = 160
ADAPTIVE_MAX_OVERLAP = SLICE_OVERLAP + ADAPTIVE_CUT_SEARCH_RADIUS * 2

CATEGORY_REVIEW_ISSUE_CODES = {
    "CATEGORY_REVIEW_REQUIRED",
    "CATEGORY_INVALID",
    "PROGRAM_CATEGORY_REVIEW_REQUIRED",
    "AI_CATEGORY_UNAVAILABLE",
    "AI_CATEGORY_UNCERTAIN",
    "AI_CATEGORY_REVIEW_REQUIRED",
}

# A missing merchant is not a value the program or model may invent.  These
# are the only prompts an explicit batch-wide "keep unknown" acknowledgement
# is allowed to clear.  Every other issue (including duplicate, amount,
# direction and category questions) remains blocking.
UNKNOWN_MERCHANT_REVIEW_ISSUE_CODES = {
    "PROGRAM_MERCHANT_REVIEW",
    "MERCHANT_REVIEW_REQUIRED",
    # The model's generic medium-confidence reminder is redundant once the
    # deterministic row already has every accounting field and the user is
    # explicitly acknowledging that only the counterparty remains unknown.
    "AI_REVIEW_REQUIRED",
    "AI_PROGRAM_ALIGNMENT_REVIEW",
    "AI_UNRESOLVED_MANUAL_REVIEW",
}


def _line_bounds(line: TencentOCRLine) -> tuple[int, int, int, int]:
    if not line.polygon:
        return (2**30, 2**30, 2**30, 2**30)
    xs = [point["x"] for point in line.polygon]
    ys = [point["y"] for point in line.polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _combined_polygon(lines: list[TencentOCRLine]) -> list[dict[str, int]]:
    bounded = [_line_bounds(line) for line in lines if line.polygon]
    if not bounded:
        return []
    left = min(item[0] for item in bounded)
    top = min(item[1] for item in bounded)
    right = max(item[2] for item in bounded)
    bottom = max(item[3] for item in bounded)
    return [
        {"x": left, "y": top},
        {"x": right, "y": top},
        {"x": right, "y": bottom},
        {"x": left, "y": bottom},
    ]


def _layout_ordered_tencent_lines(lines: list[TencentOCRLine]) -> list[TencentOCRLine]:
    """Turn spatial wallet OCR into transaction-shaped logical lines.

    Tencent returns lines in visual top/left order.  In WeChat bills the amount
    and category share a row while the merchant is directly below it.  Feeding
    those independent lines to the generic parser makes it pair a merchant with
    the *next* amount.  Cluster by visual row, then combine a transaction header
    with its detail row so amount, direction and merchant remain one fact.
    """

    positioned = sorted(lines, key=lambda line: (_line_bounds(line)[1], _line_bounds(line)[0]))
    clusters: list[list[TencentOCRLine]] = []
    for line in positioned:
        top = _line_bounds(line)[1]
        if not clusters:
            clusters.append([line])
            continue
        previous_tops = [_line_bounds(item)[1] for item in clusters[-1]]
        if previous_tops and abs(top - round(sum(previous_tops) / len(previous_tops))) <= 22:
            clusters[-1].append(line)
        else:
            clusters.append([line])
    for cluster in clusters:
        cluster.sort(key=lambda line: _line_bounds(line)[0])

    amount_pattern = re.compile(r"^(?:入\s*)?[+\-]?\s*[¥￥]?\s*\d[\d,]*(?:\.\d{1,2})?$")
    time_pattern = re.compile(r"^(?:[01]?\d|2[0-3])[:：][0-5]\d")
    date_pattern = re.compile(r"(?:\d{1,2}\s*月\s*\d{1,2}\s*日|(?:星期|周)[一二三四五六日天])")
    logical: list[TencentOCRLine] = []
    index = 0
    while index < len(clusters):
        cluster = clusters[index]
        cluster_text = " ".join(item.text for item in cluster)
        if date_pattern.search(cluster_text):
            logical.append(TencentOCRLine(
                text=cluster_text,
                confidence=min((item.confidence for item in cluster if item.confidence is not None), default=None),
                polygon=_combined_polygon(cluster),
            ))
            index += 1
            continue
        amount_lines = [item for item in cluster if amount_pattern.fullmatch(item.text.strip())]
        label_lines = [item for item in cluster if item not in amount_lines]
        following = clusters[index + 1] if index + 1 < len(clusters) else []
        following_top = min((_line_bounds(item)[1] for item in following), default=2**30)
        cluster_bottom = max((_line_bounds(item)[3] for item in cluster), default=-1)
        detail_lines = [item for item in following if time_pattern.match(item.text.strip())]
        if amount_lines and label_lines and detail_lines and following_top - cluster_bottom <= 130:
            combined = [*label_lines, *detail_lines, *amount_lines]
            logical.append(TencentOCRLine(
                text=" ".join(item.text for item in combined),
                confidence=min((item.confidence for item in combined if item.confidence is not None), default=None),
                polygon=_combined_polygon(combined),
            ))
            index += 2
            continue
        logical.extend(cluster)
        index += 1
    return logical
MAX_SEQUENCE_TOTAL_BYTES = 90 * 1024 * 1024
MAX_SEQUENCE_TOTAL_SLICES = 80
STALE_SLICE_PROCESSING_SECONDS = 180


def _is_transaction_icon_color(red: int, green: int, blue: int) -> bool:
    """Recognize the dominant icon colors used by common wallet bill lists.

    This is deliberately narrower than general colour detection: it is only a
    coverage signal and never creates a transaction or changes an amount.
    """

    return (
        (green >= 110 and green >= red * 1.25 and green >= blue * 1.10)
        or (red >= 190 and 90 <= green <= 215 and blue <= 135 and red >= green * 1.10)
        or (blue >= 135 and blue >= red * 1.15 and blue >= green * 1.02)
    )


def _detect_transaction_rows(pixmap: fitz.Pixmap) -> dict[str, Any]:
    """Conservatively detect aligned coloured transaction icons in a slice.

    We only report an expected row count when at least two plausible, similarly
    aligned icon components are present. A single logo or coloured heading is
    therefore treated as unknown rather than as a transaction count.
    """

    unknown = {
        "version": TRANSACTION_ROW_DETECTOR_VERSION,
        "reliable": False,
        "expected_transaction_rows": None,
        "row_centers": [],
    }
    if pixmap.width < 120 or pixmap.height < 120 or pixmap.n < 3:
        return unknown

    sample_step = 2 if pixmap.width <= 1600 else 3
    scan_width = min(pixmap.width, max(80, round(pixmap.width * 0.28)))
    grid_width = (scan_width + sample_step - 1) // sample_step
    grid_height = (pixmap.height + sample_step - 1) // sample_step
    if grid_width <= 0 or grid_height <= 0:
        return unknown

    samples = memoryview(pixmap.samples)
    colored = bytearray(grid_width * grid_height)
    for grid_y, pixel_y in enumerate(range(0, pixmap.height, sample_step)):
        row_offset = pixel_y * pixmap.stride
        grid_offset = grid_y * grid_width
        for grid_x, pixel_x in enumerate(range(0, scan_width, sample_step)):
            offset = row_offset + pixel_x * pixmap.n
            if _is_transaction_icon_color(
                samples[offset],
                samples[offset + 1],
                samples[offset + 2],
            ):
                colored[grid_offset + grid_x] = 1

    visited = bytearray(len(colored))
    components: list[dict[str, float | int]] = []
    for start in range(len(colored)):
        if colored[start] == 0 or visited[start]:
            continue
        visited[start] = 1
        queue: deque[int] = deque([start])
        start_y, start_x = divmod(start, grid_width)
        min_x = max_x = start_x
        min_y = max_y = start_y
        area = 0
        while queue:
            current = queue.popleft()
            y, x = divmod(current, grid_width)
            area += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            for next_y in range(max(0, y - 1), min(grid_height, y + 2)):
                neighbor_offset = next_y * grid_width
                for next_x in range(max(0, x - 1), min(grid_width, x + 2)):
                    neighbor = neighbor_offset + next_x
                    if colored[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        queue.append(neighbor)

        component_width = (max_x - min_x + 1) * sample_step
        component_height = (max_y - min_y + 1) * sample_step
        bounding_area = (max_x - min_x + 1) * (max_y - min_y + 1)
        fill_ratio = area / bounding_area if bounding_area else 0
        minimum_size = max(14, round(pixmap.width * 0.010))
        maximum_size = min(260, round(pixmap.width * 0.18))
        aspect_ratio = component_width / component_height if component_height else 0
        touches_vertical_edge = min_y == 0 or max_y == grid_height - 1
        center_x = ((min_x + max_x + 1) * sample_step) / 2
        center_y = ((min_y + max_y + 1) * sample_step) / 2
        if (
            touches_vertical_edge
            or component_width < minimum_size
            or component_height < minimum_size
            or component_width > maximum_size
            or component_height > maximum_size
            or not 0.50 <= aspect_ratio <= 1.90
            or fill_ratio < 0.14
            or center_x > pixmap.width * 0.23
        ):
            continue
        components.append(
            {
                "center_x": center_x,
                "center_y": center_y,
                "width": component_width,
                "height": component_height,
                "area": area,
            }
        )

    if len(components) < 2:
        return unknown

    alignment_tolerance = max(18, pixmap.width * 0.025)
    clusters: list[list[dict[str, float | int]]] = []
    for component in sorted(components, key=lambda item: float(item["center_x"])):
        matching = next(
            (
                cluster
                for cluster in clusters
                if abs(
                    float(component["center_x"])
                    - sum(float(item["center_x"]) for item in cluster) / len(cluster)
                )
                <= alignment_tolerance
            ),
            None,
        )
        if matching is None:
            clusters.append([component])
        else:
            matching.append(component)
    aligned = min(
        (cluster for cluster in clusters if len(cluster) >= 2),
        key=lambda cluster: (
            -len(cluster),
            sum(float(item["center_x"]) for item in cluster) / len(cluster),
        ),
        default=None,
    )
    if aligned is None:
        return unknown

    deduplicated: list[dict[str, float | int]] = []
    for component in sorted(aligned, key=lambda item: float(item["center_y"])):
        if deduplicated:
            previous = deduplicated[-1]
            same_row_tolerance = max(
                12,
                min(float(previous["height"]), float(component["height"])) * 0.60,
            )
            if abs(float(component["center_y"]) - float(previous["center_y"])) <= same_row_tolerance:
                if int(component["area"]) > int(previous["area"]):
                    deduplicated[-1] = component
                continue
        deduplicated.append(component)
    if len(deduplicated) < 2:
        return unknown
    return {
        "version": TRANSACTION_ROW_DETECTOR_VERSION,
        "reliable": True,
        "expected_transaction_rows": len(deduplicated),
        "row_centers": [round(float(item["center_y"])) for item in deduplicated],
    }


def _detect_transaction_rows_from_png(content: bytes) -> dict[str, Any]:
    document: fitz.Document | None = None
    try:
        document = fitz.open(stream=content, filetype="png")
        pixmap = document[0].get_pixmap(colorspace=fitz.csRGB, alpha=False)
        return _detect_transaction_rows(pixmap)
    except Exception:
        return {
            "version": TRANSACTION_ROW_DETECTOR_VERSION,
            "reliable": False,
            "expected_transaction_rows": None,
            "row_centers": [],
        }
    finally:
        if document is not None:
            document.close()


def _normalization_scale(width: int, height: int) -> float:
    scale = min(NORMALIZED_IMAGE_WIDTH / width, MAX_IMAGE_UPSCALE)
    adaptively_reduced = False
    maximum_normalized_height = SLICE_HEIGHT + (MAX_IMAGE_SLICES - 1) * (
        SLICE_HEIGHT - SLICE_OVERLAP
    )
    if round(height * scale) > maximum_normalized_height:
        scale = maximum_normalized_height / height
        adaptively_reduced = True
    if adaptively_reduced and width * scale < MIN_NORMALIZED_IMAGE_WIDTH:
        raise import_error(
            413,
            "cashflow_vision_too_tall_for_readable_slices",
            "截图过长，继续缩小会影响识别准确率；请把它分成两张连续截图，系统会自动处理交界重复记录",
        )
    return scale


def should_use_segmented_ocr(dimensions: tuple[int, int]) -> bool:
    width, height = dimensions
    scale = _normalization_scale(width, height)
    return round(height * scale) > SLICE_HEIGHT


def _slice_ranges(normalized_height: int) -> list[tuple[int, int]]:
    if normalized_height <= SLICE_HEIGHT:
        return [(0, normalized_height)]
    step = SLICE_HEIGHT - SLICE_OVERLAP
    starts = list(range(0, normalized_height, step))
    if normalized_height - starts[-1] < MIN_TRAILING_SLICE_HEIGHT:
        starts[-1] = max(0, normalized_height - SLICE_HEIGHT)
    starts = list(dict.fromkeys(starts))
    ranges = [(start, min(normalized_height, start + SLICE_HEIGHT)) for start in starts]
    if len(ranges) > MAX_IMAGE_SLICES:
        raise import_error(
            413,
            "cashflow_vision_too_many_slices",
            f"长截图需要拆成超过 {MAX_IMAGE_SLICES} 个片段，请分成两张截图后再导入",
        )
    return ranges


def _horizontal_row_activity(pixmap: fitz.Pixmap) -> list[float]:
    """Return a conservative text/card-edge signal for every horizontal row.

    The detector is intentionally content-agnostic.  It compares the centre of
    each row with that row's outer background and also counts dark/chromatic
    pixels.  Text, icons, separators and card fills therefore score as active;
    wide horizontal whitespace stays close to zero.  The result only moves a
    crop boundary and never creates or changes a transaction.
    """

    if pixmap.width < 8 or pixmap.height < 1 or pixmap.n < 3:
        return []
    samples = memoryview(pixmap.samples)
    margin = max(2, round(pixmap.width * 0.035))
    left = margin
    right = max(left + 1, pixmap.width - margin)
    sample_step = max(2, pixmap.width // 360)
    edge_width = max(2, min(12, margin))
    activity: list[float] = []
    for y in range(pixmap.height):
        row_offset = y * pixmap.stride
        edge_samples: list[tuple[int, int, int]] = []
        for x in (*range(0, edge_width, 2), *range(pixmap.width - edge_width, pixmap.width, 2)):
            offset = row_offset + x * pixmap.n
            edge_samples.append((samples[offset], samples[offset + 1], samples[offset + 2]))
        background = tuple(
            sum(pixel[channel] for pixel in edge_samples) / max(1, len(edge_samples))
            for channel in range(3)
        )
        active = 0
        sampled = 0
        for x in range(left, right, sample_step):
            offset = row_offset + x * pixmap.n
            red, green, blue = samples[offset], samples[offset + 1], samples[offset + 2]
            sampled += 1
            luminance = (red * 299 + green * 587 + blue * 114) / 1000
            background_luminance = (
                background[0] * 299 + background[1] * 587 + background[2] * 114
            ) / 1000
            colour_distance = max(
                abs(red - background[0]),
                abs(green - background[1]),
                abs(blue - background[2]),
            )
            chroma = max(red, green, blue) - min(red, green, blue)
            if (
                colour_distance >= 14
                or luminance <= min(236, background_luminance - 16)
                or (chroma >= 24 and luminance < 248)
            ):
                active += 1
        activity.append(active / max(1, sampled))
    return activity


def _safe_horizontal_gap_runs(activity: list[float]) -> list[tuple[int, int]]:
    """Find stable whitespace runs in a row-activity signal.

    A local maximum guard keeps the chosen line a few pixels away from glyph
    antialiasing and thin separators.  An all-active band deliberately returns
    no run so callers can retain the old deterministic cut.
    """

    if len(activity) < ADAPTIVE_MIN_GAP_HEIGHT:
        return []
    ordered = sorted(max(0.0, float(value)) for value in activity)
    low_quantile = ordered[min(len(ordered) - 1, max(0, len(ordered) // 5))]
    threshold = min(0.08, max(0.006, low_quantile * 1.35 + 0.004))
    guarded = [
        max(
            activity[max(0, index - ADAPTIVE_GAP_GUARD_ROWS):
                     min(len(activity), index + ADAPTIVE_GAP_GUARD_ROWS + 1)]
        )
        for index in range(len(activity))
    ]
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, score in enumerate(guarded):
        if score <= threshold:
            if start is None:
                start = index
            continue
        if start is not None and index - start >= ADAPTIVE_MIN_GAP_HEIGHT:
            runs.append((start, index - 1))
        start = None
    if start is not None and len(guarded) - start >= ADAPTIVE_MIN_GAP_HEIGHT:
        runs.append((start, len(guarded) - 1))
    return runs


def _nearest_positions_in_gap_runs(
    runs: list[tuple[int, int]],
    *,
    target: int,
    band_top: int,
) -> list[int]:
    positions: list[int] = []
    for start, end in runs:
        guarded_start = band_top + start + ADAPTIVE_GAP_GUARD_ROWS
        guarded_end = band_top + end - ADAPTIVE_GAP_GUARD_ROWS
        if guarded_start > guarded_end:
            continue
        position = min(max(target, guarded_start), guarded_end)
        if abs(position - target) <= ADAPTIVE_CUT_SEARCH_RADIUS:
            positions.append(position)
    return sorted(set(positions), key=lambda value: (abs(value - target), value))


def _select_adaptive_overlap_bounds(
    activity: list[float],
    *,
    band_top: int,
    nominal_start: int,
    nominal_end: int,
    transaction_row_centers: list[int] | None = None,
) -> dict[str, Any]:
    """Move both sides of one overlap to nearby horizontal whitespace.

    Both boundaries must be safe.  This means the overlap is bounded by gaps
    and contains complete visual rows.  If the band has no trustworthy pair,
    the exact legacy coordinates are returned as a safe deterministic fallback.
    """

    fallback = {
        "start": nominal_start,
        "end": nominal_end,
        "detected": False,
        "adapted": False,
        "method": "fixed_overlap_fallback",
        "start_shift": 0,
        "end_shift": 0,
    }
    runs = _safe_horizontal_gap_runs(activity)
    if not runs:
        return fallback
    start_candidates = _nearest_positions_in_gap_runs(
        runs,
        target=nominal_start,
        band_top=band_top,
    )
    end_candidates = _nearest_positions_in_gap_runs(
        runs,
        target=nominal_end,
        band_top=band_top,
    )
    pairs = [
        (start, end)
        for start in start_candidates
        for end in end_candidates
        if ADAPTIVE_MIN_OVERLAP <= end - start <= ADAPTIVE_MAX_OVERLAP
    ]
    if not pairs:
        return fallback

    # A wallet transaction usually contains a primary line and a smaller
    # merchant/detail line.  Both create horizontal whitespace, so choosing
    # the gap nearest the nominal cut can still split one transaction between
    # those two lines.  Coloured transaction icons are a much stronger row
    # anchor: when they are available, keep both crop edges well away from the
    # nearest icon centre and therefore near the midpoint between records.
    absolute_centers = sorted(
        band_top + int(center)
        for center in (transaction_row_centers or [])
        if isinstance(center, int)
    )
    minimum_row_clearance = 0
    if len(absolute_centers) >= 2:
        spacings = [
            right - left
            for left, right in zip(absolute_centers, absolute_centers[1:])
            if right > left
        ]
        if spacings:
            median_spacing = sorted(spacings)[len(spacings) // 2]
            minimum_row_clearance = min(110, max(56, round(median_spacing * 0.38)))

    def row_clearance(position: int) -> int:
        if not absolute_centers:
            return 2**30
        return min(abs(position - center) for center in absolute_centers)

    if minimum_row_clearance:
        row_safe_pairs = [
            pair
            for pair in pairs
            if row_clearance(pair[0]) >= minimum_row_clearance
            and row_clearance(pair[1]) >= minimum_row_clearance
        ]
        if row_safe_pairs:
            pairs = row_safe_pairs
    start, end = min(
        pairs,
        key=lambda pair: (
            abs(pair[0] - nominal_start) + abs(pair[1] - nominal_end),
            abs((pair[1] - pair[0]) - SLICE_OVERLAP),
            pair[0],
        ),
    )
    return {
        "start": start,
        "end": end,
        "detected": True,
        "adapted": start != nominal_start or end != nominal_end,
        "method": "horizontal_whitespace",
        "start_shift": start - nominal_start,
        "end_shift": end - nominal_end,
        "transaction_row_aware": bool(minimum_row_clearance),
        "minimum_row_clearance": minimum_row_clearance or None,
    }


def _apply_adaptive_overlap_bounds(
    nominal_ranges: list[tuple[int, int]],
    selections: list[dict[str, Any]],
    *,
    normalized_height: int,
) -> list[tuple[int, int]]:
    """Apply validated overlap selections without changing slice count/ends."""

    if len(nominal_ranges) <= 1:
        return list(nominal_ranges)
    if len(selections) != len(nominal_ranges) - 1:
        return list(nominal_ranges)
    adjusted = [list(item) for item in nominal_ranges]
    maximum_slice_height = SLICE_HEIGHT + ADAPTIVE_CUT_SEARCH_RADIUS * 2
    for index, selection in enumerate(selections):
        if not selection.get("detected"):
            continue
        start = int(selection.get("start", nominal_ranges[index + 1][0]))
        end = int(selection.get("end", nominal_ranges[index][1]))
        current_top = adjusted[index][0]
        next_bottom = adjusted[index + 1][1]
        if (
            start < 0
            or end > normalized_height
            or end - start < ADAPTIVE_MIN_OVERLAP
            or end - start > ADAPTIVE_MAX_OVERLAP
            or end <= current_top
            or next_bottom <= start
            or end - current_top > maximum_slice_height
            or next_bottom - start > maximum_slice_height
        ):
            continue
        adjusted[index][1] = end
        adjusted[index + 1][0] = start
    ranges = [(int(start), int(end)) for start, end in adjusted]
    if ranges[0][0] != 0 or ranges[-1][1] != normalized_height:
        return list(nominal_ranges)
    if len(ranges) > MAX_IMAGE_SLICES or any(start >= end for start, end in ranges):
        return list(nominal_ranges)
    return ranges


def _render_image_slices(
    content: bytes,
    *,
    detected_type: str,
    dimensions: tuple[int, int],
    force_multiple: bool,
) -> list[dict[str, Any]]:
    width, height = dimensions
    scale = _normalization_scale(width, height)
    normalized_width = max(1, round(width * scale))
    normalized_height = max(1, round(height * scale))
    nominal_ranges = _slice_ranges(normalized_height)
    ranges = nominal_ranges
    if force_multiple and len(ranges) < 2:
        if normalized_height < 2:
            raise import_error(
                400,
                "cashflow_vision_invalid_file",
                "图片高度过小，无法生成可恢复的 OCR 切片",
            )
        overlap = min(SLICE_OVERLAP, max(1, normalized_height // 5))
        midpoint = max(1, normalized_height // 2)
        first_bottom = min(normalized_height, midpoint + overlap // 2)
        second_top = max(0, midpoint - overlap // 2)
        ranges = [(0, first_bottom), (second_top, normalized_height)]

    filetype = {
        "image/png": "png",
        "image/jpeg": "jpeg",
        "image/webp": "webp",
    }[detected_type]
    try:
        document = fitz.open(stream=content, filetype=filetype)
        page = document[0]
        render_scale = normalized_width / page.rect.width
        page_y_per_source_pixel = page.rect.height / height
        adaptive_selections: list[dict[str, Any]] = []
        if not force_multiple and len(nominal_ranges) > 1:
            for index in range(len(nominal_ranges) - 1):
                nominal_start = nominal_ranges[index + 1][0]
                nominal_end = nominal_ranges[index][1]
                band_top = max(0, nominal_start - ADAPTIVE_CUT_SEARCH_RADIUS)
                band_bottom = min(
                    normalized_height,
                    nominal_end + ADAPTIVE_CUT_SEARCH_RADIUS,
                )
                selection = {
                    "start": nominal_start,
                    "end": nominal_end,
                    "detected": False,
                    "adapted": False,
                    "method": "fixed_overlap_fallback",
                    "start_shift": 0,
                    "end_shift": 0,
                }
                try:
                    source_top = band_top / scale
                    source_bottom = min(float(height), band_bottom / scale)
                    band_clip = fitz.Rect(
                        page.rect.x0,
                        page.rect.y0 + source_top * page_y_per_source_pixel,
                        page.rect.x1,
                        page.rect.y0 + source_bottom * page_y_per_source_pixel,
                    )
                    band_pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(render_scale, render_scale),
                        clip=band_clip,
                        colorspace=fitz.csRGB,
                        alpha=False,
                    )
                    transaction_rows = _detect_transaction_rows(band_pixmap)
                    selection = _select_adaptive_overlap_bounds(
                        _horizontal_row_activity(band_pixmap),
                        band_top=band_top,
                        nominal_start=nominal_start,
                        nominal_end=nominal_end,
                        transaction_row_centers=(
                            transaction_rows.get("row_centers")
                            if transaction_rows.get("reliable")
                            else None
                        ),
                    )
                except Exception:
                    # Boundary detection is a quality enhancement.  A noisy or
                    # unusual image must still use the old deterministic crop.
                    pass
                adaptive_selections.append(selection)
            ranges = _apply_adaptive_overlap_bounds(
                nominal_ranges,
                adaptive_selections,
                normalized_height=normalized_height,
            )
        slices: list[dict[str, Any]] = []
        for sequence_number, (normalized_top, normalized_bottom) in enumerate(ranges, start=1):
            overlap_pixels = 0
            if sequence_number > 1:
                previous_bottom = ranges[sequence_number - 2][1]
                overlap_pixels = max(0, previous_bottom - normalized_top)
            source_top = normalized_top / scale
            source_bottom = min(float(height), normalized_bottom / scale)
            clip = fitz.Rect(
                page.rect.x0,
                page.rect.y0 + source_top * page_y_per_source_pixel,
                page.rect.x1,
                page.rect.y0 + source_bottom * page_y_per_source_pixel,
            )
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(render_scale, render_scale),
                clip=clip,
                colorspace=fitz.csRGB,
                alpha=False,
            )
            transaction_row_detection = _detect_transaction_rows(pixmap)
            png = pixmap.tobytes("png")
            slices.append(
                {
                    "sequence_number": sequence_number,
                    "content": png,
                    "content_hash": hashlib.sha256(png).hexdigest(),
                    "byte_size": len(png),
                    "source_locator": {
                        "source_pixel_top": round(source_top),
                        "source_pixel_bottom": round(source_bottom),
                        "source_pixel_width": width,
                        "source_pixel_height": height,
                        "normalized_top": normalized_top,
                        "normalized_bottom": normalized_bottom,
                        "normalized_width": pixmap.width,
                        "normalized_height": pixmap.height,
                        "overlap_pixels": overlap_pixels,
                        "adaptive_top_boundary": (
                            adaptive_selections[sequence_number - 2]
                            if sequence_number > 1
                            and sequence_number - 2 < len(adaptive_selections)
                            else None
                        ),
                        "adaptive_bottom_boundary": (
                            adaptive_selections[sequence_number - 1]
                            if sequence_number - 1 < len(adaptive_selections)
                            else None
                        ),
                        "transaction_row_detection": transaction_row_detection,
                    },
                }
            )
        document.close()
        return slices
    except HTTPException:
        raise
    except Exception as exc:
        raise import_error(
            422,
            "cashflow_vision_slice_failed",
            "截图无法稳定切片，请换一张清晰的 PNG、JPG 或 WebP 图片",
        ) from exc


def render_long_image_slices(
    content: bytes,
    *,
    detected_type: str,
    dimensions: tuple[int, int],
) -> list[dict[str, Any]]:
    parts = _render_image_slices(
        content,
        detected_type=detected_type,
        dimensions=dimensions,
        force_multiple=False,
    )
    if len(parts) < 2:
        raise ValueError("segmented OCR requires at least two slices")
    return parts


def render_sequence_image_slices(
    content: bytes,
    *,
    detected_type: str,
    dimensions: tuple[int, int],
) -> list[dict[str, Any]]:
    """Render recoverable derived slices without retaining a whole screenshot.

    A short screenshot is deliberately split into two overlapping regions so
    that a saved artifact is never just the original image under another name.
    """

    return _render_image_slices(
        content,
        detected_type=detected_type,
        dimensions=dimensions,
        force_multiple=True,
    )


def _slice_status(artifact: FinancialRecognitionArtifact) -> str:
    metadata = artifact.artifact_metadata if isinstance(artifact.artifact_metadata, dict) else {}
    status = metadata.get("ocr_status")
    return status if status in {"pending", "processing", "completed", "failed"} else "pending"


def _row_coverage(
    *,
    locator: dict[str, Any],
    metadata: dict[str, Any],
    ocr_status: str,
) -> dict[str, Any]:
    detection = locator.get("transaction_row_detection")
    if not isinstance(detection, dict) or detection.get("reliable") is not True:
        return {
            "expected_transaction_rows": None,
            "recognized_candidate_count": metadata.get("recognized_candidate_count"),
            "missing_transaction_rows": None,
            "row_coverage_status": "unknown",
            "row_detection_version": None,
        }
    expected = detection.get("expected_transaction_rows")
    if not isinstance(expected, int) or expected < 2:
        return {
            "expected_transaction_rows": None,
            "recognized_candidate_count": metadata.get("recognized_candidate_count"),
            "missing_transaction_rows": None,
            "row_coverage_status": "unknown",
            "row_detection_version": detection.get("version"),
        }
    recognized = metadata.get("recognized_candidate_count")
    if ocr_status != "completed" or not isinstance(recognized, int) or recognized < 0:
        coverage_status = "pending"
        missing = None
    elif recognized < expected:
        coverage_status = "partial"
        missing = expected - recognized
    elif recognized > expected:
        # The coloured-icon detector is a conservative lower bound. Grey or
        # unfamiliar icons can be real transaction rows, so a larger candidate
        # count is a neutral mismatch that needs review, not proof of model
        # over-detection.
        coverage_status = "count_mismatch"
        missing = 0
    else:
        coverage_status = "complete"
        missing = 0
    return {
        "expected_transaction_rows": expected,
        "recognized_candidate_count": recognized if isinstance(recognized, int) else None,
        "missing_transaction_rows": missing,
        "row_coverage_status": coverage_status,
        "row_detection_version": detection.get("version"),
    }


def _recognition_progress(
    db: Session,
    *,
    batch: FinancialImportBatch,
) -> dict[str, Any]:
    artifacts = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
    ).order_by(FinancialRecognitionArtifact.sequence_number.asc()).all()
    slices: list[dict[str, Any]] = []
    counts = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
    for artifact in artifacts:
        metadata = artifact.artifact_metadata if isinstance(artifact.artifact_metadata, dict) else {}
        status = _slice_status(artifact)
        counts[status] += 1
        locator = artifact.source_locator if isinstance(artifact.source_locator, dict) else {}
        row_coverage = _row_coverage(
            locator=locator,
            metadata=metadata,
            ocr_status=status,
        )
        slices.append(
            {
                "sequence_number": artifact.sequence_number,
                "status": status,
                "source_image_sequence": locator.get("source_image_sequence", 1),
                "source_image_slice_sequence": locator.get("source_image_slice_sequence", artifact.sequence_number),
                "source_image_slice_total": locator.get("source_image_slice_total", len(artifacts)),
                "source_pixel_top": locator.get("source_pixel_top"),
                "source_pixel_bottom": locator.get("source_pixel_bottom"),
                "ocr_character_count": metadata.get("ocr_character_count"),
                "ocr_processed_character_count": metadata.get("ocr_processed_character_count"),
                "ocr_chunk_count": metadata.get("ocr_chunk_count"),
                "ocr_text_fully_processed": metadata.get("ocr_text_fully_processed"),
                "ocr_provider": metadata.get("ocr_provider"),
                "ocr_model": metadata.get("ocr_model"),
                "ocr_line_count": metadata.get("ocr_line_count"),
                "ocr_average_confidence": metadata.get("ocr_average_confidence"),
                "cloud_fallback_reason": metadata.get("cloud_fallback_reason"),
                "program_candidate_count": metadata.get("program_candidate_count"),
                "program_fallback_candidate_count": metadata.get("program_fallback_candidate_count"),
                "ai_candidate_count": metadata.get("ai_candidate_count"),
                "ai_rejected_candidate_count": metadata.get("ai_rejected_candidate_count"),
                "ai_chunk_count": metadata.get("ai_chunk_count"),
                **row_coverage,
                "error_code": artifact.error_code if status == "failed" else None,
                "error_message": metadata.get("error_message") if status == "failed" else None,
            }
        )
    hints = batch.parse_hints if isinstance(batch.parse_hints, dict) else {}
    sequence_images = hints.get("sequence_images") if isinstance(hints.get("sequence_images"), list) else []
    duplicate_images = [
        item
        for item in sequence_images
        if isinstance(item, dict) and isinstance(item.get("duplicate_of_image_sequence"), int)
    ]
    submitted_images = len(sequence_images) or (1 if artifacts else 0)
    return {
        "mode": "image_sequence" if batch.source_type == "screenshot_sequence" else "segmented_image",
        "submitted_images": submitted_images,
        "unique_images": max(0, submitted_images - len(duplicate_images)),
        "duplicate_images": duplicate_images,
        "total_slices": len(artifacts),
        "pending_slices": counts["pending"],
        "processing_slices": counts["processing"],
        "completed_slices": counts["completed"],
        "failed_slices": counts["failed"],
        "slices": slices,
    }


def _store_progress(db: Session, *, batch: FinancialImportBatch) -> dict[str, Any]:
    progress = _recognition_progress(db, batch=batch)
    hints = dict(batch.parse_hints or {})
    hints["recognition_progress"] = progress
    batch.parse_hints = hints
    return progress


def create_segmented_ocr_batch(
    db: Session,
    *,
    user_id: int,
    content: bytes,
    content_type: str,
    original_filename: str,
    expected_data_epoch: int | None = None,
) -> tuple[FinancialImportBatch, bool]:
    detected_type = _validated_image_type(content, content_type)
    dimensions = _validate_image_dimensions(content, detected_type, segmented=True)
    if not should_use_segmented_ocr(dimensions):
        raise ValueError("image does not require segmented OCR")
    rendered_slices = render_long_image_slices(
        content,
        detected_type=detected_type,
        dimensions=dimensions,
    )
    content_hash = hashlib.sha256(content).hexdigest()

    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if expected_data_epoch is not None and owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_data_cleared",
            "切片期间账户数据已被清空，本次结果未保存，请重新导入",
        )
    reusable = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.origin_type == "ocr",
        FinancialImportBatch.source_type == "long_screenshot",
        FinancialImportBatch.content_hash == content_hash,
        FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
        FinancialImportBatch.status != "cancelled",
    ).first()
    if reusable is not None:
        return reusable, True
    superseded = db.query(FinancialImportBatch.id).filter(
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.origin_type == "ocr",
        FinancialImportBatch.source_type == "long_screenshot",
        FinancialImportBatch.content_hash == content_hash,
        FinancialImportBatch.parser_version != LONG_IMAGE_PARSER_VERSION,
        FinancialImportBatch.status != "cancelled",
    ).order_by(FinancialImportBatch.id.desc()).first()

    created_paths: list[Path] = []
    committed = False
    try:
        safe_name = Path(original_filename or "long-screenshot.png").name[:255]
        batch = FinancialImportBatch(
            user_id=user_id,
            origin_type="ocr",
            source_type="long_screenshot",
            attachment_version_id=None,
            original_filename=safe_name,
            content_type=detected_type,
            file_size=len(content),
            content_hash=content_hash,
            parser_version=LONG_IMAGE_PARSER_VERSION,
            status="processing",
            column_mapping={},
            parse_hints={
                "intake": "ocr",
                "image_dimensions": {"width": dimensions[0], "height": dimensions[1]},
                "supersedes_batch_id": superseded[0] if superseded is not None else None,
            },
            parsed_at=None,
        )
        db.add(batch)
        db.flush()
        for item in rendered_slices:
            sequence_number = int(item["sequence_number"])
            source_locator = {
                **item["source_locator"],
                "source_image_sequence": 1,
                "source_image_slice_sequence": sequence_number,
                "source_image_slice_total": len(rendered_slices),
            }
            attachment = save_personal_attachment(
                db,
                user_id=user_id,
                document_type="cashflow_import",
                logical_key=f"cashflow-batch-{batch.id}-slice-{sequence_number}",
                display_name=f"长截图识别片段 {sequence_number}/{len(rendered_slices)}",
                original_filename=f"slice-{sequence_number:03d}.png",
                content_type="image/png",
                content=item["content"],
            )
            created_paths.append(resolve_attachment_path(attachment))
            db.add(
                FinancialRecognitionArtifact(
                    user_id=user_id,
                    batch_id=batch.id,
                    artifact_type="image_slice",
                    sequence_number=sequence_number,
                    status="ready",
                    attachment_version_id=attachment.id,
                    content_hash=item["content_hash"],
                    content_type="image/png",
                    byte_size=item["byte_size"],
                    source_locator=source_locator,
                    artifact_metadata={
                        "contains_sensitive_source_image": True,
                        "ocr_status": "pending",
                    },
                )
            )
        db.flush()
        _store_progress(db, batch=batch)
        db.commit()
        committed = True
        db.refresh(batch)
        return batch, False
    except IntegrityError as exc:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        reusable = db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.origin_type == "ocr",
            FinancialImportBatch.source_type == "long_screenshot",
            FinancialImportBatch.content_hash == content_hash,
            FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
            FinancialImportBatch.status != "cancelled",
        ).first()
        if reusable is not None:
            return reusable, True
        raise import_error(409, "cashflow_import_conflict", "相同长截图正在识别，请刷新后继续") from exc
    except Exception:
        db.rollback()
        if not committed:
            for path in created_paths:
                path.unlink(missing_ok=True)
        raise


def create_image_sequence_ocr_batch(
    db: Session,
    *,
    user_id: int,
    images: list[dict[str, Any]],
    expected_data_epoch: int | None = None,
) -> tuple[FinancialImportBatch, bool]:
    if len(images) < 2:
        raise import_error(400, "cashflow_vision_sequence_too_short", "连续截图至少选择 2 张")
    if len(images) > MAX_SEQUENCE_IMAGES:
        raise import_error(
            413,
            "cashflow_vision_sequence_too_many_images",
            f"一次最多选择 {MAX_SEQUENCE_IMAGES} 张连续截图",
        )

    total_bytes = sum(len(item.get("content") or b"") for item in images)
    if total_bytes > MAX_SEQUENCE_TOTAL_BYTES:
        raise import_error(413, "cashflow_vision_sequence_too_large", "连续截图总大小不能超过 90MB")

    sequence_hasher = hashlib.sha256(b"cashflow-image-sequence-v1\0")
    seen_hashes: dict[str, int] = {}
    sequence_images: list[dict[str, Any]] = []
    rendered_slices: list[dict[str, Any]] = []
    global_sequence = 1
    for image_sequence, image in enumerate(images, start=1):
        content = image.get("content")
        if not isinstance(content, bytes) or not content:
            raise import_error(400, "cashflow_vision_invalid_file", f"第 {image_sequence} 张图片内容为空")
        declared_type = str(image.get("content_type") or "application/octet-stream")
        detected_type = _validated_image_type(content, declared_type)
        dimensions = _validate_image_dimensions(content, detected_type, segmented=True)
        content_hash = hashlib.sha256(content).hexdigest()
        sequence_hasher.update(bytes.fromhex(content_hash))
        sequence_hasher.update(b"\0")
        duplicate_of = seen_hashes.get(content_hash)
        if duplicate_of is not None:
            sequence_images.append(
                {
                    "image_sequence": image_sequence,
                    "width": dimensions[0],
                    "height": dimensions[1],
                    "slice_count": 0,
                    "duplicate_of_image_sequence": duplicate_of,
                }
            )
            continue
        seen_hashes[content_hash] = image_sequence
        parts = render_sequence_image_slices(
            content,
            detected_type=detected_type,
            dimensions=dimensions,
        )
        if len(rendered_slices) + len(parts) > MAX_SEQUENCE_TOTAL_SLICES:
            raise import_error(
                413,
                "cashflow_vision_sequence_too_many_slices",
                f"连续截图合计需要超过 {MAX_SEQUENCE_TOTAL_SLICES} 个片段，请分成两个批次导入",
            )
        sequence_images.append(
            {
                "image_sequence": image_sequence,
                "width": dimensions[0],
                "height": dimensions[1],
                "slice_count": len(parts),
                "duplicate_of_image_sequence": None,
            }
        )
        for local_sequence, part in enumerate(parts, start=1):
            rendered_slices.append(
                {
                    **part,
                    "sequence_number": global_sequence,
                    "source_locator": {
                        **part["source_locator"],
                        "source_image_sequence": image_sequence,
                        "source_image_slice_sequence": local_sequence,
                        "source_image_slice_total": len(parts),
                    },
                }
            )
            global_sequence += 1

    content_hash = sequence_hasher.hexdigest()
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    if expected_data_epoch is not None and owner.business_data_epoch != expected_data_epoch:
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_data_cleared",
            "切片期间账户数据已被清空，本次结果未保存，请重新导入",
        )
    reusable = db.query(FinancialImportBatch).filter(
        FinancialImportBatch.user_id == user_id,
        FinancialImportBatch.origin_type == "ocr",
        FinancialImportBatch.source_type == "screenshot_sequence",
        FinancialImportBatch.content_hash == content_hash,
        FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
        FinancialImportBatch.status != "cancelled",
    ).first()
    if reusable is not None:
        return reusable, True

    created_paths: list[Path] = []
    committed = False
    try:
        batch = FinancialImportBatch(
            user_id=user_id,
            origin_type="ocr",
            source_type="screenshot_sequence",
            attachment_version_id=None,
            original_filename=f"连续账单截图（{len(images)} 张）",
            content_type="application/x-cashflow-image-sequence",
            file_size=total_bytes,
            content_hash=content_hash,
            parser_version=LONG_IMAGE_PARSER_VERSION,
            status="processing",
            column_mapping={},
            parse_hints={
                "intake": "ocr",
                "sequence_images": sequence_images,
            },
            parsed_at=None,
        )
        db.add(batch)
        db.flush()
        for item in rendered_slices:
            sequence_number = int(item["sequence_number"])
            locator = item["source_locator"]
            image_sequence = int(locator["source_image_sequence"])
            local_sequence = int(locator["source_image_slice_sequence"])
            local_total = int(locator["source_image_slice_total"])
            attachment = save_personal_attachment(
                db,
                user_id=user_id,
                document_type="cashflow_import",
                logical_key=f"cashflow-batch-{batch.id}-slice-{sequence_number}",
                display_name=f"连续截图 {image_sequence}/{len(images)} · 片段 {local_sequence}/{local_total}",
                original_filename=f"image-{image_sequence:03d}-slice-{local_sequence:03d}.png",
                content_type="image/png",
                content=item["content"],
            )
            created_paths.append(resolve_attachment_path(attachment))
            db.add(
                FinancialRecognitionArtifact(
                    user_id=user_id,
                    batch_id=batch.id,
                    artifact_type="image_slice",
                    sequence_number=sequence_number,
                    status="ready",
                    attachment_version_id=attachment.id,
                    content_hash=item["content_hash"],
                    content_type="image/png",
                    byte_size=item["byte_size"],
                    source_locator=locator,
                    artifact_metadata={
                        "contains_sensitive_source_image": True,
                        "ocr_status": "pending",
                        "source_image_sequence": image_sequence,
                    },
                )
            )
        db.flush()
        _store_progress(db, batch=batch)
        db.commit()
        committed = True
        db.refresh(batch)
        return batch, False
    except IntegrityError as exc:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        reusable = db.query(FinancialImportBatch).filter(
            FinancialImportBatch.user_id == user_id,
            FinancialImportBatch.origin_type == "ocr",
            FinancialImportBatch.source_type == "screenshot_sequence",
            FinancialImportBatch.content_hash == content_hash,
            FinancialImportBatch.parser_version == LONG_IMAGE_PARSER_VERSION,
            FinancialImportBatch.status != "cancelled",
        ).first()
        if reusable is not None:
            return reusable, True
        raise import_error(409, "cashflow_import_conflict", "相同连续截图正在识别，请刷新后继续") from exc
    except Exception:
        db.rollback()
        if not committed:
            for path in created_paths:
                path.unlink(missing_ok=True)
        raise


def _safe_processing_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        return (
            str(exc.detail.get("code") or "cashflow_vision_slice_failed")[:100],
            str(exc.detail.get("message") or "该片段识别失败，请重试")[:240],
        )
    if isinstance(exc, FileNotFoundError):
        return "cashflow_vision_slice_missing", "识别片段缺失，请删除该批次后重新上传长截图"
    return "cashflow_vision_slice_failed", "该片段识别失败，请重试"


def _normalized_overlap_text(value: str | None) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (value or "").lower())


def _normalized_ocr_lines(ocr_text: str) -> list[tuple[int, str]]:
    # The deterministic parser numbers candidates after removing blank OCR
    # lines.  Anchors and evidence must use the same coordinate system or a
    # blank line can move a transaction across a date heading.
    normalized = [
        re.sub(r"[\t \u3000]+", " ", raw).strip()
        for raw in str(ocr_text or "").replace("\x00", "").splitlines()
        if raw.strip()
    ]
    return list(enumerate(normalized, start=1))


def _extract_ocr_date_anchors(
    ocr_text: str,
    *,
    reference_date: date | None = None,
) -> list[dict[str, Any]]:
    """Return top-to-bottom date markers from one OCR slice.

    OCR text has no reliable pixel boxes in the current local engine, but its
    line order is stable.  Keeping every marker (instead of a set of dates)
    lets a following slice inherit the *last active date group* when the
    overlap contains two day headings.
    """

    reference = reference_date or date.today()
    anchors: list[dict[str, Any]] = []
    for line_index, line in _normalized_ocr_lines(ocr_text):
        parsed_date, year_inferred = _program_date_from_text(
            line,
            reference_date=reference,
        )
        if parsed_date is None:
            continue
        anchors.append(
            {
                "transaction_date": parsed_date,
                "line_index": line_index,
                "year_inferred": year_inferred,
                "source_has_explicit_year": not year_inferred,
                "evidence_quote": redact_cashflow_text(line, max_length=80),
            }
        )
    return anchors


def _candidate_ocr_line_index(
    candidate: ParsedCandidate | FinancialTransactionCandidate,
    *,
    lines: list[tuple[int, str]],
) -> tuple[int | None, str]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    explicit = evidence.get("ocr_line_index")
    if (
        isinstance(explicit, int)
        and explicit >= 1
        and any(line_index == explicit for line_index, _line in lines)
    ):
        return explicit, "program_line"
    quote = str(evidence.get("evidence_quote") or "").strip()
    normalized_quote = _normalized_overlap_text(quote)
    if not normalized_quote:
        return None, "unlocated"
    matches = _matching_ocr_line_indices(
        normalized_quote=normalized_quote,
        lines=lines,
    )
    if len(matches) == 1:
        return matches[0], "evidence_quote"
    return None, "unlocated"


def _matching_ocr_line_indices(
    *,
    normalized_quote: str,
    lines: list[tuple[int, str]],
) -> list[int]:
    matches: list[int] = []
    for line_index, line in lines:
        normalized_line = _normalized_overlap_text(line)
        if not normalized_line:
            continue
        if normalized_quote in normalized_line or normalized_line in normalized_quote:
            matches.append(line_index)
    return matches


def _locate_candidate_ocr_lines(
    candidates: list[ParsedCandidate | FinancialTransactionCandidate],
    *,
    lines: list[tuple[int, str]],
) -> list[tuple[int | None, str]]:
    """Locate candidates without guessing when repeated OCR rows look alike.

    A repeated quote can be paired by order only when the candidate group and
    OCR line group are closed one-to-one within the same slice.  Explicit line
    evidence wins and its lines are excluded from group pairing.
    """

    line_ids = {line_index for line_index, _line in lines}
    located: list[tuple[int | None, str]] = [
        (None, "unlocated") for _candidate in candidates
    ]
    claimed_lines: set[int] = set()
    unresolved_by_quote: dict[str, list[int]] = {}
    for index, candidate in enumerate(candidates):
        evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
        explicit = evidence.get("ocr_line_index")
        if isinstance(explicit, int) and explicit in line_ids:
            located[index] = (explicit, "program_line")
            claimed_lines.add(explicit)
            continue
        normalized_quote = _normalized_overlap_text(
            str(evidence.get("evidence_quote") or "")
        )
        if normalized_quote:
            unresolved_by_quote.setdefault(normalized_quote, []).append(index)

    proposals: list[tuple[list[int], list[int], str]] = []
    for normalized_quote, candidate_indexes in unresolved_by_quote.items():
        matches = [
            line_index
            for line_index in _matching_ocr_line_indices(
                normalized_quote=normalized_quote,
                lines=lines,
            )
            if line_index not in claimed_lines
        ]
        if len(matches) != len(candidate_indexes):
            continue
        stable_indexes = []
        detection_methods = []
        for index in candidate_indexes:
            evidence = (
                candidates[index].evidence
                if isinstance(candidates[index].evidence, dict)
                else {}
            )
            stable_indexes.append(evidence.get("slice_candidate_index"))
            detection_methods.append(evidence.get("detection_method"))
        if len(candidate_indexes) > 1:
            if not all(method == "program" for method in detection_methods):
                continue
            if not all(
                isinstance(value, int) and value >= 1
                for value in stable_indexes
            ) or len(set(stable_indexes)) != len(stable_indexes):
                continue
        ordered_candidates = sorted(
            candidate_indexes,
            key=lambda index: int(
                (
                    candidates[index].evidence
                    if isinstance(candidates[index].evidence, dict)
                    else {}
                ).get("slice_candidate_index")
                or index + 1
            ),
        )
        proposals.append(
            (
                ordered_candidates,
                sorted(matches),
                "evidence_quote_ordered_group"
                if len(candidate_indexes) > 1
                else "evidence_quote",
            )
        )

    proposal_line_counts: dict[int, int] = {}
    for _candidate_indexes, matches, _method in proposals:
        for line_index in matches:
            proposal_line_counts[line_index] = proposal_line_counts.get(line_index, 0) + 1
    for candidate_indexes, matches, method in proposals:
        if any(proposal_line_counts[line_index] != 1 for line_index in matches):
            continue
        for candidate_index, line_index in zip(candidate_indexes, matches):
            located[candidate_index] = (line_index, method)
    return located


def _approximate_candidate_region(
    *,
    locator: dict[str, Any],
    line_index: int | None = None,
    candidate_index: int | None,
    candidate_total: int | None,
) -> dict[str, Any]:
    width = max(1, int(locator.get("normalized_width") or 1))
    height = max(1, int(locator.get("normalized_height") or 1))
    line_positions = locator.get("ocr_line_positions")
    if line_index is not None and isinstance(line_positions, list):
        position = next(
            (
                item
                for item in line_positions
                if isinstance(item, dict) and item.get("line_index") == line_index
            ),
            None,
        )
        polygon = position.get("polygon") if isinstance(position, dict) else None
        points = [
            point
            for point in (polygon or [])
            if isinstance(point, dict)
            and isinstance(point.get("x"), int)
            and isinstance(point.get("y"), int)
        ]
        if points:
            raw_top = min(point["y"] for point in points)
            raw_bottom = max(point["y"] for point in points)
            line_height = max(24, raw_bottom - raw_top)
            padding = max(36, round(line_height * 1.4))
            return {
                "left": 0,
                "top": max(0, raw_top - padding),
                "right": width,
                "bottom": min(height, max(raw_top + 1, raw_bottom + padding)),
                "coordinate_space": "slice_pixels",
                "precision": "ocr_text_line",
                "method": "tencent_ocr_text_polygon",
                "note": "依据腾讯云 OCR 返回的文字行坐标定位，并向上下扩展以覆盖同一交易行。",
            }
    detection = locator.get("transaction_row_detection")
    row_centers = (
        [int(value) for value in detection.get("row_centers", []) if isinstance(value, int)]
        if isinstance(detection, dict) and detection.get("reliable") is True
        else []
    )
    if (
        candidate_index is not None
        and candidate_index >= 1
        and candidate_total is not None
        and candidate_total >= candidate_index
        and row_centers
        and len(row_centers) == candidate_total
    ):
        mapped_index = candidate_index - 1
        center = row_centers[mapped_index]
        previous = row_centers[mapped_index - 1] if mapped_index > 0 else None
        following = row_centers[mapped_index + 1] if mapped_index + 1 < len(row_centers) else None
        default_half = max(70, round(height / max(len(row_centers), 2) / 2))
        top = round((previous + center) / 2) if previous is not None else center - default_half
        bottom = round((center + following) / 2) if following is not None else center + default_half
        return {
            "left": 0,
            "top": max(0, top),
            "right": width,
            "bottom": min(height, max(top + 1, bottom)),
            "coordinate_space": "slice_pixels",
            "precision": "approximate",
            "method": "transaction_icon_row_alignment",
            "note": "当前本地 OCR 未返回文字框；框选依据彩色交易图标行与候选顺序近似定位。",
        }
    return {
        "left": 0,
        "top": 0,
        "right": width,
        "bottom": height,
        "coordinate_space": "slice_pixels",
        "precision": "slice_only",
        "method": "slice_only",
        "note": "OCR 文本行与图标行无法唯一对齐；当前只定位到识别切片，不给出可能框错的行区域。",
    }


def _annotate_parsed_source_locations(
    parsed: list[ParsedCandidate],
    *,
    ocr_text: str,
    source_locator: dict[str, Any],
) -> list[ParsedCandidate]:
    lines = _normalized_ocr_lines(ocr_text)
    located = _locate_candidate_ocr_lines(parsed, lines=lines)
    line_counts: dict[int, int] = {}
    for line_index, _method in located:
        if line_index is not None:
            line_counts[line_index] = line_counts.get(line_index, 0) + 1
    ordered_unique_lines = sorted(
        line_index for line_index, count in line_counts.items() if count == 1
    )
    visual_rank_by_line = {
        line_index: rank
        for rank, line_index in enumerate(ordered_unique_lines, start=1)
    }
    annotated: list[ParsedCandidate] = []
    for candidate, (line_index, line_method) in zip(parsed, located):
        evidence = dict(candidate.evidence or {})
        if line_index is not None:
            evidence["ocr_line_index"] = line_index
        evidence["ocr_text_locator"] = {
            "line_index": line_index,
            "precision": "exact" if line_index is not None else "unlocated",
            "method": line_method,
        }
        region = _approximate_candidate_region(
            locator=source_locator,
            line_index=line_index,
            candidate_index=visual_rank_by_line.get(line_index),
            candidate_total=len(ordered_unique_lines) or None,
        )
        evidence["candidate_region"] = region
        sources = list(evidence.get("source_slices") or [])
        if sources:
            first = dict(sources[0])
            first["candidate_region"] = region
            first["ocr_line_index"] = line_index
            sources[0] = first
            evidence["source_slices"] = sources
        annotated.append(replace(candidate, evidence=evidence))
    return annotated


def _serialize_date_context(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    serialized = dict(value)
    transaction_date = serialized.get("transaction_date")
    if isinstance(transaction_date, date):
        serialized["transaction_date"] = transaction_date.isoformat()
    return serialized


def _parse_stored_date_context(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw_date = value.get("transaction_date")
    try:
        transaction_date = date.fromisoformat(str(raw_date))
    except (TypeError, ValueError):
        return None
    return {**value, "transaction_date": transaction_date}


def _date_context_from_anchor(
    anchor: dict[str, Any],
    *,
    slice_sequence: int,
    source_locator: dict[str, Any],
) -> dict[str, Any]:
    return {
        "transaction_date": anchor["transaction_date"],
        "source_slice_sequence": slice_sequence,
        "source_image_sequence": source_locator.get("source_image_sequence", 1),
        "source_image_slice_sequence": source_locator.get(
            "source_image_slice_sequence",
            slice_sequence,
        ),
        "anchor_line_index": anchor.get("line_index"),
        "year_inferred": bool(anchor.get("year_inferred")),
        "source_has_explicit_year": bool(anchor.get("source_has_explicit_year")),
        "confidence": "deterministic",
        "method": "ordered_ocr_date_anchor",
    }


def _previous_slice_date_context(
    db: Session,
    *,
    batch: FinancialImportBatch,
    target_sequence: int,
    target_locator: dict[str, Any],
) -> dict[str, Any] | None:
    if target_sequence <= 1:
        return None
    previous = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
        FinancialRecognitionArtifact.sequence_number == target_sequence - 1,
    ).first()
    if previous is None or _slice_status(previous) != "completed":
        return None
    previous_locator = previous.source_locator if isinstance(previous.source_locator, dict) else {}
    previous_image = previous_locator.get("source_image_sequence", 1)
    target_image = target_locator.get("source_image_sequence", 1)
    if not isinstance(previous_image, int) or not isinstance(target_image, int):
        return None
    if target_image not in {previous_image, previous_image + 1}:
        return None
    metadata = previous.artifact_metadata if isinstance(previous.artifact_metadata, dict) else {}
    stored_context = _parse_stored_date_context(metadata.get("active_trailing_date_context"))
    if stored_context is not None:
        if target_image != previous_image:
            stored_context = {
                **stored_context,
                "confidence": "review",
                "method": "cross_image_trailing_date_without_proven_overlap",
            }
        return stored_context
    raw_dates = metadata.get("recognized_transaction_dates")
    if not isinstance(raw_dates, list):
        return None
    parsed_dates: set[date] = set()
    for raw_date in raw_dates:
        if not isinstance(raw_date, str):
            continue
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        parsed_dates.add(parsed_date)
    if len(parsed_dates) != 1:
        return None
    transaction_date = next(iter(parsed_dates))
    return {
        "transaction_date": transaction_date,
        "source_slice_sequence": previous.sequence_number,
        "source_image_sequence": previous_image,
        "source_image_slice_sequence": previous_locator.get(
            "source_image_slice_sequence",
            previous.sequence_number,
        ),
        "year_inferred": False,
        "source_has_explicit_year": False,
        "confidence": "review",
        "method": "unique_previous_slice_candidate_date",
    }


def _context_for_candidate(
    candidate: ParsedCandidate | FinancialTransactionCandidate,
    *,
    lines: list[tuple[int, str]],
    anchors: list[dict[str, Any]],
    previous_context: dict[str, Any] | None,
    slice_sequence: int,
    source_locator: dict[str, Any],
    candidate_line_index: int | None,
) -> dict[str, Any] | None:
    line_index = candidate_line_index
    if line_index is not None:
        preceding = [
            anchor
            for anchor in anchors
            if isinstance(anchor.get("line_index"), int)
            and int(anchor["line_index"]) <= line_index
        ]
        if preceding:
            return _date_context_from_anchor(
                preceding[-1],
                slice_sequence=slice_sequence,
                source_locator=source_locator,
            )
        return previous_context
    if not anchors:
        return previous_context
    # Without a unique text-line locator we cannot know whether this candidate
    # sits above or below a date heading in the same slice.  Leaving it red is
    # safer than assigning the bottom heading to rows visually above it.
    return None


def _apply_slice_date_context(
    parsed: list[ParsedCandidate],
    *,
    ocr_text: str,
    date_anchors: list[dict[str, Any]],
    previous_context: dict[str, Any] | None,
    slice_sequence: int,
    source_locator: dict[str, Any],
    content_hash: str,
) -> list[ParsedCandidate]:
    lines = _normalized_ocr_lines(ocr_text)
    contextualized: list[ParsedCandidate] = []
    located = _locate_candidate_ocr_lines(parsed, lines=lines)
    for index, (candidate, (line_index, _line_method)) in enumerate(
        zip(parsed, located),
        start=1,
    ):
        missing_date = any(
            issue.get("code") == "DATE_INVALID"
            for issue in candidate.validation_errors
        )
        if candidate.transaction_date is not None or not missing_date:
            contextualized.append(candidate)
            continue
        date_context = _context_for_candidate(
            candidate,
            lines=lines,
            anchors=date_anchors,
            previous_context=previous_context,
            slice_sequence=slice_sequence,
            source_locator=source_locator,
            candidate_line_index=line_index,
        )
        if date_context is None:
            contextualized.append(candidate)
            continue
        inherited_date = date_context["transaction_date"]
        inherited_clock = _normalized_overlap_time(
            candidate.occurred_at,
            evidence=candidate.evidence,
        )
        inherited_occurred_at = (
            datetime(
                inherited_date.year,
                inherited_date.month,
                inherited_date.day,
                inherited_clock[0],
                inherited_clock[1],
                inherited_clock[2],
            )
            if inherited_clock is not None
            else None
        )
        fingerprint = build_candidate_fingerprint(
            direction=candidate.direction,
            amount=candidate.amount,
            transaction_date=inherited_date,
            merchant=candidate.merchant,
            description=candidate.description,
        )
        key_digest = hashlib.sha256(
            f"ocr|{content_hash}|{index}|{fingerprint}".encode("utf-8")
        ).hexdigest()
        deterministic = date_context.get("confidence") == "deterministic"
        year_inferred = bool(date_context.get("year_inferred"))
        context_warnings: list[dict[str, str]] = []
        if year_inferred:
            context_warnings.append(
                {
                    "field": "transaction_date",
                    "code": "PROGRAM_YEAR_INFERRED",
                    "message": "截图只显示月日，程序按最近发生年份补全年份，可在本批次一次确认",
                }
            )
        elif not deterministic:
            context_warnings.append(
                {
                    "field": "transaction_date",
                    "code": "DATE_CONTEXT_INHERITED",
                    "message": (
                        f"本片没有独立日期标题，程序沿用上一片的唯一候选日期 "
                        f"{inherited_date.isoformat()}，仍需人工确认"
                    ),
                }
            )
        evidence = {
            **candidate.evidence,
            "date_context_inherited": True,
            "date_context": _serialize_date_context(date_context),
        }
        if year_inferred:
            evidence["date_year_inference"] = {
                "month": inherited_date.month,
                "day": inherited_date.day,
                "proposed_year": inherited_date.year,
                "status": "pending",
                "source_has_explicit_year": False,
            }
        contextualized.append(
            replace(
                candidate,
                transaction_date=inherited_date,
                occurred_at=inherited_occurred_at,
                external_key=f"ocr:{key_digest}",
                fingerprint=fingerprint,
                evidence=evidence,
                validation_errors=[
                    issue
                    for issue in candidate.validation_errors
                    if issue.get("code") != "DATE_INVALID"
                ],
                warnings=[*context_warnings, *candidate.warnings],
            )
        )
    return contextualized


def _candidate_has_issue(candidate: FinancialTransactionCandidate, code: str) -> bool:
    return any(
        isinstance(issue, dict) and issue.get("code") == code
        for issue in [*(candidate.validation_errors or []), *(candidate.warnings or [])]
    )


def _clear_stale_duplicate_review_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "economic_fact_merge",
        "review_accepted_at",
        "duplicate_review_fingerprint",
        "duplicate_review_transaction_ids",
        "duplicate_review_bucket_watermark",
        "duplicate_review_sibling",
        "duplicate_override_at",
        "duplicate_override_reason",
        "duplicate_override_transaction_ids",
        "duplicate_override_original_external_key_hash",
        "possible_duplicate_transaction_ids",
        "possible_duplicate_fact_targets",
        "possible_duplicate_candidate_ids",
        "possible_duplicate_bucket_watermark",
        "formal_duplicate_ai_review",
        "candidate_duplicate_ai_review",
    ):
        evidence.pop(key, None)
    return evidence


def _repair_existing_date_contexts_locked(
    db: Session,
    *,
    batch: FinancialImportBatch,
    repair_missing_dates: bool,
) -> tuple[set[int], int]:
    """Rebuild date provenance and optionally fill missing old-batch dates."""

    if batch.origin_type != "ocr" or batch.source_type not in {
        "long_screenshot",
        "screenshot_sequence",
    }:
        return set(), 0
    image_slices = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
    ).order_by(FinancialRecognitionArtifact.sequence_number.asc()).all()
    ocr_artifacts = {
        row.sequence_number: row
        for row in db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == batch.user_id,
            FinancialRecognitionArtifact.batch_id == batch.id,
            FinancialRecognitionArtifact.artifact_type == "ocr_text",
        ).all()
    }
    candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == batch.user_id,
        FinancialTransactionCandidate.batch_id == batch.id,
        FinancialTransactionCandidate.status.in_(ACTIONABLE_CANDIDATE_STATUSES),
    ).order_by(FinancialTransactionCandidate.row_number.asc()).all()
    candidates_by_slice: dict[int, list[FinancialTransactionCandidate]] = {}
    for candidate in candidates:
        sequence = (candidate.evidence or {}).get("slice_sequence")
        if isinstance(sequence, int):
            candidates_by_slice.setdefault(sequence, []).append(candidate)

    active_context: dict[str, Any] | None = None
    previous_image_sequence: int | None = None
    changed_ids: set[int] = set()
    repaired_count = 0
    for artifact in image_slices:
        if _slice_status(artifact) != "completed":
            active_context = None
            continue
        locator = artifact.source_locator if isinstance(artifact.source_locator, dict) else {}
        image_sequence = int(locator.get("source_image_sequence") or 1)
        candidate_previous_context = active_context
        if (
            candidate_previous_context is not None
            and previous_image_sequence is not None
            and image_sequence != previous_image_sequence
        ):
            candidate_previous_context = {
                **candidate_previous_context,
                "confidence": "review",
                "method": "cross_image_trailing_date_without_proven_overlap",
            }
        ocr_artifact = ocr_artifacts.get(artifact.sequence_number)
        ocr_text = ocr_artifact.content_text if ocr_artifact is not None else ""
        anchors = _extract_ocr_date_anchors(ocr_text or "")
        lines = _normalized_ocr_lines(ocr_text or "")
        slice_candidates = candidates_by_slice.get(artifact.sequence_number, [])
        located = _locate_candidate_ocr_lines(slice_candidates, lines=lines)
        line_counts: dict[int, int] = {}
        for line_index, _method in located:
            if line_index is not None:
                line_counts[line_index] = line_counts.get(line_index, 0) + 1
        ordered_unique_lines = sorted(
            line_index for line_index, count in line_counts.items() if count == 1
        )
        visual_rank_by_line = {
            line_index: rank
            for rank, line_index in enumerate(ordered_unique_lines, start=1)
        }
        for candidate, (line_index, line_method) in zip(slice_candidates, located):
            evidence = dict(candidate.evidence or {})
            region = _approximate_candidate_region(
                locator=locator,
                line_index=line_index,
                candidate_index=visual_rank_by_line.get(line_index),
                candidate_total=len(ordered_unique_lines) or None,
            )
            evidence["candidate_region"] = region
            evidence["ocr_text_locator"] = {
                "line_index": line_index,
                "precision": "exact" if line_index is not None else "unlocated",
                "method": line_method,
            }
            if line_index is not None:
                evidence["ocr_line_index"] = line_index
            sources = list(evidence.get("source_slices") or [])
            if sources:
                for source_index, source in enumerate(sources):
                    if (
                        isinstance(source, dict)
                        and source.get("slice_sequence") == artifact.sequence_number
                    ):
                        updated_source = dict(source)
                        updated_source["candidate_region"] = region
                        updated_source["ocr_line_index"] = line_index
                        sources[source_index] = updated_source
                        break
                evidence["source_slices"] = sources

            missing_date = (
                repair_missing_dates
                and candidate.transaction_date is None
                and _candidate_has_issue(candidate, "DATE_INVALID")
            )
            inferred_year_pending = _candidate_has_issue(
                candidate,
                "PROGRAM_YEAR_INFERRED",
            )
            context = (
                _context_for_candidate(
                    candidate,
                    lines=lines,
                    anchors=anchors,
                    previous_context=candidate_previous_context,
                    slice_sequence=artifact.sequence_number,
                    source_locator=locator,
                    candidate_line_index=line_index,
                )
                if missing_date
                or (inferred_year_pending and candidate.transaction_date is not None)
                else None
            )
            if (
                context is None
                and inferred_year_pending
                and candidate.transaction_date is not None
            ):
                corroborating_anchor = next(
                    (
                        anchor
                        for anchor in anchors
                        if anchor.get("transaction_date") == candidate.transaction_date
                    ),
                    None,
                )
                if corroborating_anchor is not None:
                    context = {
                        **_date_context_from_anchor(
                            corroborating_anchor,
                            slice_sequence=artifact.sequence_number,
                            source_locator=locator,
                        ),
                        "method": "candidate_date_corroborated_by_slice_anchor",
                    }
            if context is not None and context.get("confidence") == "deterministic":
                inherited_date = context["transaction_date"]
                previous_date = candidate.transaction_date
                candidate.transaction_date = inherited_date
                candidate.occurred_at = None
                candidate.validation_errors = [
                    dict(issue)
                    for issue in (candidate.validation_errors or [])
                    if issue.get("code") != "DATE_INVALID"
                ]
                source_errors = evidence.get("source_validation_errors")
                if isinstance(source_errors, list):
                    evidence["source_validation_errors"] = [
                        dict(issue)
                        for issue in source_errors
                        if isinstance(issue, dict) and issue.get("code") != "DATE_INVALID"
                    ]
                evidence["date_context_inherited"] = True
                evidence["date_context"] = _serialize_date_context(context)
                evidence["date_context_repair"] = {
                    "repaired_at": datetime.utcnow().isoformat(),
                    "method": context.get("method"),
                    "source_slice_sequence": context.get("source_slice_sequence"),
                    "previous_date": previous_date.isoformat() if previous_date else None,
                    "status": "repaired",
                }
                if context.get("year_inferred"):
                    evidence["date_year_inference"] = {
                        "month": inherited_date.month,
                        "day": inherited_date.day,
                        "proposed_year": inherited_date.year,
                        "status": "pending",
                        "source_has_explicit_year": False,
                    }
                    if not _candidate_has_issue(candidate, "PROGRAM_YEAR_INFERRED"):
                        candidate.warnings = [
                            {
                                "field": "transaction_date",
                                "code": "PROGRAM_YEAR_INFERRED",
                                "message": "截图只显示月日，程序按最近发生年份补全年份，可在本批次一次确认",
                            },
                            *(candidate.warnings or []),
                        ]
                else:
                    candidate.warnings = [
                        dict(issue)
                        for issue in (candidate.warnings or [])
                        if issue.get("code") not in {
                            "DATE_CONTEXT_INHERITED",
                            "PROGRAM_YEAR_INFERRED",
                        }
                    ]
                    evidence.pop("date_year_inference", None)
                if previous_date != inherited_date:
                    repaired_count += 1
            elif inferred_year_pending and context is not None:
                # Crossing into another uploaded screenshot without proven
                # overlap is useful context, but not enough to silently turn a
                # candidate green after a year confirmation.
                evidence["date_context"] = _serialize_date_context(context)
                evidence["date_context_repair"] = {
                    "repaired_at": datetime.utcnow().isoformat(),
                    "method": context.get("method"),
                    "source_slice_sequence": context.get("source_slice_sequence"),
                    "status": "review_required",
                }
                if not _candidate_has_issue(candidate, "DATE_CONTEXT_INHERITED"):
                    candidate.warnings = [
                        *(candidate.warnings or []),
                        {
                            "field": "transaction_date",
                            "code": "DATE_CONTEXT_INHERITED",
                            "message": "日期来自另一张截图的末尾上下文，无法证明连续，请人工确认",
                        },
                    ]
                changed_ids.add(candidate.id)
            elif inferred_year_pending:
                # Older parser versions could mistake decimal OCR noise for a
                # month/day.  If persisted OCR cannot reconstruct a unique
                # ordered date context, discard that unsafe guess and require
                # a human date instead of accepting it in the batch-year gate.
                previous_date = candidate.transaction_date
                candidate.transaction_date = None
                candidate.occurred_at = None
                candidate.validation_errors = [
                    dict(issue)
                    for issue in (candidate.validation_errors or [])
                    if issue.get("code") != "DATE_INVALID"
                ] + [
                    {
                        "field": "transaction_date",
                        "code": "DATE_INVALID",
                        "message": "OCR 原文无法唯一定位到日期分组，请人工确认",
                    }
                ]
                source_errors = evidence.get("source_validation_errors")
                if isinstance(source_errors, list):
                    evidence["source_validation_errors"] = [
                        dict(issue)
                        for issue in source_errors
                        if isinstance(issue, dict) and issue.get("code") != "DATE_INVALID"
                    ] + [
                        {
                            "field": "transaction_date",
                            "code": "DATE_INVALID",
                            "message": "OCR 原文无法唯一定位到日期分组，请人工确认",
                        }
                    ]
                candidate.warnings = [
                    dict(issue)
                    for issue in (candidate.warnings or [])
                    if issue.get("code") != "PROGRAM_YEAR_INFERRED"
                ]
                evidence.pop("date_year_inference", None)
                evidence["date_context_repair"] = {
                    "repaired_at": datetime.utcnow().isoformat(),
                    "method": "ordered_ocr_context_unresolved",
                    "previous_date": previous_date.isoformat() if previous_date else None,
                    "status": "manual_date_required",
                }
                changed_ids.add(candidate.id)
            if evidence != (candidate.evidence or {}):
                candidate.evidence = evidence
                changed_ids.add(candidate.id)
            if context is not None and context.get("confidence") == "deterministic":
                changed_ids.add(candidate.id)

        next_context = (
            _date_context_from_anchor(
                anchors[-1],
                slice_sequence=artifact.sequence_number,
                source_locator=locator,
            )
            if anchors
            else (
                {
                    **candidate_previous_context,
                    "propagated_through_slice_sequence": artifact.sequence_number,
                }
                if candidate_previous_context is not None
                else None
            )
        )
        metadata = dict(artifact.artifact_metadata or {})
        metadata["date_context_anchors"] = [
            _serialize_date_context(
                _date_context_from_anchor(
                    anchor,
                    slice_sequence=artifact.sequence_number,
                    source_locator=locator,
                )
            )
            for anchor in anchors
        ]
        metadata["active_trailing_date_context"] = _serialize_date_context(next_context)
        if metadata != (artifact.artifact_metadata or {}):
            artifact.artifact_metadata = metadata
        active_context = next_context
        previous_image_sequence = image_sequence
    return changed_ids, repaired_count


def _recompute_bulk_review_candidates(
    db: Session,
    *,
    candidates: list[FinancialTransactionCandidate],
    user_id: int,
) -> None:
    preserved_manual_duplicate_ids: set[int] = set()
    for candidate in candidates:
        next_fingerprint = build_candidate_fingerprint(
            direction=candidate.direction,
            amount=candidate.amount,
            transaction_date=candidate.transaction_date,
            merchant=candidate.merchant,
            description=candidate.description,
        )
        fingerprint_changed = candidate.fingerprint != next_fingerprint
        evidence = dict(candidate.evidence or {})
        merge_intent = evidence.get("economic_fact_merge")
        decision_fingerprint = evidence.get("duplicate_review_fingerprint")
        if not isinstance(decision_fingerprint, str) and isinstance(merge_intent, dict):
            decision_fingerprint = merge_intent.get("candidate_fingerprint")
        has_manual_duplicate_decision = bool(
            isinstance(decision_fingerprint, str)
            and (
                evidence.get("review_accepted_at")
                or evidence.get("duplicate_override_at")
                or isinstance(merge_intent, dict)
            )
        )
        decision_is_current = decision_fingerprint == next_fingerprint
        if (
            fingerprint_changed
            or not has_manual_duplicate_decision
            or not decision_is_current
        ):
            evidence = _clear_stale_duplicate_review_evidence(evidence)
        elif has_manual_duplicate_decision and candidate.id is not None:
            preserved_manual_duplicate_ids.add(candidate.id)
        candidate.evidence = evidence
        resolved_fields = set(evidence.get("user_modified_fields") or [])
        errors, category = _candidate_validation(
            db,
            candidate=candidate,
            user_id=user_id,
            resolved_fields=resolved_fields,
        )
        warnings = [dict(issue) for issue in (candidate.warnings or [])]
        if candidate.direction in {"income", "expense"} and candidate.category_id is None:
            # Import creation deliberately treats a missing category as a
            # reviewable question.  A batch year/currency acknowledgement must
            # not upgrade that yellow question into an invalid red candidate.
            errors = [
                issue
                for issue in errors
                if issue.get("code") != "CATEGORY_INVALID"
            ]
            if not any(
                issue.get("code") == "CATEGORY_REVIEW_REQUIRED"
                for issue in warnings
            ):
                warnings.append(
                    {
                        "field": "category_id",
                        "code": "CATEGORY_REVIEW_REQUIRED",
                        "message": "请确认这笔收支的分类",
                    }
                )
        elif category is not None:
            warnings = [
                issue
                for issue in warnings
                if issue.get("code") != "CATEGORY_REVIEW_REQUIRED"
            ]
        candidate.validation_errors = errors
        candidate.warnings = warnings
        if category is not None:
            candidate.category_name = category.name
        candidate.fingerprint = next_fingerprint
        candidate.status = "invalid" if errors else (
            "needs_review" if warnings else "ready"
        )
    db.flush()

    for candidate in candidates:
        if candidate.validation_errors:
            continue
        if candidate.id in preserved_manual_duplicate_ids:
            # A currency acknowledgement or a same-year confirmation does not
            # change matching semantics.  Keep the user's accepted duplicate
            # or economic-fact decision; final confirmation still performs its
            # normal ledger snapshot checks.
            continue
        possible_matches, overflow_watermark = _find_possible_duplicates_for_candidate(
            db,
            candidate=candidate,
        )
        fact_matches, fact_overflow_watermark = (
            _find_possible_duplicate_fact_targets_for_candidate(
                db,
                candidate=candidate,
            )
        )
        sibling_matches = _active_sibling_fingerprint_matches(db, candidate=candidate)
        fact_target_ids = sorted({
            (target.transaction.id, target.fact.id)
            for target in fact_matches
        })
        transaction_ids = sorted({
            *(row.id for row in possible_matches),
            *(transaction_id for transaction_id, _fact_id in fact_target_ids),
        })
        effective_overflow = overflow_watermark or fact_overflow_watermark
        warnings = [
            dict(issue)
            for issue in (candidate.warnings or [])
            if issue.get("code") != "POSSIBLE_DUPLICATE"
        ]
        evidence = dict(candidate.evidence or {})
        if transaction_ids or effective_overflow is not None or sibling_matches:
            message = (
                f"同日同金额已有 {effective_overflow.count} 个可能对应，请人工核对"
                if effective_overflow is not None
                else f"发现 {len(fact_target_ids)} 个同日同额且描述相近的已有经济事实，请核对后决定是否入账"
                if fact_target_ids
                else f"发现 {len(possible_matches)} 笔同日同额且描述相近的已有记录，请核对后决定是否入账"
                if possible_matches
                else "发现其他待处理候选中有同日同额且文本相近的记录，请核对后决定是否入账"
            )
            warnings.append(
                {
                    "field": "fingerprint",
                    "code": "POSSIBLE_DUPLICATE",
                    "message": message,
                }
            )
            evidence["possible_duplicate_transaction_ids"] = transaction_ids
            evidence["possible_duplicate_fact_targets"] = [
                {"transaction_id": transaction_id, "fact_id": fact_id}
                for transaction_id, fact_id in fact_target_ids
            ]
            evidence["possible_duplicate_candidate_ids"] = sorted(
                row.id for row in sibling_matches
            )
            if effective_overflow is not None:
                evidence["possible_duplicate_bucket_watermark"] = (
                    effective_overflow.as_evidence()
                )
            candidate.duplicate_transaction_id = (
                possible_matches[0].id
                if possible_matches
                else transaction_ids[0] if transaction_ids else None
            )
            candidate.status = "possible_duplicate"
        else:
            candidate.duplicate_transaction_id = None
            candidate.status = "needs_review" if warnings else "ready"
        candidate.evidence = evidence
        candidate.warnings = warnings
    # SessionLocal deliberately disables autoflush.  Persist the final
    # duplicate-review statuses before refresh_batch_counts() queries them;
    # otherwise the response can show stale yellow/duplicate totals even
    # though the candidates themselves were already recomputed.
    db.flush()


def _candidate_has_category_question(candidate: FinancialTransactionCandidate) -> bool:
    return (
        candidate.direction in {"income", "expense"}
        and (
            candidate.category_id is None
            or any(
                _candidate_has_issue(candidate, code)
                for code in CATEGORY_REVIEW_ISSUE_CODES
            )
        )
    )


def _candidate_can_confirm_unknown_merchant(
    candidate: FinancialTransactionCandidate,
) -> bool:
    """Return whether one explicit acknowledgement can resolve merchant only.

    Fail closed: structured accounting fields must already be complete, both
    merchant text fields must truly be blank, and *every* remaining prompt must
    be one of the merchant/alignment prompts above.  This keeps unrelated
    category, amount, direction and duplicate questions visible.
    """

    merchant = (candidate.merchant or "").strip()
    description = (candidate.description or "").strip()
    if merchant or description:
        return False
    if candidate.direction not in {"income", "expense"}:
        return False
    amount = Decimal(candidate.amount) if candidate.amount is not None else None
    if amount is None or amount <= 0:
        return False
    if (
        candidate.transaction_date is None
        or candidate.currency != "CNY"
        or candidate.category_id is None
    ):
        return False
    issues = [
        issue
        for issue in [*(candidate.validation_errors or []), *(candidate.warnings or [])]
        if isinstance(issue, dict)
    ]
    if not issues:
        return False
    issue_codes = {str(issue.get("code") or "") for issue in issues}
    return bool(issue_codes) and issue_codes.issubset(
        UNKNOWN_MERCHANT_REVIEW_ISSUE_CODES
    )


def _validate_unknown_merchant_resolutions_locked(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    data: FinancialImportBatchReviewResolutionRequest,
) -> dict[int, FinancialTransactionCandidate]:
    selected = {
        item.candidate_id: item.expected_version
        for item in data.confirm_unknown_merchant_candidates
    }
    if not selected:
        return {}
    rows = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.id.in_(sorted(selected)),
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    ).order_by(FinancialTransactionCandidate.id.asc()).with_for_update().all()
    candidates = {row.id: row for row in rows}
    if set(candidates) != set(selected):
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_unknown_merchant_selection_changed",
            "交易对方未知候选已移出当前批次，请刷新后重试",
        )
    for candidate_id, expected_version in selected.items():
        candidate = candidates[candidate_id]
        if candidate.version != expected_version:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_stale_candidate",
                f"候选 #{candidate_id} 已更新，请刷新后重试",
            )
        if (
            candidate.status not in ACTIONABLE_CANDIDATE_STATUSES
            or not _candidate_can_confirm_unknown_merchant(candidate)
        ):
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_unknown_merchant_selection_changed",
                f"候选 #{candidate_id} 已不是仅待确认交易对方未知的状态",
            )
    return candidates


def _validate_category_resolutions_locked(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    data: FinancialImportBatchReviewResolutionRequest,
) -> tuple[dict[int, FinancialTransactionCandidate], dict[int, Any]]:
    """Lock and validate every explicitly selected candidate before mutation."""

    selected = {
        item.candidate_id: (item.expected_version, resolution.category_id)
        for resolution in data.category_resolutions
        for item in resolution.candidates
    }
    if not selected:
        return {}, {}
    rows = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.id.in_(sorted(selected)),
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    ).order_by(FinancialTransactionCandidate.id.asc()).with_for_update().all()
    candidates = {row.id: row for row in rows}
    if set(candidates) != set(selected):
        db.rollback()
        raise import_error(
            409,
            "cashflow_import_category_selection_changed",
            "分类候选已移出当前批次或不再可处理，请刷新后重试",
        )
    for candidate_id, (expected_version, _category_id) in selected.items():
        candidate = candidates[candidate_id]
        if candidate.version != expected_version:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_stale_candidate",
                f"候选 #{candidate_id} 已更新，请刷新后重试",
            )
        if candidate.status not in {"needs_review", "possible_duplicate", "invalid"}:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_category_selection_changed",
                f"候选 #{candidate_id} 已不是待分类状态",
            )
        if not _candidate_has_category_question(candidate):
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_category_selection_changed",
                f"候选 #{candidate_id} 已没有待确认的分类问题",
            )

    categories_by_candidate: dict[int, Any] = {}
    for resolution in data.category_resolutions:
        group = [candidates[item.candidate_id] for item in resolution.candidates]
        directions = {candidate.direction for candidate in group}
        if len(directions) != 1 or next(iter(directions)) not in {"income", "expense"}:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_category_direction_mismatch",
                "同一批量分类组只能包含同一收支方向的候选",
            )
        direction = next(iter(directions))
        try:
            category = get_available_category(
                db,
                user_id=user_id,
                category_id=resolution.category_id,
                direction=direction,
            )
        except HTTPException as exc:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_category_resolution_invalid",
                str(exc.detail),
            ) from exc
        for candidate in group:
            categories_by_candidate[candidate.id] = category
    return candidates, categories_by_candidate


def apply_batch_review_resolutions(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    data: FinancialImportBatchReviewResolutionRequest,
) -> dict[str, Any]:
    """Atomically resolve repeated OCR questions without confirming entries."""

    lock_financial_ledger_owner(
        db,
        user_id=user_id,
        conflict_code="cashflow_import_state_conflict",
    )
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.version != data.expected_batch_version:
        raise import_error(409, "cashflow_import_stale_batch", "导入批次已更新，请刷新后继续")
    if batch.status not in {"review_ready", "completed"}:
        raise import_error(409, "cashflow_import_state_conflict", "该批次当前不能批量核对")

    selected_category_candidates, categories_by_candidate = (
        _validate_category_resolutions_locked(
            db,
            user_id=user_id,
            batch_id=batch_id,
            data=data,
        )
    )
    selected_unknown_merchant_candidates = (
        _validate_unknown_merchant_resolutions_locked(
            db,
            user_id=user_id,
            batch_id=batch_id,
            data=data,
        )
    )
    changed_ids: set[int] = set()
    date_context_repaired_count = 0
    if data.repair_date_context or data.inferred_year is not None:
        repaired_ids, date_context_repaired_count = _repair_existing_date_contexts_locked(
            db,
            batch=batch,
            repair_missing_dates=data.repair_date_context,
        )
        changed_ids.update(repaired_ids)

    candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
        FinancialTransactionCandidate.status.in_(ACTIONABLE_CANDIDATE_STATUSES),
    ).order_by(FinancialTransactionCandidate.row_number.asc()).with_for_update().all()
    resolved_dates: dict[int, date] = {}
    if data.inferred_year is not None:
        for candidate in candidates:
            if not _candidate_has_issue(candidate, "PROGRAM_YEAR_INFERRED"):
                continue
            inference = (candidate.evidence or {}).get("date_year_inference")
            if not (
                isinstance(inference, dict)
                and inference.get("status") == "pending"
                and inference.get("source_has_explicit_year") is False
            ):
                # Old/unlocatable guesses stay in review instead of being
                # silently accepted by the shared-year action.
                continue
            if candidate.transaction_date is None:
                db.rollback()
                raise import_error(
                    409,
                    "cashflow_import_year_resolution_invalid",
                    "批次中有候选尚无月日，无法批量确认年份",
                )
            try:
                resolved_dates[candidate.id] = date(
                    data.inferred_year,
                    candidate.transaction_date.month,
                    candidate.transaction_date.day,
                )
            except ValueError as exc:
                db.rollback()
                raise import_error(
                    409,
                    "cashflow_import_year_resolution_invalid",
                    f"{data.inferred_year} 年无法承载批次中的 {candidate.transaction_date.month} 月 {candidate.transaction_date.day} 日",
                ) from exc
    currency_candidates: set[int] = set()
    if data.confirm_currency == "CNY":
        currency_candidates = {
            candidate.id
            for candidate in candidates
            if _candidate_has_issue(candidate, "PROGRAM_CURRENCY_INFERRED")
            or (
                candidate.currency in {None, "", "UNK"}
                and _candidate_has_issue(candidate, "CURRENCY_REQUIRED")
            )
        }
        invalid_currency = next(
            (
                candidate
                for candidate in candidates
                if _candidate_has_issue(candidate, "PROGRAM_CURRENCY_INFERRED")
                and candidate.currency != "CNY"
            ),
            None,
        )
        if invalid_currency is not None:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_currency_resolution_invalid",
                "批次中有候选并非程序提议的人民币，不能批量确认",
            )
    year_updated_count = 0
    currency_confirmed_count = 0
    category_updated_count = 0
    unknown_merchant_confirmed_count = 0
    confirmed_at = datetime.utcnow()
    for candidate in candidates:
        evidence = dict(candidate.evidence or {})
        warnings = [dict(issue) for issue in (candidate.warnings or [])]
        changed = candidate.id in changed_ids
        if data.inferred_year is not None and candidate.id in resolved_dates:
            resolved_date = resolved_dates[candidate.id]
            previous_date = candidate.transaction_date
            candidate.transaction_date = resolved_date
            if previous_date != resolved_date and candidate.occurred_at is not None:
                candidate.occurred_at = None
            warnings = [
                issue for issue in warnings if issue.get("code") != "PROGRAM_YEAR_INFERRED"
            ]
            inference = evidence.get("date_year_inference")
            evidence["date_year_inference"] = {
                **(inference if isinstance(inference, dict) else {}),
                "month": resolved_date.month,
                "day": resolved_date.day,
                "proposed_year": previous_date.year,
                "confirmed_year": data.inferred_year,
                "status": "confirmed",
                "confirmed_at": confirmed_at.isoformat(),
                "source_has_explicit_year": False,
            }
            review = dict(evidence.get("batch_review_resolutions") or {})
            review["inferred_year"] = {
                "value": data.inferred_year,
                "confirmed_at": confirmed_at.isoformat(),
                "previous_date": previous_date.isoformat(),
            }
            evidence["batch_review_resolutions"] = review
            modified = set(evidence.get("user_modified_fields") or [])
            modified.add("transaction_date")
            evidence["user_modified_fields"] = sorted(modified)
            year_updated_count += 1
            changed = True
        if data.confirm_currency == "CNY" and candidate.id in currency_candidates:
            had_required_error = _candidate_has_issue(candidate, "CURRENCY_REQUIRED")
            candidate.currency = "CNY"
            warnings = [
                issue
                for issue in warnings
                if issue.get("code") != "PROGRAM_CURRENCY_INFERRED"
            ]
            if had_required_error:
                candidate.validation_errors = [
                    dict(issue)
                    for issue in (candidate.validation_errors or [])
                    if issue.get("code") != "CURRENCY_REQUIRED"
                ]
                source_errors = evidence.get("source_validation_errors")
                if isinstance(source_errors, list):
                    evidence["source_validation_errors"] = [
                        dict(issue)
                        for issue in source_errors
                        if isinstance(issue, dict)
                        and issue.get("code") != "CURRENCY_REQUIRED"
                    ]
            review = dict(evidence.get("batch_review_resolutions") or {})
            review["currency"] = {
                "value": "CNY",
                "confirmed_at": confirmed_at.isoformat(),
            }
            evidence["batch_review_resolutions"] = review
            modified = set(evidence.get("user_modified_fields") or [])
            modified.add("currency")
            evidence["user_modified_fields"] = sorted(modified)
            currency_confirmed_count += 1
            changed = True
        if candidate.id in selected_category_candidates:
            category = categories_by_candidate[candidate.id]
            candidate.category_id = category.id
            candidate.category_name = category.name
            candidate.validation_errors = [
                dict(issue)
                for issue in (candidate.validation_errors or [])
                if issue.get("code") not in CATEGORY_REVIEW_ISSUE_CODES
            ]
            warnings = [
                issue
                for issue in warnings
                if issue.get("code") not in CATEGORY_REVIEW_ISSUE_CODES
            ]
            source_errors = evidence.get("source_validation_errors")
            if isinstance(source_errors, list):
                evidence["source_validation_errors"] = [
                    dict(issue)
                    for issue in source_errors
                    if isinstance(issue, dict)
                    and issue.get("code") not in CATEGORY_REVIEW_ISSUE_CODES
                ]
            review = dict(evidence.get("batch_review_resolutions") or {})
            review["category"] = {
                "category_id": category.id,
                "category_name": category.name,
                "confirmed_at": confirmed_at.isoformat(),
            }
            evidence["batch_review_resolutions"] = review
            suggestion = evidence.get("category_suggestion")
            if isinstance(suggestion, dict):
                evidence["category_suggestion"] = {
                    **suggestion,
                    "confirmed_category_id": category.id,
                    "confirmed_category_name": category.name,
                    "confirmed_at": confirmed_at.isoformat(),
                }
            modified = set(evidence.get("user_modified_fields") or [])
            modified.add("category_id")
            evidence["user_modified_fields"] = sorted(modified)
            category_updated_count += 1
            changed = True
        if candidate.id in selected_unknown_merchant_candidates:
            candidate.validation_errors = [
                dict(issue)
                for issue in (candidate.validation_errors or [])
                if issue.get("code") not in UNKNOWN_MERCHANT_REVIEW_ISSUE_CODES
            ]
            warnings = [
                issue
                for issue in warnings
                if issue.get("code") not in UNKNOWN_MERCHANT_REVIEW_ISSUE_CODES
            ]
            source_errors = evidence.get("source_validation_errors")
            if isinstance(source_errors, list):
                evidence["source_validation_errors"] = [
                    dict(issue)
                    for issue in source_errors
                    if isinstance(issue, dict)
                    and issue.get("code") not in UNKNOWN_MERCHANT_REVIEW_ISSUE_CODES
                ]
            evidence["merchant_resolution"] = "confirmed_unknown"
            evidence["merchant_resolution_confirmed_at"] = confirmed_at.isoformat()
            if evidence.get("ai_alignment_review_required") is True:
                evidence["ai_alignment_review_required"] = False
                evidence["ai_alignment_resolution"] = {
                    "value": "merchant_confirmed_unknown",
                    "confirmed_at": confirmed_at.isoformat(),
                }
            review = dict(evidence.get("batch_review_resolutions") or {})
            review["merchant"] = {
                "value": "confirmed_unknown",
                "confirmed_at": confirmed_at.isoformat(),
            }
            evidence["batch_review_resolutions"] = review
            unknown_merchant_confirmed_count += 1
            changed = True
        if changed:
            candidate.evidence = evidence
            candidate.warnings = warnings
            changed_ids.add(candidate.id)

    changed_candidates = [row for row in candidates if row.id in changed_ids]
    if changed_candidates:
        _recompute_bulk_review_candidates(
            db,
            candidates=changed_candidates,
            user_id=user_id,
        )
        batch.updated_at = confirmed_at
        refresh_batch_counts(db, batch)
        try:
            db.commit()
        except (IntegrityError, StaleDataError) as exc:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_stale_batch",
                "批量核对期间批次已更新，本次没有产生部分修改",
            ) from exc
    else:
        db.rollback()
        batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id)
        candidates = []

    if changed_candidates:
        db.refresh(batch)
        for candidate in changed_candidates:
            db.refresh(candidate)
    return {
        "batch": batch_payload(batch),
        "candidates": candidate_payloads(
            db,
            batch=batch,
            candidates=changed_candidates,
        ),
        "applied_candidate_ids": sorted(changed_ids),
        "year_updated_count": year_updated_count,
        "currency_confirmed_count": currency_confirmed_count,
        "date_context_repaired_count": date_context_repaired_count,
        "category_updated_count": category_updated_count,
        "unknown_merchant_confirmed_count": unknown_merchant_confirmed_count,
        "ready_count": sum(row.status == "ready" for row in changed_candidates),
        "remaining_review_count": (
            batch.review_count
            + batch.possible_duplicate_count
            + batch.invalid_count
        ),
    }


def _candidate_source_evidence_entries(
    candidate: FinancialTransactionCandidate,
) -> list[dict[str, Any]]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    sources = [
        dict(source)
        for source in (evidence.get("source_slices") or [])
        if isinstance(source, dict) and isinstance(source.get("slice_sequence"), int)
    ]
    if not sources and isinstance(evidence.get("slice_sequence"), int):
        sources.append(
            {
                "slice_sequence": evidence["slice_sequence"],
                "source_locator": evidence.get("source_locator") or {},
                "candidate_region": evidence.get("candidate_region"),
                "ocr_line_index": evidence.get("ocr_line_index"),
            }
        )
    unique: dict[int, dict[str, Any]] = {}
    for source in sources:
        unique.setdefault(int(source["slice_sequence"]), source)
    return [unique[key] for key in sorted(unique)]


def get_candidate_evidence_payload(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    candidate_id: int,
) -> dict[str, Any]:
    get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    candidate = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.id == candidate_id,
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    ).first()
    if candidate is None:
        raise import_error(404, "cashflow_import_candidate_not_found", "导入候选不存在")
    source_entries = _candidate_source_evidence_entries(candidate)
    sequences = [int(source["slice_sequence"]) for source in source_entries]
    artifacts = {
        artifact.sequence_number: artifact
        for artifact in db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == user_id,
            FinancialRecognitionArtifact.batch_id == batch_id,
            FinancialRecognitionArtifact.artifact_type == "image_slice",
            FinancialRecognitionArtifact.sequence_number.in_(sequences or [-1]),
        ).all()
    }
    ocr_artifacts = {
        artifact.sequence_number: artifact
        for artifact in db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == user_id,
            FinancialRecognitionArtifact.batch_id == batch_id,
            FinancialRecognitionArtifact.artifact_type == "ocr_text",
            FinancialRecognitionArtifact.sequence_number.in_(sequences or [-1]),
        ).all()
    }
    batch_candidates = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    ).order_by(FinancialTransactionCandidate.row_number.asc()).all()
    payload_sources: list[dict[str, Any]] = []
    for source in source_entries:
        sequence = int(source["slice_sequence"])
        artifact = artifacts.get(sequence)
        if artifact is None or artifact.attachment_version_id is None:
            continue
        locator = artifact.source_locator if isinstance(artifact.source_locator, dict) else {}
        ocr_artifact = ocr_artifacts.get(sequence)
        lines = _normalized_ocr_lines(
            ocr_artifact.content_text if ocr_artifact is not None else ""
        )
        same_slice_candidates = [
            row
            for row in batch_candidates
            if any(
                item.get("slice_sequence") == sequence
                for item in _candidate_source_evidence_entries(row)
            )
        ]
        located = _locate_candidate_ocr_lines(
            same_slice_candidates,
            lines=lines,
        )
        line_counts: dict[int, int] = {}
        for line_index, _method in located:
            if line_index is not None:
                line_counts[line_index] = line_counts.get(line_index, 0) + 1
        ordered_unique_lines = sorted(
            line_index for line_index, count in line_counts.items() if count == 1
        )
        target_position = next(
            (
                index
                for index, row in enumerate(same_slice_candidates)
                if row.id == candidate.id
            ),
            None,
        )
        target_line_index = (
            located[target_position][0]
            if target_position is not None
            else None
        )
        region = _approximate_candidate_region(
            locator=locator,
            line_index=target_line_index,
            candidate_index=(
                ordered_unique_lines.index(target_line_index) + 1
                if target_line_index in ordered_unique_lines
                else None
            ),
            candidate_total=len(ordered_unique_lines) or None,
        )
        width = max(1, int(locator.get("normalized_width") or region.get("right") or 1))
        height = max(1, int(locator.get("normalized_height") or region.get("bottom") or 1))
        payload_sources.append(
            {
                "slice_sequence": sequence,
                "source_image_sequence": int(locator.get("source_image_sequence") or 1),
                "source_image_slice_sequence": int(
                    locator.get("source_image_slice_sequence") or sequence
                ),
                "source_image_slice_total": int(
                    locator.get("source_image_slice_total") or len(artifacts) or 1
                ),
                "source_pixel_top": locator.get("source_pixel_top"),
                "source_pixel_bottom": locator.get("source_pixel_bottom"),
                "slice_width": width,
                "slice_height": height,
                "region": region,
            }
        )
    return {
        "candidate_id": candidate.id,
        "batch_id": candidate.batch_id,
        "evidence_quote": (candidate.evidence or {}).get("evidence_quote"),
        "sources": payload_sources,
    }


def get_candidate_evidence_slice(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    candidate_id: int,
    sequence_number: int,
) -> tuple[Path, str, str]:
    get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    candidate = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.id == candidate_id,
        FinancialTransactionCandidate.user_id == user_id,
        FinancialTransactionCandidate.batch_id == batch_id,
    ).first()
    if candidate is None:
        raise import_error(404, "cashflow_import_candidate_not_found", "导入候选不存在")
    allowed_sequences = {
        int(source["slice_sequence"])
        for source in _candidate_source_evidence_entries(candidate)
    }
    if sequence_number not in allowed_sequences:
        raise import_error(404, "cashflow_import_evidence_not_found", "该候选没有对应的识别切片")
    artifact = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
        FinancialRecognitionArtifact.sequence_number == sequence_number,
    ).first()
    if artifact is None or artifact.attachment_version_id is None:
        raise import_error(404, "cashflow_import_evidence_not_found", "识别切片已不存在")
    attachment = db.query(PersonalAttachmentVersion).filter(
        PersonalAttachmentVersion.id == artifact.attachment_version_id,
        PersonalAttachmentVersion.user_id == user_id,
    ).first()
    if attachment is None:
        raise import_error(404, "cashflow_import_evidence_not_found", "识别切片已不存在")
    try:
        path = resolve_attachment_path(attachment)
    except FileNotFoundError as exc:
        raise import_error(404, "cashflow_import_evidence_missing", "识别切片文件已丢失") from exc
    return (
        path,
        artifact.content_type or attachment.content_type or "image/png",
        f"cashflow-candidate-{candidate.id}-slice-{sequence_number}.png",
    )


def get_ocr_slice_detail_payload(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    sequence_number: int,
) -> dict[str, Any]:
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    artifact = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
        FinancialRecognitionArtifact.sequence_number == sequence_number,
    ).first()
    if artifact is None:
        raise import_error(404, "cashflow_import_evidence_not_found", "识别切片不存在")
    ocr_artifact = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "ocr_text",
        FinancialRecognitionArtifact.sequence_number == sequence_number,
        FinancialRecognitionArtifact.status == "ready",
    ).first()
    progress = _recognition_progress(db, batch=batch)
    slice_progress = next(
        (
            item
            for item in progress["slices"]
            if item["sequence_number"] == sequence_number
        ),
        None,
    )
    if slice_progress is None:
        raise import_error(404, "cashflow_import_evidence_not_found", "识别切片不存在")
    locator = artifact.source_locator if isinstance(artifact.source_locator, dict) else {}
    return {
        "batch_id": batch_id,
        "slice": slice_progress,
        "slice_width": max(1, int(locator.get("normalized_width") or 1)),
        "slice_height": max(1, int(locator.get("normalized_height") or 1)),
        "ocr_text": ocr_artifact.content_text if ocr_artifact is not None else None,
        "image_available": artifact.attachment_version_id is not None,
    }


def get_ocr_slice_image(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    sequence_number: int,
) -> tuple[Path, str, str]:
    get_owned_batch(db, user_id=user_id, batch_id=batch_id)
    artifact = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
        FinancialRecognitionArtifact.sequence_number == sequence_number,
    ).first()
    if artifact is None or artifact.attachment_version_id is None:
        raise import_error(404, "cashflow_import_evidence_not_found", "识别切片已不存在")
    attachment = db.query(PersonalAttachmentVersion).filter(
        PersonalAttachmentVersion.id == artifact.attachment_version_id,
        PersonalAttachmentVersion.user_id == user_id,
    ).first()
    if attachment is None:
        raise import_error(404, "cashflow_import_evidence_not_found", "识别切片已不存在")
    try:
        path = resolve_attachment_path(attachment)
    except FileNotFoundError as exc:
        raise import_error(404, "cashflow_import_evidence_missing", "识别切片文件已丢失") from exc
    return (
        path,
        artifact.content_type or attachment.content_type or "image/png",
        f"cashflow-batch-{batch_id}-slice-{sequence_number}.png",
    )


def _adjacent_candidate_source(
    evidence: dict[str, Any],
    *,
    candidate_sequence: int | None,
) -> dict[str, Any] | None:
    source_slices = list(evidence.get("source_slices") or [])
    if not source_slices and isinstance(evidence.get("slice_sequence"), int):
        source_slices.append(
            {
                "slice_sequence": evidence["slice_sequence"],
                "source_locator": evidence.get("source_locator") or {},
            }
        )
    return next(
        (
            source
            for source in reversed(source_slices)
            if isinstance(source, dict)
            and isinstance(source.get("slice_sequence"), int)
            and isinstance(candidate_sequence, int)
            and abs(source["slice_sequence"] - candidate_sequence) == 1
        ),
        None,
    )


_OVERLAP_TIME_PATTERN = re.compile(
    r"(?<!\d)(?P<hour>[01]?\d|2[0-3])[:：](?P<minute>[0-5]\d)(?:[:：](?P<second>[0-5]\d))?(?!\d)"
)


def _normalized_overlap_time(
    value: datetime | None,
    *,
    evidence: dict[str, Any] | None = None,
) -> tuple[int, int, int] | None:
    if value is None:
        quote = (evidence or {}).get("evidence_quote")
        match = _OVERLAP_TIME_PATTERN.search(str(quote or ""))
        if match is None:
            return None
        return (
            int(match.group("hour")),
            int(match.group("minute")),
            int(match.group("second") or 0),
        )
    return value.hour, value.minute, value.second


def _normalized_merchant_core(value: str | None) -> str:
    normalized = _normalized_overlap_text(value)
    for prefix in (
        "生活缴费",
        "其他支出",
        "其他收入",
        "餐饮",
        "交通",
        "医疗",
        "购物",
        "娱乐",
        "通讯",
        "转账",
    ):
        if normalized.startswith(prefix) and len(normalized) - len(prefix) >= 3:
            normalized = normalized[len(prefix):]
            break
    return normalized


def _merchant_cores_match(left: str | None, right: str | None) -> bool:
    left_core = _normalized_merchant_core(left)
    right_core = _normalized_merchant_core(right)
    if not left_core or not right_core:
        return False
    if left_core == right_core:
        return True
    shorter, longer = sorted((left_core, right_core), key=len)
    return (
        len(shorter) >= 4
        and shorter in longer
        and len(shorter) / len(longer) >= 0.70
    )


def _absolute_candidate_region(
    evidence: dict[str, Any],
    source: dict[str, Any],
) -> tuple[int, int, int] | None:
    locator = source.get("source_locator")
    if not isinstance(locator, dict):
        return None
    region = source.get("candidate_region")
    if not isinstance(region, dict):
        if source.get("slice_sequence") == evidence.get("slice_sequence"):
            region = evidence.get("candidate_region")
    if not isinstance(region, dict):
        return None
    if region.get("coordinate_space") != "slice_pixels":
        return None
    if region.get("precision") not in {"ocr_text_line", "approximate"}:
        return None
    normalized_top = locator.get("normalized_top")
    region_top = region.get("top")
    region_bottom = region.get("bottom")
    image_sequence = locator.get("source_image_sequence", 1)
    if not all(isinstance(value, int) for value in (normalized_top, region_top, region_bottom, image_sequence)):
        return None
    if region_bottom <= region_top:
        return None
    return int(image_sequence), int(normalized_top) + int(region_top), int(normalized_top) + int(region_bottom)


def _candidate_regions_clearly_overlap(
    row_evidence: dict[str, Any],
    row_source: dict[str, Any],
    candidate_evidence: dict[str, Any],
    candidate_source: dict[str, Any],
) -> bool:
    row_region = _absolute_candidate_region(row_evidence, row_source)
    candidate_region = _absolute_candidate_region(candidate_evidence, candidate_source)
    if row_region is None or candidate_region is None or row_region[0] != candidate_region[0]:
        return False
    overlap = min(row_region[2], candidate_region[2]) - max(row_region[1], candidate_region[1])
    minimum_height = min(row_region[2] - row_region[1], candidate_region[2] - candidate_region[1])
    return overlap >= 8 and overlap / max(1, minimum_height) >= 0.40


def _cross_image_overlap_cases(
    db: Session,
    *,
    batch: FinancialImportBatch,
    parsed: list[ParsedCandidate],
) -> list[dict[str, Any]]:
    existing = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == batch.user_id,
        FinancialTransactionCandidate.batch_id == batch.id,
        FinancialTransactionCandidate.status.in_(
            {*ACTIONABLE_CANDIDATE_STATUSES, "exact_duplicate"}
        ),
    ).all()
    cases: list[dict[str, Any]] = []
    for candidate in parsed:
        candidate_sequence = candidate.evidence.get("slice_sequence")
        candidate_locator = candidate.evidence.get("source_locator")
        if not isinstance(candidate_locator, dict):
            continue
        candidate_image = candidate_locator.get("source_image_sequence", 1)
        for row in existing:
            row_evidence = dict(row.evidence or {})
            adjacent_source = _adjacent_candidate_source(
                row_evidence,
                candidate_sequence=candidate_sequence if isinstance(candidate_sequence, int) else None,
            )
            if adjacent_source is None:
                continue
            row_locator = adjacent_source.get("source_locator")
            if not isinstance(row_locator, dict):
                row_locator = {}
            row_image = row_locator.get("source_image_sequence", 1)
            if row_image == candidate_image:
                continue
            if (
                row.direction != candidate.direction
                or row.amount != candidate.amount
                or row.transaction_date != candidate.transaction_date
                or row.amount is None
                or row.transaction_date is None
            ):
                continue
            if not duplicate_text_is_similar(
                row.merchant,
                row.description,
                merchant_b=candidate.merchant,
                description_b=candidate.description,
            ):
                continue
            row_merchant = _normalized_overlap_text(row.merchant)
            row_description = _normalized_overlap_text(row.description)
            candidate_merchant = _normalized_overlap_text(candidate.merchant)
            candidate_description = _normalized_overlap_text(candidate.description)
            row_quote = _normalized_overlap_text(row_evidence.get("evidence_quote"))
            candidate_quote = _normalized_overlap_text(candidate.evidence.get("evidence_quote"))
            merchant_conflicts = bool(
                row_merchant and candidate_merchant and row_merchant != candidate_merchant
            )
            description_conflicts = bool(
                row_description and candidate_description and row_description != candidate_description
            )
            exact_business_text = bool(
                (row_merchant and row_merchant == candidate_merchant)
                or (row_description and row_description == candidate_description)
            )
            exact_quote = bool(row_quote and row_quote == candidate_quote)
            if exact_business_text and exact_quote and not merchant_conflicts and not description_conflicts:
                continue
            cases.append(
                {
                    "current_row_number": candidate.row_number,
                    "prior_candidate_id": row.id,
                    "direction": candidate.direction,
                    "amount": format(candidate.amount, "f") if candidate.amount is not None else None,
                    "transaction_date": candidate.transaction_date.isoformat() if candidate.transaction_date else None,
                    "current_merchant": redact_cashflow_text(candidate.merchant or "", max_length=120),
                    "current_description": redact_cashflow_text(candidate.description or "", max_length=200),
                    "prior_merchant": redact_cashflow_text(row.merchant or "", max_length=120),
                    "prior_description": redact_cashflow_text(row.description or "", max_length=200),
                    "program_reason": "相邻截图交界处日期、金额和方向相同，交易文本相似但不完全一致",
                }
            )
            if len(cases) >= 20:
                return cases
    return cases


def _enrich_cross_image_overlap_with_ai(
    parsed: list[ParsedCandidate],
    *,
    cases: list[dict[str, Any]],
    user_id: int,
    expected_data_epoch: int,
) -> list[ParsedCandidate]:
    if not cases:
        return parsed
    from app.services.payslip_intake_service import _call_payslip_llm

    prompt = """你是收支守护的跨截图重复判断助手。程序已经先按截图顺序、日期、金额、方向和文本找到相似候选。
你只能评议是否可能为同一笔交易，不能合并、不能写账、不能代替用户确认。信息不足必须输出 uncertain。
只输出严格 JSON：{"assessments":[{"current_row_number":3001,"prior_candidate_id":12,"assessment":"likely_same|likely_different|uncertain","reason":"一句可核对理由"}]}
候选：
{cases}
""".replace("{cases}", json.dumps(cases, ensure_ascii=False))
    output = _call_payslip_llm(
        prompt,
        user_id=user_id,
        expected_data_epoch=expected_data_epoch,
        feature="cashflow_cross_image_duplicate_reasoning",
        max_tokens=1600,
    )
    assessments_by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    if output:
        text = output.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            payload = None
        raw_assessments = payload.get("assessments") if isinstance(payload, dict) else None
        allowed_pairs = {
            (item["current_row_number"], item["prior_candidate_id"])
            for item in cases
        }
        if isinstance(raw_assessments, list):
            for item in raw_assessments[:20]:
                if not isinstance(item, dict):
                    continue
                key = (item.get("current_row_number"), item.get("prior_candidate_id"))
                verdict = item.get("assessment")
                if key not in allowed_pairs or verdict not in {"likely_same", "likely_different", "uncertain"}:
                    continue
                reason = re.sub(r"\s+", " ", str(item.get("reason") or "")).strip()[:240]
                assessments_by_pair[(int(key[0]), int(key[1]))] = {
                    "prior_candidate_id": int(key[1]),
                    "assessment": verdict,
                    "reason": reason or "AI 未提供可核对理由",
                    "ai_status": "completed",
                }

    contextualized: list[ParsedCandidate] = []
    cases_by_row: dict[int, list[dict[str, Any]]] = {}
    for item in cases:
        cases_by_row.setdefault(int(item["current_row_number"]), []).append(item)
    for candidate in parsed:
        row_cases = cases_by_row.get(candidate.row_number)
        if not row_cases:
            contextualized.append(candidate)
            continue
        assessments = [
            assessments_by_pair.get(
                (candidate.row_number, int(item["prior_candidate_id"])),
                {
                    "prior_candidate_id": int(item["prior_candidate_id"]),
                    "assessment": "uncertain",
                    "reason": "AI 未返回可用判断，需要人工核对",
                    "ai_status": "unavailable",
                },
            )
            for item in row_cases
        ]
        primary = next(
            (item for item in assessments if item["assessment"] == "likely_same"),
            assessments[0],
        )
        verdict_copy = {
            "likely_same": "AI 认为较可能是同一笔",
            "likely_different": "AI 认为较可能不是同一笔",
            "uncertain": "AI 仍无法确定是否同一笔",
        }[primary["assessment"]]
        warning = {
            "field": "fingerprint",
            "code": "CROSS_IMAGE_DUPLICATE_AI_REVIEW",
            "message": (
                f"程序发现相邻截图交界处的疑似同笔交易；{verdict_copy}："
                f"{primary['reason']}。系统不会自动合并或入账，请人工确认"
            ),
        }
        contextualized.append(
            replace(
                candidate,
                evidence={
                    **candidate.evidence,
                    "cross_image_duplicate_assessments": assessments,
                },
                warnings=[warning, *candidate.warnings],
            )
        )
    return contextualized


def _merge_exact_overlap_candidates(
    db: Session,
    *,
    batch: FinancialImportBatch,
    parsed: list[ParsedCandidate],
) -> list[ParsedCandidate]:
    """Collapse only deterministic cross-slice repeats and retain both proofs.

    Similar-but-not-identical rows deliberately remain for the normal fuzzy
    duplicate gate. This helper never turns an uncertain match into an
    automatic merge.
    """

    existing = db.query(FinancialTransactionCandidate).filter(
        FinancialTransactionCandidate.user_id == batch.user_id,
        FinancialTransactionCandidate.batch_id == batch.id,
        FinancialTransactionCandidate.status.in_(
            {*ACTIONABLE_CANDIDATE_STATUSES, "exact_duplicate"}
        ),
    ).all()
    remaining = []
    for candidate in parsed:
        candidate_merchant = _normalized_overlap_text(candidate.merchant)
        candidate_description = _normalized_overlap_text(candidate.description)
        candidate_time = _normalized_overlap_time(
            candidate.occurred_at,
            evidence=candidate.evidence,
        )
        candidate_currency = str(candidate.currency or "").strip().upper()
        candidate_sources = [
            source
            for source in (candidate.evidence.get("source_slices") or [])
            if isinstance(source, dict)
        ]
        candidate_source = next(
            (
                source
                for source in candidate_sources
                if source.get("slice_sequence") == candidate.evidence.get("slice_sequence")
            ),
            candidate_sources[0] if candidate_sources else {
                "slice_sequence": candidate.evidence.get("slice_sequence"),
                "source_locator": candidate.evidence.get("source_locator") or {},
                "candidate_region": candidate.evidence.get("candidate_region"),
            },
        )
        match = None
        matched_source_locator: dict[str, Any] = {}
        for row in existing:
            row_evidence = dict(row.evidence or {})
            candidate_sequence = candidate.evidence.get("slice_sequence")
            adjacent_source = _adjacent_candidate_source(
                row_evidence,
                candidate_sequence=candidate_sequence if isinstance(candidate_sequence, int) else None,
            )
            if adjacent_source is None:
                continue
            if (
                row.direction != candidate.direction
                or row.amount != candidate.amount
                or row.transaction_date != candidate.transaction_date
                or str(row.currency or "").strip().upper() != candidate_currency
            ):
                continue
            row_time = _normalized_overlap_time(
                row.occurred_at,
                evidence=row_evidence,
            )
            if row_time is None or candidate_time is None or row_time != candidate_time:
                continue
            row_merchant = _normalized_overlap_text(row.merchant)
            row_description = _normalized_overlap_text(row.description)
            row_quote = _normalized_overlap_text(row_evidence.get("evidence_quote"))
            candidate_quote = _normalized_overlap_text(candidate.evidence.get("evidence_quote"))
            merchant_conflicts = bool(row_merchant and candidate_merchant and row_merchant != candidate_merchant)
            description_conflicts = bool(
                row_description and candidate_description and row_description != candidate_description
            )
            exact_business_text = bool(
                (row_merchant and row_merchant == candidate_merchant)
                or (row_description and row_description == candidate_description)
            )
            exact_quote = bool(row_quote and row_quote == candidate_quote)
            matched_source_locator = (
                adjacent_source.get("source_locator")
                if isinstance(adjacent_source.get("source_locator"), dict)
                else {}
            )
            candidate_locator = (
                candidate_source.get("source_locator")
                if isinstance(candidate_source.get("source_locator"), dict)
                else {}
            )
            same_source_image = (
                matched_source_locator.get("source_image_sequence", 1)
                == candidate_locator.get("source_image_sequence", 1)
            )
            same_image_exact_overlap = (
                same_source_image
                and _merchant_cores_match(row.merchant, candidate.merchant)
                and _candidate_regions_clearly_overlap(
                    row_evidence,
                    adjacent_source,
                    candidate.evidence,
                    candidate_source,
                )
            )
            cross_image_exact_evidence = (
                not same_source_image
                and bool(row_merchant)
                and row_merchant == candidate_merchant
                and exact_business_text
                and exact_quote
                and not merchant_conflicts
                and not description_conflicts
            )
            if same_image_exact_overlap or cross_image_exact_evidence:
                match = row
                break
        if match is None:
            remaining.append(candidate)
            continue
        evidence = dict(match.evidence or {})
        sources = list(evidence.get("source_slices") or [])
        if not sources and isinstance(evidence.get("slice_sequence"), int):
            sources.append(
                {
                    "slice_sequence": evidence["slice_sequence"],
                    "source_locator": evidence.get("source_locator") or {},
                }
            )
        next_source = {
            "slice_sequence": candidate.evidence.get("slice_sequence"),
            "source_locator": candidate.evidence.get("source_locator") or {},
            "candidate_region": candidate.evidence.get("candidate_region"),
            "ocr_line_index": candidate.evidence.get("ocr_line_index"),
        }
        if next_source not in sources:
            sources.append(next_source)
        evidence["source_slices"] = sources
        candidate_locator = candidate.evidence.get("source_locator") if isinstance(candidate.evidence.get("source_locator"), dict) else {}
        same_source_image = matched_source_locator.get("source_image_sequence", 1) == candidate_locator.get("source_image_sequence", 1)
        next_reason = (
            "同一截图相邻片段的日期、时间、金额、方向与商户核心一致，且原图区域明显重合"
            if same_source_image
            else "相邻截图交界处的日期、时间、金额、方向和交易文本完全一致"
        )
        current_reason = evidence.get("overlap_merge_reason")
        if current_reason is None or not same_source_image:
            evidence["overlap_merge_reason"] = next_reason
        match.evidence = evidence
    return remaining


def _finalize_batch_state(db: Session, *, batch: FinancialImportBatch) -> dict[str, Any]:
    progress = _store_progress(db, batch=batch)
    unfinished = progress["pending_slices"] + progress["processing_slices"]
    if unfinished:
        batch.status = "processing"
        batch.parsed_at = None
    else:
        refresh_batch_counts(db, batch)
        if batch.total_count == 0:
            batch.status = "failed"
        batch.parsed_at = datetime.utcnow()
    batch.updated_at = datetime.utcnow()
    return progress


def _reset_stale_processing_slices(db: Session, *, batch: FinancialImportBatch) -> None:
    stale_before = datetime.utcnow() - timedelta(seconds=STALE_SLICE_PROCESSING_SECONDS)
    artifacts = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == batch.user_id,
        FinancialRecognitionArtifact.batch_id == batch.id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
    ).all()
    for artifact in artifacts:
        metadata = dict(artifact.artifact_metadata or {})
        if metadata.get("ocr_status") != "processing":
            continue
        raw_started = metadata.get("processing_started_at")
        try:
            started = datetime.fromisoformat(str(raw_started))
        except (TypeError, ValueError):
            started = datetime.min
        if started <= stale_before:
            metadata["ocr_status"] = "pending"
            metadata.pop("processing_started_at", None)
            artifact.artifact_metadata = metadata


def process_ocr_slice(
    db: Session,
    *,
    user_id: int,
    batch_id: int,
    sequence_number: int | None = None,
    retry_failed: bool = False,
) -> FinancialImportBatch:
    owner = lock_financial_ledger_owner(db, user_id=user_id)
    expected_data_epoch = owner.business_data_epoch
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    if batch.origin_type != "ocr" or batch.source_type not in {"long_screenshot", "screenshot_sequence"}:
        raise import_error(409, "cashflow_vision_not_segmented", "该批次不是长截图分片识别任务")
    _reset_stale_processing_slices(db, batch=batch)
    query = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
    )
    if sequence_number is not None:
        query = query.filter(FinancialRecognitionArtifact.sequence_number == sequence_number)
    artifacts = query.order_by(FinancialRecognitionArtifact.sequence_number.asc()).all()
    target = None
    for artifact in artifacts:
        status = _slice_status(artifact)
        if status == "pending" or (retry_failed and status == "failed"):
            target = artifact
            break
    if target is None:
        _finalize_batch_state(db, batch=batch)
        db.commit()
        db.refresh(batch)
        return batch
    if target.attachment_version_id is None:
        raise import_error(409, "cashflow_vision_slice_missing", "识别片段缺失，请重新上传长截图")
    metadata = dict(target.artifact_metadata or {})
    metadata["ocr_status"] = "processing"
    metadata["processing_started_at"] = datetime.utcnow().isoformat()
    metadata.pop("error_message", None)
    target.artifact_metadata = metadata
    target.error_code = None
    batch.status = "processing"
    _store_progress(db, batch=batch)
    attachment_id = target.attachment_version_id
    target_sequence = target.sequence_number
    source_locator = dict(target.source_locator or {})
    slice_hash = target.content_hash
    db.commit()

    try:
        attachment = db.query(PersonalAttachmentVersion).filter(
            PersonalAttachmentVersion.id == attachment_id,
            PersonalAttachmentVersion.user_id == user_id,
        ).first()
        if attachment is None:
            raise FileNotFoundError("slice attachment missing")
        slice_content = resolve_attachment_path(attachment).read_bytes()
        if hashlib.sha256(slice_content).hexdigest() != slice_hash:
            raise FileNotFoundError("slice attachment corrupt")
        if not isinstance(source_locator.get("transaction_row_detection"), dict):
            source_locator["transaction_row_detection"] = _detect_transaction_rows_from_png(
                slice_content
            )
        # The slice bytes are now in memory. Release the attachment lookup
        # transaction before local OCR and either model call.
        db.rollback()
        ocr_artifact_metadata: dict[str, Any]
        if (
            settings.TENCENT_OCR_ENABLED
            and target_sequence <= max(0, int(settings.TENCENT_OCR_MAX_CALLS_PER_BATCH))
        ):
            try:
                cloud_ocr = recognize_with_tencent_cloud(
                    user_id=user_id,
                    content=slice_content,
                    expected_data_epoch=expected_data_epoch,
                )
                layout_lines = _layout_ordered_tencent_lines(cloud_ocr.lines)
                ocr_text = "\n".join(line.text for line in layout_lines).strip()
                source_locator.update(
                    {
                        "ocr_provider": "tencent-cloud",
                        "ocr_model": cloud_ocr.model,
                        "ocr_line_positions": [
                            {
                                "line_index": index,
                                "confidence": line.confidence,
                                "polygon": line.polygon,
                            }
                            for index, line in enumerate(layout_lines, start=1)
                        ],
                    }
                )
                ocr_artifact_metadata = {
                    "ocr_provider": "tencent-cloud",
                    "ocr_model": cloud_ocr.model,
                    "ocr_request_id": cloud_ocr.request_id,
                    "ocr_line_count": len(cloud_ocr.lines),
                    "ocr_layout_line_count": len(layout_lines),
                    "ocr_layout_reordered": layout_lines != cloud_ocr.lines,
                    "ocr_average_confidence": cloud_ocr.average_confidence,
                    "image_slice_sent_to_tencent_cloud": True,
                }
            except TencentOCRError as exc:
                if not settings.TENCENT_OCR_FALLBACK_TO_TESSERACT:
                    raise import_error(
                        422,
                        "cashflow_vision_tencent_ocr_failed",
                        exc.user_message,
                    ) from exc
                ocr_text = _local_ocr(
                    user_id=user_id,
                    content=slice_content,
                    detected_type="image/png",
                    expected_data_epoch=expected_data_epoch,
                )
                source_locator["ocr_provider"] = "local-tesseract"
                ocr_artifact_metadata = {
                    "ocr_provider": "local-tesseract",
                    "ocr_model": "tesseract-chi_sim+eng-psm6",
                    "image_slice_sent_to_tencent_cloud": exc.request_sent,
                    "cloud_fallback_reason": exc.code,
                }
        else:
            if (
                settings.TENCENT_OCR_ENABLED
                and not settings.TENCENT_OCR_FALLBACK_TO_TESSERACT
            ):
                raise import_error(
                    422,
                    "cashflow_vision_tencent_ocr_batch_limit",
                    "该批次切片数超过腾讯云 OCR 调用上限，请拆成两个批次",
                )
            ocr_text = _local_ocr(
                user_id=user_id,
                content=slice_content,
                detected_type="image/png",
                expected_data_epoch=expected_data_epoch,
            )
            source_locator["ocr_provider"] = "local-tesseract"
            ocr_artifact_metadata = {
                "ocr_provider": "local-tesseract",
                "ocr_model": "tesseract-chi_sim+eng-psm6",
                "image_slice_sent_to_tencent_cloud": False,
                "cloud_fallback_reason": (
                    "TencentOCRBatchCallLimitReached"
                    if settings.TENCENT_OCR_ENABLED
                    else None
                ),
            }
        result = parse_ocr_text_intake(
            user_id=user_id,
            ocr_text=ocr_text,
            content_hash=slice_hash,
            expected_data_epoch=expected_data_epoch,
        )

        context_batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id)
        date_context = _previous_slice_date_context(
            db,
            batch=context_batch,
            target_sequence=target_sequence,
            target_locator=source_locator,
        )
        row_start = target_sequence * 1000
        parsed = [
            replace(
                candidate,
                row_number=row_start + index,
                evidence={
                    **candidate.evidence,
                    "slice_sequence": target_sequence,
                    "slice_candidate_index": index,
                    "source_image_sequence": source_locator.get("source_image_sequence", 1),
                    "source_image_slice_sequence": source_locator.get("source_image_slice_sequence", target_sequence),
                    "source_locator": source_locator,
                    "source_slices": [
                        {
                            "slice_sequence": target_sequence,
                            "source_image_sequence": source_locator.get("source_image_sequence", 1),
                            "source_image_slice_sequence": source_locator.get("source_image_slice_sequence", target_sequence),
                            "source_locator": source_locator,
                        }
                    ],
                },
            )
            for index, candidate in enumerate(result.parsed, start=1)
        ]
        parsed = _annotate_parsed_source_locations(
            parsed,
            ocr_text=ocr_text,
            source_locator=source_locator,
        )
        date_anchors = _extract_ocr_date_anchors(ocr_text)
        parsed = _apply_slice_date_context(
            parsed,
            ocr_text=ocr_text,
            date_anchors=date_anchors,
            previous_context=date_context,
            slice_sequence=target_sequence,
            source_locator=source_locator,
            content_hash=slice_hash,
        )
        cross_image_cases = _cross_image_overlap_cases(
            db,
            batch=context_batch,
            parsed=parsed,
        )
        db.rollback()
        parsed = _enrich_cross_image_overlap_with_ai(
            parsed,
            cases=cross_image_cases,
            user_id=user_id,
            expected_data_epoch=expected_data_epoch,
        )
        recognized_candidate_count = len(parsed)
        recognized_transaction_dates = sorted(
            {
                candidate.transaction_date.isoformat()
                for candidate in parsed
                if candidate.transaction_date is not None
            }
        )
        date_context_inherited_count = sum(
            1
            for candidate in parsed
            if candidate.evidence.get("date_context_inherited") is True
        )
        owner = lock_financial_ledger_owner(db, user_id=user_id)
        if owner.business_data_epoch != expected_data_epoch:
            db.rollback()
            raise import_error(
                409,
                "cashflow_import_data_cleared",
                "识别期间账户数据已被清空，本片段结果未保存",
            )
        batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
        target = db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == user_id,
            FinancialRecognitionArtifact.batch_id == batch_id,
            FinancialRecognitionArtifact.artifact_type == "image_slice",
            FinancialRecognitionArtifact.sequence_number == target_sequence,
        ).with_for_update().first()
        if target is None:
            raise import_error(409, "cashflow_import_data_cleared", "识别批次已被删除，本片段结果未保存")
        db.query(FinancialTransactionCandidate).filter(
            FinancialTransactionCandidate.user_id == user_id,
            FinancialTransactionCandidate.batch_id == batch_id,
            FinancialTransactionCandidate.row_number > row_start,
            FinancialTransactionCandidate.row_number < row_start + 1000,
            FinancialTransactionCandidate.status != "confirmed",
        ).delete(synchronize_session="fetch")
        db.query(FinancialRecognitionArtifact).filter(
            FinancialRecognitionArtifact.user_id == user_id,
            FinancialRecognitionArtifact.batch_id == batch_id,
            FinancialRecognitionArtifact.artifact_type == "ocr_text",
            FinancialRecognitionArtifact.sequence_number == target_sequence,
        ).delete(synchronize_session="fetch")
        persist_ocr_text_artifact(
            db,
            batch=batch,
            ocr_text=ocr_text,
            sequence_number=target_sequence,
            source_locator={"slice_sequence": target_sequence, **source_locator},
            artifact_metadata=ocr_artifact_metadata,
        )
        parsed = _merge_exact_overlap_candidates(db, batch=batch, parsed=parsed)
        _populate_candidates(db, batch=batch, parsed=parsed)
        metadata = dict(target.artifact_metadata or {})
        active_trailing_date_context = (
            _date_context_from_anchor(
                date_anchors[-1],
                slice_sequence=target_sequence,
                source_locator=source_locator,
            )
            if date_anchors
            else (
                {
                    **date_context,
                    "propagated_through_slice_sequence": target_sequence,
                }
                if date_context is not None
                else None
            )
        )
        metadata.update(
            {
                "ocr_status": "completed",
                "ocr_character_count": len(ocr_text),
                "ocr_processed_character_count": result.ocr_processed_characters or len(ocr_text),
                "ocr_chunk_count": result.ocr_chunk_count or 1,
                "ocr_text_fully_processed": (result.ocr_processed_characters or len(ocr_text)) == len(ocr_text),
                "program_candidate_count": result.program_candidate_count,
                "program_fallback_candidate_count": result.program_fallback_candidate_count,
                "ai_candidate_count": result.ai_candidate_count,
                "ai_rejected_candidate_count": result.ai_rejected_candidate_count,
                "ai_chunk_count": result.ai_chunk_count,
                "recognized_candidate_count": recognized_candidate_count,
                "new_candidate_count": len(parsed),
                "overlap_merge_count": recognized_candidate_count - len(parsed),
                "recognized_transaction_dates": recognized_transaction_dates,
                "date_context_inherited_count": date_context_inherited_count,
                "date_context_anchors": [
                    _serialize_date_context(
                        _date_context_from_anchor(
                            anchor,
                            slice_sequence=target_sequence,
                            source_locator=source_locator,
                        )
                    )
                    for anchor in date_anchors
                ],
                "active_trailing_date_context": _serialize_date_context(
                    active_trailing_date_context
                ),
                "model": result.model,
                "parser_version": result.parser_version,
                **ocr_artifact_metadata,
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        metadata.pop("processing_started_at", None)
        metadata.pop("error_message", None)
        target.source_locator = source_locator
        target.artifact_metadata = metadata
        target.error_code = None
        _finalize_batch_state(db, batch=batch)
        db.commit()
        db.refresh(batch)
        return batch
    except HTTPException as exc:
        if isinstance(exc.detail, dict) and exc.detail.get("code") == "cashflow_import_data_cleared":
            raise
        error_code, error_message = _safe_processing_error(exc)
    except Exception as exc:
        error_code, error_message = _safe_processing_error(exc)

    db.rollback()
    batch = get_owned_batch(db, user_id=user_id, batch_id=batch_id, lock=True)
    target = db.query(FinancialRecognitionArtifact).filter(
        FinancialRecognitionArtifact.user_id == user_id,
        FinancialRecognitionArtifact.batch_id == batch_id,
        FinancialRecognitionArtifact.artifact_type == "image_slice",
        FinancialRecognitionArtifact.sequence_number == target_sequence,
    ).with_for_update().first()
    if target is not None:
        metadata = dict(target.artifact_metadata or {})
        metadata["ocr_status"] = "failed"
        metadata["error_message"] = error_message
        metadata.pop("processing_started_at", None)
        target.artifact_metadata = metadata
        target.error_code = error_code
    _finalize_batch_state(db, batch=batch)
    db.commit()
    db.refresh(batch)
    return batch
