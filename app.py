
#!/usr/bin/env python3
from __future__ import annotations

import copy
import io
import json
import xml.etree.ElementTree as ET
from typing import Any, cast
from pathlib import Path
import zipfile
from dataclasses import dataclass
from functools import lru_cache

import streamlit as st
from collections import OrderedDict
# openpyxl is imported lazily inside load_mapping_rows() so the app can run without it

ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
ET.register_namespace("xsd", "http://www.w3.org/2001/XMLSchema")

COPY_TAGS = {"TotalCopies"}

SOURCE_PASSTHROUGH_TAGS = {
    "Tags",
    "SprayAmount",
    "LinearSprayAmount",
    "MaxOpacity",
    "MinOpacity",
    "ChokeWhitePixels",
    "HighlightOpacity",
    "ColorSaturation",
    "PrintSpeed2",
    "PrintDirection",
    "IsSpray",
    "IsWipe",
    "Factory",
    "Sharpen",
    "IccInRGBFileName",
    "IccInCMYKFileName",
    "RenderingIntent",
    "DelaySprayToPrint",
    "LayerDelay1to2",
    "MaxDischarge",
    "UseDischarge",
    "DischargeOpacity",
    "MinDischarge",
    "ChokeDischargePixels",
    "ColorKnockout",
    "WhiteKnockout",
}


GEOMETRY_TAGS = {
    "XOffsetMM",
    "YOffsetMM",
    "WidthMM",
    "HeightMM",
    "Rotate90",
    "Rotate180",
    "RotateSmallDegree",
    "Mirror",
    "XCenter",
    "YCenter",
    "KeepRatio",
    "TopCrop",
    "LeftCrop",
    "BottomCrop",
    "RightCrop",
    "Strips",
}

ATLAS_SETUP_MAP = {
    "black_std": {
        "set_applied": "Atlas MAX+ Black STD",
        "last_base_setup_name": "Atlas MAX+ Black STD",
        "media_name": "Atlas MAX+ Black STD",
        "icc_in_rgb": "RGB Color Space Profile",
        "icc_out": "Atlas MAX+ Black STD SatRGK.icm",
        "rendering_intent": "Perceptual",
    },
    "black_high_production": {
        "set_applied": "Atlas MAX+ Black High Production",
        "last_base_setup_name": "Atlas MAX+ Black High Production",
        "media_name": "Atlas MAX+ Black HP",
        "icc_in_rgb": "RGB Color Space Profile",
        "icc_out": "Atlas MAX+ Black High Production.icm",
        "rendering_intent": "Perceptual",
    },
    "black_hq": {
        "set_applied": "Atlas MAX+ Black HQ",
        "last_base_setup_name": "Atlas MAX+ Black HQ",
        "media_name": "Atlas MAX+ Black HQ",
        "icc_in_rgb": "RGB Color Space Profile",
        "icc_out": "Atlas MAX+ Black HQ.icm",
        "rendering_intent": "Perceptual",
    },
    "light_high_production": {
        "set_applied": "Atlas MAX+ Light High Production",
        "last_base_setup_name": "Atlas MAX+ Light High Production",
        "media_name": "Atlas MAX+ Light High Production",
        "icc_in_rgb": "RGB Color Space Profile",
        "icc_out": "Atlas MAX+ Light High Production.icm",
        "rendering_intent": "Perceptual",
    },
    "light_hq": {
        "set_applied": "Atlas MAX+ Light HQ",
        "last_base_setup_name": "Atlas MAX+ Light HQ",
        "media_name": "Atlas MAX+ Light HQ",
        "icc_in_rgb": "RGB Color Space Profile",
        "icc_out": "Atlas MAX+ Light HQ.icm",
        "rendering_intent": "Perceptual",
    },
    "light_std": {
        "set_applied": "Atlas MAX+ Light STD",
        "last_base_setup_name": "Atlas MAX+ Light STD",
        "media_name": "Atlas MAX+ Light STD",
        "icc_in_rgb": "RGB Color Space Profile",
        "icc_out": "Atlas MAX+ Light STD.icm",
        "rendering_intent": "Perceptual",
    },
}

CANONICAL_ATLAS_TARGETS = {
    "Atlas MAX+ Black STD": {
        "media_name": "Atlas MAX+ Black STD",
        "icc_out": "Atlas MAX+ Black STD SatRGK.icm",
    },
    "Atlas MAX+ Black HQ": {
        "media_name": "Atlas MAX+ Black HQ",
        "icc_out": "Atlas MAX+ Black HQ.icm",
    },
    "Atlas MAX+ Black High Production": {
        "media_name": "Atlas MAX+ Black HP",
        "icc_out": "Atlas MAX+ Black High Production.icm",
    },
    "Atlas MAX+ Light High Production": {
        "media_name": "Atlas MAX+ Light High Production",
        "icc_out": "Atlas MAX+ Light High Production.icm",
    },
    "Atlas MAX+ Light HQ": {
        "media_name": "Atlas MAX+ Light HQ",
        "icc_out": "Atlas MAX+ Light HQ.icm",
    },
    "Atlas MAX+ Light STD": {
        "media_name": "Atlas MAX+ Light STD",
        "icc_out": "Atlas MAX+ Light STD.icm",
    },
}


ROOT_ATTRS = OrderedDict([
    ("xmlns:xsd", "http://www.w3.org/2001/XMLSchema"),
])

# Special separation rules block
SPECIAL_SEPARATION_RULES = {
    "Qc": {"solid": "25", "max_coverage": "0", "is_max_coverage": "false"},
    "Qw": {"solid": "0", "max_coverage": "55", "is_max_coverage": "true"},
    "Iw": {"solid": "40", "max_coverage": "0", "is_max_coverage": "false"},
    "Ic": {"solid": "25", "max_coverage": "0", "is_max_coverage": "false"},
}

# Built-in default template path
DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
PREFERRED_TEMPLATE_NAMES = [
    "approved_atlas_max_template.ksf",
    "default_atlas_template.ksf",
]
DEFAULT_TEMPLATE_PATH = DEFAULT_TEMPLATE_DIR / PREFERRED_TEMPLATE_NAMES[0]

PREFERRED_CROSS_TEMPLATE_NAMES = {
    "plus_to_poly": [
        "approved_atlas_max_poly_template.ksf",
        "approved_poly_kxlgm_dark_tee_template.kst",
        "approved_poly_kxlgm_dark_hoodie_template.kst",
        "approved_poly_kxlgm_light_tee_template.kst",
        "approved_poly_kxlgm_light_hoodie_template.kst",
        "approved_poly_kxlgm_white_tee_template.kst",
        "approved_poly_kxlgm_white_hoodie_template.kst",
        "atlas_max_poly_output_template.ksf",
        "approved_poly_output_template.ksf",
        "poly_output_template.ksf",
    ],
    "max_to_poly": [
        "approved_atlas_max_poly_template.ksf",
        "approved_poly_kxlgm_dark_tee_template.kst",
        "approved_poly_kxlgm_dark_hoodie_template.kst",
        "approved_poly_kxlgm_light_tee_template.kst",
        "approved_poly_kxlgm_light_hoodie_template.kst",
        "approved_poly_kxlgm_white_tee_template.kst",
        "approved_poly_kxlgm_white_hoodie_template.kst",
        "atlas_max_poly_output_template.ksf",
        "approved_poly_output_template.ksf",
        "poly_output_template.ksf",
    ],
    "poly_to_plus": [
        "approved_atlas_max_template.ksf",
        "atlas_max_plus_output_template.ksf",
        "approved_plus_output_template.ksf",
        "plus_output_template.ksf",
    ],
    "avhd6_to_plus": [
        "approved_atlas_max_template.ksf",
        "atlas_max_plus_output_template.ksf",
        "approved_plus_output_template.ksf",
        "plus_output_template.ksf",
    ],
    "plus_to_avhd6": [
        "approved_avhd6_output_template.ksf",
        "avhd6_output_template.ksf",
    ],
}


PREFERRED_MAPPING_WORKBOOK_NAMES = [
    "vulcan_mapping_with_atlas_reference_adj.xlsx",
    "vulcan_mapping_with_atlas_reference.xlsx",
    "vulcan_mapping_english_with_atlas_reference.xlsx",
    "vulcan_mapping_starter_table_v2.xlsx",
    "atlas_max_plus_to_poly_mapping_template.xlsx",
]
MAPPING_WORKBOOK_DIR = Path(__file__).resolve().parent

LEGACY_MAPPING_WORKBOOK_NAMES = (
    "vulcan_mapping_with_atlas_reference_adj.xlsx",
    "vulcan_mapping_with_atlas_reference.xlsx",
    "vulcan_mapping_english_with_atlas_reference.xlsx",
    "vulcan_mapping_starter_table_v2.xlsx",
)

CROSS_MAPPING_WORKBOOK_NAMES = (
    "atlas_max_plus_to_poly_mapping_template.xlsx",
)

PALLET_OVERRIDE_DEFAULT = "Use mapping value"
POLY_PALLET_OPTIONS = [
    PALLET_OVERRIDE_DEFAULT,
    "Standard pallet",
    "Standard pallet poly",
    "Atlas - Baby",
    "Atlas - Children (L)",
    "Atlas - Children (S)",
    "Atlas - Grand",
    "Atlas - Neck Tag",
    "Atlas - Standard",
    "Atlas - Standard poly",
    "Atlas - Super Grand",
    "Atlas - Tote bag",
    "Atlas - Youth And Ladies Neck Tag",
    "Atlas - Youth and Ladies",
    "Atlas - Zipper hoodie",
    "AutoFIT - Large",
    "AutoFIT - Large Neck Tag",
    "AutoFIT - Medium",
    "AutoFIT - Medium Neck Tag",
    "AutoFIT - Small",
    "AutoFIT - Small Neck Tag",
    "AutoFIT ExtraLarge",
    "AutoFIT Hoodies Medium",
    "AutoFIT Hoodies Small",
    "AutoFIT MenYouth",
    "Undefined",
]


@dataclass(frozen=True)
class MappingRow:
    workbook_name: str
    sheet_name: str
    source_family: str
    target_family: str
    source_setup: str
    source_media: str
    source_input_rgb: str
    source_input_cmyk: str
    source_output_icc: str
    target_setup: str
    target_base_setup: str
    target_media: str
    target_input_rgb: str
    target_input_cmyk: str
    target_output_icc: str
    target_pallet: str
    status: str
    auto_map_key: str
    notes: str


@dataclass(frozen=True)
class MappingSheetDefinition:
    sheet_name: str
    source_family: str
    target_family: str
    source_setup_headers: tuple[str, ...]
    source_media_headers: tuple[str, ...]
    source_output_headers: tuple[str, ...]
    source_input_rgb_headers: tuple[str, ...]
    source_input_cmyk_headers: tuple[str, ...]
    target_setup_headers: tuple[str, ...]
    target_base_setup_headers: tuple[str, ...]
    target_media_headers: tuple[str, ...]
    target_output_headers: tuple[str, ...]
    target_input_rgb_headers: tuple[str, ...]
    target_input_cmyk_headers: tuple[str, ...]
    target_pallet_headers: tuple[str, ...]
    status_headers: tuple[str, ...]
    auto_map_key_headers: tuple[str, ...]
    notes_headers: tuple[str, ...]


MAPPING_SHEET_DEFINITIONS = (
    MappingSheetDefinition(
        sheet_name="Plus_to_Poly_Mapping",
        source_family="plus",
        target_family="poly",
        source_setup_headers=("PLUS_SETUP", "PLUS_BASE_SETUP"),
        source_media_headers=("PLUS_MEDIA",),
        source_output_headers=("PLUS_OUTPUT_ICC",),
        source_input_rgb_headers=("PLUS_INPUT_RGB",),
        source_input_cmyk_headers=("PLUS_INPUT_CMYK",),
        target_setup_headers=("POLY_SETUP",),
        target_base_setup_headers=("POLY_BASE_SETUP",),
        target_media_headers=("POLY_MEDIA",),
        target_output_headers=("POLY_OUTPUT_ICC",),
        target_input_rgb_headers=("POLY_INPUT_RGB",),
        target_input_cmyk_headers=("POLY_INPUT_CMYK",),
        target_pallet_headers=("POLY_PALLET",),
        status_headers=("STATUS",),
        auto_map_key_headers=("AUTO_MAP_KEY",),
        notes_headers=("NOTES",),
    ),
    MappingSheetDefinition(
        sheet_name="Poly_to_Plus_Mapping",
        source_family="poly",
        target_family="plus",
        source_setup_headers=("POLY_SETUP", "POLY_BASE_SETUP"),
        source_media_headers=("POLY_MEDIA",),
        source_output_headers=("POLY_OUTPUT_ICC",),
        source_input_rgb_headers=("POLY_INPUT_RGB",),
        source_input_cmyk_headers=("POLY_INPUT_CMYK",),
        target_setup_headers=("PLUS_SETUP",),
        target_base_setup_headers=("PLUS_BASE_SETUP",),
        target_media_headers=("PLUS_MEDIA",),
        target_output_headers=("PLUS_OUTPUT_ICC",),
        target_input_rgb_headers=("PLUS_INPUT_RGB",),
        target_input_cmyk_headers=("PLUS_INPUT_CMYK",),
        target_pallet_headers=("PLUS_PALLET",),
        status_headers=("STATUS",),
        auto_map_key_headers=("AUTO_MAP_KEY",),
        notes_headers=("NOTES",),
    ),
    MappingSheetDefinition(
        sheet_name="MAX_TO_POLY",
        source_family="atlas",
        target_family="poly",
        source_setup_headers=("MAX_SETUP", "MAX_BASE_SETUP"),
        source_media_headers=("MAX_MEDIA",),
        source_output_headers=("MAX_OUTPUT_ICC",),
        source_input_rgb_headers=("MAX_INPUT_RGB",),
        source_input_cmyk_headers=("MAX_INPUT_CMYK",),
        target_setup_headers=("POLY_SETUP", "POLY_BASE_SETUP"),
        target_base_setup_headers=("POLY_BASE_SETUP", "POLY_SETUP"),
        target_media_headers=("POLY_MEDIA",),
        target_output_headers=("POLY_OUTPUT_ICC",),
        target_input_rgb_headers=("POLY_INPUT_RGB",),
        target_input_cmyk_headers=("POLY_INPUT_CMYK",),
        target_pallet_headers=("POLY_PALLET",),
        status_headers=("STATUS",),
        auto_map_key_headers=("AUTO_MAP_KEY",),
        notes_headers=("NOTES",),
    ),
    MappingSheetDefinition(
        sheet_name="AVHD6_TO_PLUS",
        source_family="avhd6",
        target_family="plus",
        source_setup_headers=("AVHD6_SETUP", "AVHD6_BASE_SETUP"),
        source_media_headers=("AVHD6_MEDIA",),
        source_output_headers=("AVHD6_OUTPUT_ICC",),
        source_input_rgb_headers=("AVHD6_INPUT_RGB",),
        source_input_cmyk_headers=("AVHD6_INPUT_CMYK",),
        target_setup_headers=("PLUS_SETUP", "PLUS_BASE_SETUP"),
        target_base_setup_headers=("PLUS_BASE_SETUP", "PLUS_SETUP"),
        target_media_headers=("PLUS_MEDIA",),
        target_output_headers=("PLUS_OUTPUT_ICC",),
        target_input_rgb_headers=("PLUS_INPUT_RGB",),
        target_input_cmyk_headers=("PLUS_INPUT_CMYK",),
        target_pallet_headers=("PLUS_PALLET",),
        status_headers=("STATUS",),
        auto_map_key_headers=("AUTO_MAP_KEY",),
        notes_headers=("NOTES",),
    ),
    MappingSheetDefinition(
        sheet_name="AVHD6_TO_PLUS",
        source_family="plus",
        target_family="avhd6",
        source_setup_headers=("PLUS_SETUP", "PLUS_BASE_SETUP"),
        source_media_headers=("PLUS_MEDIA",),
        source_output_headers=("PLUS_OUTPUT_ICC",),
        source_input_rgb_headers=("PLUS_INPUT_RGB",),
        source_input_cmyk_headers=("PLUS_INPUT_CMYK",),
        target_setup_headers=("AVHD6_SETUP", "AVHD6_BASE_SETUP"),
        target_base_setup_headers=("AVHD6_BASE_SETUP", "AVHD6_SETUP"),
        target_media_headers=("AVHD6_MEDIA",),
        target_output_headers=("AVHD6_OUTPUT_ICC",),
        target_input_rgb_headers=("AVHD6_INPUT_RGB",),
        target_input_cmyk_headers=("AVHD6_INPUT_CMYK",),
        target_pallet_headers=("AVHD6_PALLET",),
        status_headers=("STATUS",),
        auto_map_key_headers=("AUTO_MAP_KEY",),
        notes_headers=("NOTES",),
    ),
    MappingSheetDefinition(
        sheet_name="Vulcan Mapping",
        source_family="vulcan",
        target_family="atlas",
        source_setup_headers=("VULCAN_SETUP",),
        source_media_headers=("VULCAN_MEDIA",),
        source_output_headers=("OUTPUT_PROFILE",),
        source_input_rgb_headers=("INPUT_PROFILE",),
        source_input_cmyk_headers=("INPUT_PROFILE_CMYK",),
        target_setup_headers=("ATLAS_SETUP",),
        target_base_setup_headers=("ATLAS_SETUP",),
        target_media_headers=("ATLAS_MEDIA",),
        target_output_headers=("ATLAS_OUTPUT_ICC",),
        target_input_rgb_headers=("ATLAS_INPUT_RGB",),
        target_input_cmyk_headers=("ATLAS_INPUT_CMYK",),
        target_pallet_headers=("PALLET_MAPPING",),
        status_headers=("STATUS",),
        auto_map_key_headers=("AUTO_MAP_KEY",),
        notes_headers=("NOTES",),
    ),
)


@dataclass
class SourceItem:
    relative_path: Path
    data: bytes
    origin: str


@dataclass
class ConvertedItem:
    relative_path: Path
    output_path: Path
    data: bytes | None
    status: str
    error: str | None


def load_xml(path: Path) -> ET.ElementTree:
    return cast(ET.ElementTree, ET.parse(path))


def safe_rerun() -> None:
    rerun = getattr(st, "rerun", None)
    if callable(rerun):
        rerun()
        return

    experimental_rerun = getattr(st, "experimental_rerun", None)
    if callable(experimental_rerun):
        experimental_rerun()


def dedupe_relative_path(relative_path: Path, used_paths: set[Path]) -> Path:
    candidate = relative_path
    counter = 2
    while candidate in used_paths:
        candidate = relative_path.with_name(f"{relative_path.stem}_{counter}{relative_path.suffix}")
        counter += 1
    used_paths.add(candidate)
    return candidate


def collect_source_items(
    file_uploads: list[Any] | None,
    zip_uploads: list[Any] | None,
) -> tuple[list[SourceItem], list[str]]:
    items: list[SourceItem] = []
    issues: list[str] = []
    used_paths: set[Path] = set()

    for uploaded in file_uploads or []:
        uploaded_path = Path(uploaded.name)
        if uploaded_path.suffix.lower() != ".ksf":
            continue
        if uploaded_path.name == ".DS_Store":
            continue
        if any(part.startswith("._") for part in uploaded_path.parts):
            continue
        if "__MACOSX" in uploaded_path.parts:
            continue
        relative_path = dedupe_relative_path(Path(uploaded_path.name), used_paths)
        items.append(SourceItem(relative_path=relative_path, data=uploaded.getvalue(), origin="file"))

    for uploaded in zip_uploads or []:
        with zipfile.ZipFile(io.BytesIO(uploaded.getvalue())) as archive:
            for member in sorted(archive.infolist(), key=lambda info: info.filename):
                member_path = Path(member.filename)
                if member.is_dir() or member_path.suffix.lower() != ".ksf":
                    continue
                safe_parts = [part for part in member_path.parts if part not in {"", ".", ".."}]
                if not safe_parts:
                    continue
                if safe_parts[0] == "__MACOSX":
                    continue
                if member_path.name == ".DS_Store":
                    continue
                if any(part.startswith("._") for part in safe_parts):
                    continue
                if len(safe_parts) > 1 and safe_parts[0] == Path(uploaded.name).stem:
                    safe_parts = safe_parts[1:]
                if not safe_parts:
                    continue
                relative_path = dedupe_relative_path(Path(*safe_parts), used_paths)
                items.append(
                    SourceItem(
                        relative_path=relative_path,
                        data=archive.read(member.filename),
                        origin="zip",
                    )
                )

    return items, issues


def detect_missing_source_error(
    file_uploads: list[Any] | None,
    zip_uploads: list[Any] | None,
    source_parts: list[SourceItem],
) -> str | None:
    if source_parts:
        return None

    if file_uploads:
        return "The uploaded source files could not be processed. Only `.ksf` files are supported."

    if zip_uploads:
        return (
            "No `.ksf` files were found inside the uploaded ZIP package(s). "
            "This converter ignores other formats such as `.kst`, `.xml`, `.lut`, and `.icc`."
        )

    return None


# Helper to load the default template if present
def load_default_template_bytes() -> tuple[str | None, bytes | None]:
    if not DEFAULT_TEMPLATE_DIR.is_dir():
        return None, None

    for filename in PREFERRED_TEMPLATE_NAMES:
        candidate = DEFAULT_TEMPLATE_DIR / filename
        if candidate.is_file():
            return candidate.name, candidate.read_bytes()

    candidates = sorted(DEFAULT_TEMPLATE_DIR.glob("*.ksf"))
    if not candidates:
        return None, None

    selected = candidates[0]
    return selected.name, selected.read_bytes()


def load_preferred_template_bytes(preferred_names: list[str]) -> tuple[str | None, bytes | None]:
    if not DEFAULT_TEMPLATE_DIR.is_dir():
        return None, None

    for filename in preferred_names:
        candidate = DEFAULT_TEMPLATE_DIR / filename
        if candidate.is_file():
            return candidate.name, candidate.read_bytes()

    return None, None


def load_available_template_options(preferred_names: list[str]) -> dict[str, bytes]:
    if not DEFAULT_TEMPLATE_DIR.is_dir():
        return {}

    options: dict[str, bytes] = {}
    for filename in preferred_names:
        candidate = DEFAULT_TEMPLATE_DIR / filename
        if candidate.is_file():
            options[candidate.name] = candidate.read_bytes()
    return options


def normalize_lookup(text: str) -> str:
    cleaned = normalize(text)
    for suffix in [".icm", ".icc", ".lut", ".kst"]:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return " ".join(cleaned.split())


# Similarity scoring helper for mapping
def similarity_score(left: str, right: str) -> int:
    left_norm = normalize_lookup(left)
    right_norm = normalize_lookup(right)
    if not left_norm or not right_norm:
        return 0
    if left_norm == right_norm:
        return 100
    if left_norm in right_norm or right_norm in left_norm:
        return 60

    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return 0

    overlap = left_tokens & right_tokens
    if not overlap:
        return 0

    return int((len(overlap) / max(len(left_tokens), len(right_tokens))) * 40)


def resolve_mapping_workbook_paths() -> list[Path]:
    selected_paths: list[Path] = []
    seen: set[Path] = set()

    for filename in CROSS_MAPPING_WORKBOOK_NAMES:
        candidate = MAPPING_WORKBOOK_DIR / filename
        if candidate.is_file() and candidate not in seen:
            selected_paths.append(candidate)
            seen.add(candidate)

    if selected_paths:
        return selected_paths

    for candidate in sorted(MAPPING_WORKBOOK_DIR.glob("*.xlsx")):
        if candidate not in seen:
            selected_paths.append(candidate)
            seen.add(candidate)

    return selected_paths


def resolve_single_mapping_workbook_path(preferred_names: tuple[str, ...]) -> Path | None:
    for filename in preferred_names:
        candidate = MAPPING_WORKBOOK_DIR / filename
        if candidate.is_file():
            return candidate
    return None


def first_header_value(
    row: tuple[Any, ...],
    headers: dict[str, list[int]],
    header_names: tuple[str, ...],
) -> str:
    for header_name in header_names:
        for index in headers.get(header_name, []):
            if index >= len(row):
                continue
            value = str(row[index] or "").strip()
            if value:
                return value
    return ""


def collect_mapping_rows_from_sheet(
    sheet: Any,
    definition: MappingSheetDefinition,
    workbook_name: str,
) -> list[MappingRow]:
    headers: dict[str, list[int]] = {}
    for index, cell in enumerate(sheet[1]):
        value = str(cell.value or "").strip()
        if value:
            headers.setdefault(value, []).append(index)

    rows: list[MappingRow] = []
    for raw_row in sheet.iter_rows(min_row=2, values_only=True):
        source_setup = first_header_value(raw_row, headers, definition.source_setup_headers)
        source_media = first_header_value(raw_row, headers, definition.source_media_headers)
        source_output_icc = first_header_value(raw_row, headers, definition.source_output_headers)
        source_input_rgb = first_header_value(raw_row, headers, definition.source_input_rgb_headers)
        source_input_cmyk = first_header_value(raw_row, headers, definition.source_input_cmyk_headers)
        target_setup = first_header_value(raw_row, headers, definition.target_setup_headers)
        target_base_setup = first_header_value(raw_row, headers, definition.target_base_setup_headers)
        target_media = first_header_value(raw_row, headers, definition.target_media_headers)
        target_output_icc = first_header_value(raw_row, headers, definition.target_output_headers)
        target_input_rgb = first_header_value(raw_row, headers, definition.target_input_rgb_headers)
        target_input_cmyk = first_header_value(raw_row, headers, definition.target_input_cmyk_headers)
        target_pallet = first_header_value(raw_row, headers, definition.target_pallet_headers)
        status = first_header_value(raw_row, headers, definition.status_headers)
        auto_map_key = first_header_value(raw_row, headers, definition.auto_map_key_headers)
        notes = first_header_value(raw_row, headers, definition.notes_headers)

        if not any(
            [
                source_setup,
                source_media,
                source_output_icc,
                source_input_rgb,
                source_input_cmyk,
                target_setup,
                target_base_setup,
                target_media,
                target_output_icc,
            ]
        ):
            continue

        rows.append(
            MappingRow(
                workbook_name=workbook_name,
                sheet_name=definition.sheet_name,
                source_family=definition.source_family,
                target_family=definition.target_family,
                source_setup=source_setup,
                source_media=source_media,
                source_input_rgb=source_input_rgb,
                source_input_cmyk=source_input_cmyk,
                source_output_icc=source_output_icc,
                target_setup=target_setup,
                target_base_setup=target_base_setup,
                target_media=target_media,
                target_input_rgb=target_input_rgb,
                target_input_cmyk=target_input_cmyk,
                target_output_icc=target_output_icc,
                target_pallet=target_pallet,
                status=status,
                auto_map_key=auto_map_key,
                notes=notes,
            )
        )

    return rows


def load_workbook_loader() -> Any | None:
    try:
        import importlib
        _openpyxl = importlib.import_module("openpyxl")
        return _openpyxl.load_workbook
    except ModuleNotFoundError:
        return None


@lru_cache(maxsize=1)
def load_legacy_mapping_rows() -> tuple[str | None, list[MappingRow]]:
    workbook_path = resolve_single_mapping_workbook_path(LEGACY_MAPPING_WORKBOOK_NAMES)
    if workbook_path is None:
        return None, []

    load_workbook_fn = load_workbook_loader()
    if load_workbook_fn is None:
        return None, []

    workbook = load_workbook_fn(workbook_path, data_only=True)
    sheet_name = "Vulcan Mapping" if "Vulcan Mapping" in workbook.sheetnames else workbook.sheetnames[0]
    sheet = workbook[sheet_name]

    headers: dict[str, int] = {}
    for index, cell in enumerate(sheet[1]):
        value = str(cell.value or "").strip()
        if value:
            headers[value] = index

    def cell_value(row: tuple[Any, ...], header: str) -> str:
        index = headers.get(header)
        if index is None or index >= len(row):
            return ""
        return str(row[index] or "").strip()

    rows: list[MappingRow] = []
    for raw_row in sheet.iter_rows(min_row=2, values_only=True):
        vulcan_setup = cell_value(raw_row, "VULCAN_SETUP")
        vulcan_media = cell_value(raw_row, "VULCAN_MEDIA")
        input_profile = cell_value(raw_row, "INPUT_PROFILE")
        output_profile = cell_value(raw_row, "OUTPUT_PROFILE")
        atlas_setup = cell_value(raw_row, "ATLAS_SETUP")
        atlas_media = cell_value(raw_row, "ATLAS_MEDIA")
        atlas_output_icc = cell_value(raw_row, "ATLAS_OUTPUT_ICC")
        pallet_mapping = cell_value(raw_row, "PALLET_MAPPING")
        status = cell_value(raw_row, "STATUS")
        auto_map_key = cell_value(raw_row, "AUTO_MAP_KEY")

        if not any([vulcan_setup, vulcan_media, input_profile, output_profile, atlas_setup, atlas_media, atlas_output_icc]):
            continue

        rows.append(
            MappingRow(
                workbook_name=workbook_path.name,
                sheet_name=sheet_name,
                source_family="vulcan",
                target_family="atlas",
                source_setup=vulcan_setup,
                source_media=vulcan_media,
                source_input_rgb=input_profile,
                source_input_cmyk="",
                source_output_icc=output_profile,
                target_setup=atlas_setup,
                target_base_setup=atlas_setup,
                target_media=atlas_media,
                target_input_rgb="",
                target_input_cmyk="",
                target_output_icc=atlas_output_icc,
                target_pallet=pallet_mapping,
                status=status,
                auto_map_key=auto_map_key,
                notes="",
            )
        )

    return workbook_path.name, rows


def find_legacy_mapping_row(source_root: ET.Element) -> MappingRow | None:
    _, rows = load_legacy_mapping_rows()
    if not rows:
        return None

    source_setup = get_text(source_root, "SetApplied")
    source_media = get_text(source_root, "MediaName")
    source_input = get_text(source_root, "IccInRGBFileName")
    source_output = get_text(source_root, "IccOutFileName")

    source_setup_norm = normalize_lookup(source_setup)
    source_media_norm = normalize_lookup(source_media)
    source_input_norm = normalize_lookup(source_input)
    source_output_norm = normalize_lookup(source_output)

    def row_status_priority(row: MappingRow) -> int:
        status = normalize_lookup(row.status)
        if status == "mapped":
            return 30
        if status == "fallback":
            return 20
        if status == "review":
            return 10
        return 0

    def field_presence_bonus(row: MappingRow) -> int:
        bonus = 0
        if normalize_lookup(row.source_setup):
            bonus += 3
        if normalize_lookup(row.source_output_icc):
            bonus += 2
        if normalize_lookup(row.source_media):
            bonus += 1
        return bonus

    best_row: MappingRow | None = None
    best_source_score = -1
    best_template_score = -1
    best_bonus_score = -1

    for row in rows:
        row_setup_norm = normalize_lookup(row.source_setup)
        row_media_norm = normalize_lookup(row.source_media)
        row_input_norm = normalize_lookup(row.source_input_rgb)
        row_output_norm = normalize_lookup(row.source_output_icc)

        score = 0

        if row_output_norm and source_output_norm:
            if row_output_norm == source_output_norm:
                score += 1200
            else:
                score += similarity_score(row.source_output_icc, source_output) * 10

        if row_setup_norm and source_setup_norm:
            if row_setup_norm == source_setup_norm:
                score += 700
            else:
                score += similarity_score(row.source_setup, source_setup) * 6

        if row_media_norm and source_media_norm:
            score += similarity_score(row.source_media, source_media) * 3

        if row_input_norm and source_input_norm:
            score += similarity_score(row.source_input_rgb, source_input)

        score += row_status_priority(row)
        score += field_presence_bonus(row)

        if score > best_score:
            best_score = score
            best_row = row

    if best_score < 120:
        return None

    return best_row


def apply_legacy_mapping_row(target_root: ET.Element, mapping_row: MappingRow | None) -> None:
    if mapping_row is None:
        return

    atlas_setup = mapping_row.target_setup or ""
    atlas_media = mapping_row.target_media or ""
    atlas_output_icc = mapping_row.target_output_icc or ""

    atlas_media, atlas_output_icc = get_canonical_atlas_targets(
        atlas_setup,
        atlas_media,
        atlas_output_icc,
    )

    if atlas_setup:
        replace_simple_text(target_root, "SetApplied", atlas_setup)
        replace_simple_text(target_root, "LastBaseSetupName", atlas_setup)
    if atlas_media:
        replace_simple_text(target_root, "MediaName", atlas_media)
    if atlas_output_icc:
        replace_simple_text(target_root, "IccOutFileName", atlas_output_icc)
    if mapping_row.target_pallet:
        replace_simple_text(target_root, "TableName", mapping_row.target_pallet)

@lru_cache(maxsize=1)
def load_mapping_rows() -> tuple[str | None, list[MappingRow]]:
    workbook_paths = resolve_mapping_workbook_paths()
    if not workbook_paths:
        return None, []

    try:
        import importlib
        _openpyxl = importlib.import_module("openpyxl")
        _load_workbook = _openpyxl.load_workbook
    except ModuleNotFoundError:
        return None, []

    rows: list[MappingRow] = []
    workbook_names: list[str] = []
    for workbook_path in workbook_paths:
        workbook = _load_workbook(workbook_path, data_only=True)
        workbook_names.append(workbook_path.name)

        for definition in MAPPING_SHEET_DEFINITIONS:
            if definition.sheet_name not in workbook.sheetnames:
                continue
            rows.extend(
                collect_mapping_rows_from_sheet(
                    workbook[definition.sheet_name],
                    definition,
                    workbook_path.name,
                )
            )

        if not any(row.workbook_name == workbook_path.name for row in rows) and workbook.sheetnames:
            fallback_sheet = workbook[workbook.sheetnames[0]]
            rows.extend(
                collect_mapping_rows_from_sheet(
                    fallback_sheet,
                    MappingSheetDefinition(
                        sheet_name=fallback_sheet.title,
                        source_family="unknown",
                        target_family="unknown",
                        source_setup_headers=("SOURCE_SETUP", "SETUP", "BASE_SETUP"),
                        source_media_headers=("SOURCE_MEDIA", "MEDIA"),
                        source_output_headers=("SOURCE_OUTPUT_ICC", "OUTPUT_ICC"),
                        source_input_rgb_headers=("SOURCE_INPUT_RGB", "INPUT_RGB"),
                        source_input_cmyk_headers=("SOURCE_INPUT_CMYK", "INPUT_CMYK"),
                        target_setup_headers=("TARGET_SETUP",),
                        target_base_setup_headers=("TARGET_BASE_SETUP",),
                        target_media_headers=("TARGET_MEDIA",),
                        target_output_headers=("TARGET_OUTPUT_ICC",),
                        target_input_rgb_headers=("TARGET_INPUT_RGB",),
                        target_input_cmyk_headers=("TARGET_INPUT_CMYK",),
                        target_pallet_headers=("TARGET_PALLET", "PALLET_MAPPING"),
                        status_headers=("STATUS",),
                        auto_map_key_headers=("AUTO_MAP_KEY",),
                        notes_headers=("NOTES",),
                    ),
                    workbook_path.name,
                ),
            )

    return ", ".join(workbook_names), rows


def find_mapping_row(
    source_root: ET.Element,
    template_root: ET.Element | None = None,
    expected_source_family: str | None = None,
    expected_target_family: str | None = None,
) -> MappingRow | None:
    _, rows = load_mapping_rows()
    if not rows:
        return None

    source_family = expected_source_family or detect_mapping_family(source_root)
    target_family = expected_target_family or detect_mapping_family(template_root)

    source_setup = get_text(source_root, "SetApplied")
    source_base_setup = get_text(source_root, "LastBaseSetupName")
    source_media = get_text(source_root, "MediaName")
    source_input_rgb = get_text(source_root, "IccInRGBFileName")
    source_input_cmyk = get_text(source_root, "IccInCMYKFileName")
    source_output_icc = get_text(source_root, "IccOutFileName")

    source_setup_norm = normalize_lookup(source_setup)
    source_base_setup_norm = normalize_lookup(source_base_setup)
    source_media_norm = normalize_lookup(source_media)
    source_input_rgb_norm = normalize_lookup(source_input_rgb)
    source_input_cmyk_norm = normalize_lookup(source_input_cmyk)
    source_output_norm = normalize_lookup(source_output_icc)

    template_base_setup = get_text(template_root, "LastBaseSetupName") if template_root is not None else ""
    template_media = get_text(template_root, "MediaName") if template_root is not None else ""
    template_output_icc = get_text(template_root, "IccOutFileName") if template_root is not None else ""

    template_base_setup_norm = normalize_lookup(template_base_setup)
    template_media_norm = normalize_lookup(template_media)
    template_output_norm = normalize_lookup(template_output_icc)

    def row_status_priority(row: MappingRow) -> int:
        status = normalize_lookup(row.status)
        if status in {"mapped", "maped"}:
            return 30
        if status == "fallback":
            return 20
        if status == "review":
            return 10
        return 0

    def field_presence_bonus(row: MappingRow) -> int:
        bonus = 0
        if normalize_lookup(row.source_setup):
            bonus += 3
        if normalize_lookup(row.source_output_icc):
            bonus += 2
        if normalize_lookup(row.source_media):
            bonus += 1
        return bonus

    best_row: MappingRow | None = None
    best_source_score = -1
    best_template_score = -1
    best_bonus_score = -1

    for row in rows:
        if not families_are_compatible(source_family, row.source_family):
            continue
        if not families_are_compatible(target_family, row.target_family):
            continue

        row_setup_norm = normalize_lookup(row.source_setup)
        row_media_norm = normalize_lookup(row.source_media)
        row_input_rgb_norm = normalize_lookup(row.source_input_rgb)
        row_input_cmyk_norm = normalize_lookup(row.source_input_cmyk)
        row_output_norm = normalize_lookup(row.source_output_icc)
        row_target_base_norm = normalize_lookup(row.target_base_setup or row.target_setup)
        row_target_media_norm = normalize_lookup(row.target_media)
        row_target_output_norm = normalize_lookup(row.target_output_icc)

        source_score = 0
        template_score = 0
        bonus_score = row_status_priority(row) + field_presence_bonus(row)

        if row_setup_norm:
            if source_base_setup_norm and row_setup_norm == source_base_setup_norm:
                source_score += 1200
            elif source_base_setup_norm:
                source_score += similarity_score(row.source_setup, source_base_setup) * 10

            if source_setup_norm and row_setup_norm == source_setup_norm:
                source_score += 700
            elif source_setup_norm:
                source_score += similarity_score(row.source_setup, source_setup) * 5

        if row_output_norm and source_output_norm:
            if row_output_norm == source_output_norm:
                source_score += 700
            else:
                source_score += similarity_score(row.source_output_icc, source_output_icc) * 6

        if row_media_norm and source_media_norm:
            source_score += similarity_score(row.source_media, source_media) * 4

        if row_input_rgb_norm and source_input_rgb_norm:
            source_score += similarity_score(row.source_input_rgb, source_input_rgb) * 2
        if row_input_cmyk_norm and source_input_cmyk_norm:
            source_score += similarity_score(row.source_input_cmyk, source_input_cmyk)

        if template_root is not None:
            if row_target_base_norm and template_base_setup_norm:
                if row_target_base_norm == template_base_setup_norm:
                    template_score += 180
                else:
                    template_score += similarity_score(row.target_base_setup or row.target_setup, template_base_setup) * 2
            if row_target_media_norm and template_media_norm:
                template_score += similarity_score(row.target_media, template_media) * 2
            if row_target_output_norm and template_output_norm:
                template_score += similarity_score(row.target_output_icc, template_output_icc) * 2

        if (
            source_score > best_source_score
            or (
                source_score == best_source_score
                and template_score > best_template_score
            )
            or (
                source_score == best_source_score
                and template_score == best_template_score
                and bonus_score > best_bonus_score
            )
        ):
            best_row = row
            best_source_score = source_score
            best_template_score = template_score
            best_bonus_score = bonus_score

    if best_source_score < 120:
        return None

    return best_row


def apply_mapping_row(target_root: ET.Element, mapping_row: MappingRow | None) -> None:
    if mapping_row is None:
        return

    target_setup = mapping_row.target_setup or mapping_row.target_base_setup or ""
    target_base_setup = mapping_row.target_base_setup or mapping_row.target_setup or ""
    target_media = mapping_row.target_media or ""
    target_output_icc = mapping_row.target_output_icc or ""

    target_media, target_output_icc = get_canonical_atlas_targets(
        target_base_setup,
        target_media,
        target_output_icc,
    )

    if target_setup:
        replace_simple_text(target_root, "SetApplied", target_setup)
    if mapping_row.target_family == "poly":
        replace_simple_text(target_root, "LastBaseSetupName", "")
    elif target_base_setup:
        replace_simple_text(target_root, "LastBaseSetupName", target_base_setup)
    if target_media:
        replace_simple_text(target_root, "MediaName", target_media)
    if target_output_icc:
        replace_simple_text(target_root, "IccOutFileName", target_output_icc)
    if mapping_row.target_input_rgb:
        replace_simple_text(target_root, "IccInRGBFileName", mapping_row.target_input_rgb)
    if mapping_row.target_input_cmyk:
        replace_simple_text(target_root, "IccInCMYKFileName", mapping_row.target_input_cmyk)
    if mapping_row.target_pallet:
        replace_simple_text(target_root, "TableName", mapping_row.target_pallet)


def parse_ksf_bytes(data: bytes) -> ET.Element:
    return cast(ET.Element, ET.fromstring(data))


def get_text(root: ET.Element, tag: str) -> str:
    return (root.findtext(tag) or "").strip()


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


def detect_mapping_family(root: ET.Element | None) -> str | None:
    if root is None:
        return None

    media_name = normalize(get_text(root, "MediaName"))
    set_applied = normalize(get_text(root, "SetApplied"))
    last_base_setup_name = normalize(get_text(root, "LastBaseSetupName"))
    icc_out = normalize(get_text(root, "IccOutFileName"))
    table_name = normalize(get_text(root, "TableName"))
    machine_type = normalize(get_text(root, "MachineType"))

    haystack = " ".join(
        [
            media_name,
            set_applied,
            last_base_setup_name,
            icc_out,
            table_name,
            machine_type,
        ]
    )

    if "atlas max poly" in haystack or "maxpoly" in haystack or "atl poly" in haystack:
        return "poly"
    if "av hd6" in haystack or "avhd6" in haystack:
        return "avhd6"
    if "atlas max+" in haystack or "atlas max plus" in haystack:
        return "plus"
    if "vulcan" in haystack:
        return "vulcan"
    if "atlas" in haystack:
        return "atlas"
    return None


def families_are_compatible(detected_family: str | None, row_family: str) -> bool:
    if not detected_family or row_family == "unknown":
        return True
    if detected_family == row_family:
        return True

    compatible_families = {
        "atlas": {"atlas", "plus"},
        "plus": {"plus", "atlas"},
        "max": {"max", "atlas", "plus"},
        "avhd6": {"avhd6"},
    }
    return row_family in compatible_families.get(detected_family, {detected_family})


def get_cross_direction_families(direction: str) -> tuple[str, str]:
    if direction == "plus_to_poly":
        return "plus", "poly"
    if direction == "max_to_poly":
        return "atlas", "poly"
    if direction == "avhd6_to_plus":
        return "avhd6", "plus"
    if direction == "plus_to_avhd6":
        return "plus", "avhd6"
    return "poly", "plus"


def validate_cross_direction(
    source_root: ET.Element,
    template_root: ET.Element | None,
    direction: str,
) -> str | None:
    expected_source_family, expected_target_family = get_cross_direction_families(direction)
    detected_source_family = detect_mapping_family(source_root)
    detected_target_family = detect_mapping_family(template_root)

    if detected_source_family and not families_are_compatible(detected_source_family, expected_source_family):
        return (
            f"Source file family mismatch for direction `{direction}`. "
            f"Expected `{expected_source_family}`, detected `{detected_source_family}`."
        )

    if (
        template_root is not None
        and detected_target_family
        and not families_are_compatible(detected_target_family, expected_target_family)
    ):
        return (
            f"Output template family mismatch for direction `{direction}`. "
            f"Expected `{expected_target_family}`, detected `{detected_target_family}`."
        )

    return None


def infer_atlas_setup_key(root: ET.Element) -> str | None:
    media_name = normalize(get_text(root, "MediaName"))
    set_applied = normalize(get_text(root, "SetApplied"))
    last_base_setup_name = normalize(get_text(root, "LastBaseSetupName"))
    icc_out = normalize(get_text(root, "IccOutFileName"))

    primary_text = f" {media_name} {set_applied} {last_base_setup_name} {icc_out} "

    if "dark" in primary_text or "black" in primary_text:
        if "hq" in primary_text:
            return "black_hq"
        if "std" in primary_text or "standard" in primary_text:
            return "black_std"
        if any(token in primary_text for token in ["high production", "highproduction", " hp "]):
            return "black_high_production"

    if "light" in primary_text and any(
        token in primary_text for token in ["high production", "highproduction"]
    ):
        return "light_high_production"
    if "light" in primary_text and "hq" in primary_text:
        return "light_hq"
    if "light" in primary_text and ("std" in primary_text or "standard" in primary_text):
        return "light_std"

    return None


def apply_atlas_setup_mapping(target_root: ET.Element, atlas_setup_key: str | None) -> None:
    if not atlas_setup_key:
        return
    mapping = ATLAS_SETUP_MAP.get(atlas_setup_key)
    if not mapping:
        return

    media_name, icc_out = get_canonical_atlas_targets(
        mapping["set_applied"],
        mapping["media_name"],
        mapping["icc_out"],
    )

    replace_simple_text(target_root, "SetApplied", mapping["set_applied"])
    replace_simple_text(target_root, "LastBaseSetupName", mapping["last_base_setup_name"])
    replace_simple_text(target_root, "MediaName", media_name)
    replace_simple_text(target_root, "IccOutFileName", icc_out)


def detect_profile(root: ET.Element) -> dict:
    fields = {
        "table_name": get_text(root, "TableName"),
        "media_name": get_text(root, "MediaName"),
        "set_applied": get_text(root, "SetApplied"),
        "last_base_setup_name": get_text(root, "LastBaseSetupName"),
        "machine_type": get_text(root, "MachineType"),
        "white_pass": get_text(root, "WhitePass"),
        "icc_out": get_text(root, "IccOutFileName"),
        "x_offset": get_text(root, "XOffsetMM"),
        "y_offset": get_text(root, "YOffsetMM"),
        "spray_amount": get_text(root, "SprayAmount"),
        "linear_spray_amount": get_text(root, "LinearSprayAmount"),
        "max_opacity": get_text(root, "MaxOpacity"),
        "min_opacity": get_text(root, "MinOpacity"),
        "choke_white_pixels": get_text(root, "ChokeWhitePixels"),
        "highlight_opacity": get_text(root, "HighlightOpacity"),
        "print_speed": get_text(root, "PrintSpeed"),
        "print_speed2": get_text(root, "PrintSpeed2"),
        "print_direction": get_text(root, "PrintDirection"),
        "is_spray": get_text(root, "IsSpray"),
        "is_wipe": get_text(root, "IsWipe"),
        "factory": get_text(root, "Factory"),
        "sharpen": get_text(root, "Sharpen"),
        "icc_in_rgb": get_text(root, "IccInRGBFileName"),
        "icc_in_cmyk": get_text(root, "IccInCMYKFileName"),
        "rendering_intent": get_text(root, "RenderingIntent"),
        "delay_spray_to_print": get_text(root, "DelaySprayToPrint"),
        "layer_delay_1_to_2": get_text(root, "LayerDelay1to2"),
        "layer_delay_2_to_3": get_text(root, "LayerDelay2to3"),
        "max_discharge": get_text(root, "MaxDischarge"),
        "use_discharge": get_text(root, "UseDischarge"),
        "discharge_opacity": get_text(root, "DischargeOpacity"),
        "min_discharge": get_text(root, "MinDischarge"),
        "choke_discharge_pixels": get_text(root, "ChokeDischargePixels"),
        "color_knockout": get_text(root, "ColorKnockout"),
        "white_knockout": get_text(root, "WhiteKnockout"),
        "image_position": get_text(root, "ImagePosition"),
        "copies": get_text(root, "TotalCopies"),
        "atlas_setup_key": infer_atlas_setup_key(root) or "",
        "mapping_status": "",
        "mapping_source": "",
        "mapped_atlas_setup": "",
        "mapped_atlas_media": "",
        "mapped_atlas_output_icc": "",
        "mapped_atlas_input_rgb": "",
    }
    haystack = normalize(
        " ".join(
            [
                fields["table_name"],
                fields["media_name"],
                fields["set_applied"],
                fields["last_base_setup_name"],
            ]
        )
    )

    detected = {
        "shirt_family": "unknown",
        "recommended_atlas_family": "review",
        "warnings": [],
    }

    if any(key in haystack for key in ["black t shirt", "black tshirt", "black shirt", " black "]):
        detected["shirt_family"] = "black"
        detected["recommended_atlas_family"] = "black"
        detected["warnings"].append(
            "Source indicates a Black T-shirt. Recommendation: validate a Black setup in Atlas Max."
        )
    elif any(key in haystack for key in ["dark", "charcoal", "navy", "burgundy"]):
        detected["shirt_family"] = "dark"
        detected["recommended_atlas_family"] = "black"
        detected["warnings"].append(
            "Source indicates a dark garment. Recommendation: validate a Black setup in Atlas Max."
        )
    elif any(key in haystack for key in ["light", "white", "paper", "transparent"]):
        detected["shirt_family"] = "light"
        detected["recommended_atlas_family"] = "light"
    elif any(key in haystack for key in ["color", "premium", "poly", "cotton"]):
        detected["shirt_family"] = "color"
        detected["recommended_atlas_family"] = "color"

    if fields["machine_type"]:
        detected["warnings"].append(f"Source file detected as {fields['machine_type']}.")

    return {**fields, **detected}


def compare_with_template(source_info: dict, template_info: dict) -> list[str]:
    warnings = list(source_info["warnings"])
    if not source_info.get("mapped_atlas_setup"):
        warnings.append("No spreadsheet mapping was found for this source file. Review required.")
    return warnings



def replace_or_append(parent: ET.Element, child: ET.Element) -> None:
    existing = parent.find(child.tag)
    child_copy = copy.deepcopy(child)
    if existing is None:
        parent.append(child_copy)
    else:
        index = list(parent).index(existing)
        parent.remove(existing)
        parent.insert(index, child_copy)


# Only replace existing tag, do not append if missing
def replace_existing_only(parent: ET.Element, child: ET.Element) -> None:
    existing = parent.find(child.tag)
    if existing is None:
        return
    index = list(parent).index(existing)
    parent.remove(existing)
    parent.insert(index, copy.deepcopy(child))


def preserve_geometry(source_root: ET.Element, target_root: ET.Element) -> None:
    for tag in GEOMETRY_TAGS:
        source_node = source_root.find(tag)
        if source_node is not None:
            replace_existing_only(target_root, source_node)


def preserve_copies(source_root: ET.Element, target_root: ET.Element) -> None:
    for tag in COPY_TAGS:
        source_node = source_root.find(tag)
        if source_node is not None:
            replace_existing_only(target_root, source_node)



def replace_simple_text(root: ET.Element, tag: str, value: str) -> None:
    node = root.find(tag)
    if node is None:
        node = ET.SubElement(root, tag)
    node.text = value


def get_canonical_atlas_targets(
    atlas_setup: str, fallback_media: str, fallback_icc_out: str
) -> tuple[str, str]:
    canonical = CANONICAL_ATLAS_TARGETS.get(atlas_setup)
    if canonical is None:
        return fallback_media, fallback_icc_out
    return canonical["media_name"], canonical["icc_out"]


def sync_strip_geometry_from_root(target_root: ET.Element) -> None:
    strip_params = target_root.findall("./Strips/StripParam")
    if not strip_params:
        return

    tags_to_sync = [
        "XOffsetMM",
        "YOffsetMM",
        "WidthMM",
        "HeightMM",
        "XCenter",
        "YCenter",
        "KeepRatio",
        "Rotate90",
        "Rotate180",
        "RotateSmallDegree",
        "Mirror",
    ]

    for strip in strip_params:
        for tag in tags_to_sync:
            source_node = target_root.find(tag)
            if source_node is not None:
                replace_existing_only(strip, source_node)


# Special separation rules function
def apply_special_separation_rules(target_root: ET.Element) -> None:
    special_separations = target_root.find("SpecialSeparations")
    if special_separations is None:
        return

    existing_models = {
        model.findtext("Name", default="").strip(): model
        for model in special_separations.findall("SpecialSepModel")
    }

    for name, config in SPECIAL_SEPARATION_RULES.items():
        model = existing_models.get(name)
        if model is None:
            model = ET.SubElement(special_separations, "SpecialSepModel")
            ET.SubElement(model, "Name").text = name
            ET.SubElement(model, "Enable").text = "true"
            ET.SubElement(model, "MaxCoverage").text = "0"
            ET.SubElement(model, "IsMaxCoverage").text = "false"
            ET.SubElement(model, "Solid").text = "0"
            ET.SubElement(model, "GradedEdgeOrStrokePixelsAmount").text = "4"
            ET.SubElement(model, "GradedEdgeOrStrokeLevel").text = "30"
            ET.SubElement(model, "DefaultGradedEdgeOrStrokePixelsAmount").text = "4"
            ET.SubElement(model, "DefaultGradedEdgeOrStrokeLevel").text = "30"
            ET.SubElement(model, "ChannelIndex").text = "0"

        replace_simple_text(model, "Enable", "true")
        replace_simple_text(model, "Solid", config["solid"])
        replace_simple_text(model, "MaxCoverage", config["max_coverage"])
        replace_simple_text(model, "IsMaxCoverage", config["is_max_coverage"])


def apply_cross_special_separation_rules(source_root: ET.Element, target_root: ET.Element) -> None:
    source_specials = source_root.find("SpecialSeparations")
    target_specials = target_root.find("SpecialSeparations")
    if target_specials is None:
        return

    source_models = {}
    if source_specials is not None:
        source_models = {
            (model.findtext("Name", default="").strip()): model
            for model in source_specials.findall("SpecialSepModel")
        }

    target_models = {
        (model.findtext("Name", default="").strip()): model
        for model in target_specials.findall("SpecialSepModel")
    }

    for name in ("Qw", "Qc"):
        source_model = source_models.get(name)
        target_model = target_models.get(name)
        if source_model is None or target_model is None:
            continue
        for tag in ("Enable", "Solid", "MaxCoverage", "IsMaxCoverage"):
            value = get_text(source_model, tag)
            if value:
                replace_simple_text(target_model, tag, value)

    pe_model = target_models.get("PE")
    if pe_model is not None:
        replace_simple_text(pe_model, "Enable", "true")
        replace_simple_text(pe_model, "Solid", "0")
        replace_simple_text(pe_model, "MaxCoverage", "40")
        replace_simple_text(pe_model, "IsMaxCoverage", "true")


def format_number(value: float, original_text: str | None) -> str:
    if original_text and "." in original_text:
        decimals = len(original_text.split(".")[-1])
        return f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def apply_delta_to_tag(parent: ET.Element, tag: str, delta: float) -> None:
    node = parent.find(tag)
    if node is None or node.text is None:
        return
    original = node.text.strip()
    value = float(original)
    node.text = format_number(value + delta, original)


def apply_offset_delta(root: ET.Element, x_delta: float, y_delta: float) -> None:
    if x_delta:
        apply_delta_to_tag(root, "XOffsetMM", x_delta)
        for strip in root.findall("./Strips/StripParam"):
            apply_delta_to_tag(strip, "XOffsetMM", x_delta)
    if y_delta:
        apply_delta_to_tag(root, "YOffsetMM", y_delta)
        for strip in root.findall("./Strips/StripParam"):
            apply_delta_to_tag(strip, "YOffsetMM", y_delta)


def build_converted_root(
    source_root: ET.Element,
    template_tree: ET.ElementTree,
    geometry_mode: str,
    copies_mode: str,
    set_name_mode: str,
    output_stem: str,
    x_delta: float,
    y_delta: float,
) -> ET.Element:
    target_root = cast(ET.Element, copy.deepcopy(template_tree.getroot()))
    white_support_type = target_root.attrib.get("WhiteSupportType", "WBCICC")
    target_root.attrib.clear()
    for key, value in ROOT_ATTRS.items():
        target_root.set(key, value)
    target_root.set("WhiteSupportType", white_support_type)

    for tag in SOURCE_PASSTHROUGH_TAGS:
        source_node = source_root.find(tag)
        if source_node is not None:
            replace_existing_only(target_root, source_node)

    if geometry_mode == "source":
        preserve_geometry(source_root, target_root)
        sync_strip_geometry_from_root(target_root)

    if copies_mode == "source":
        preserve_copies(source_root, target_root)

    mapping_row = find_legacy_mapping_row(source_root)
    if mapping_row is not None:
        apply_legacy_mapping_row(target_root, mapping_row)
    else:
        atlas_setup_key = infer_atlas_setup_key(source_root)
        apply_atlas_setup_mapping(target_root, atlas_setup_key)
    replace_simple_text(target_root, "IccInRGBFileName", "None")
    replace_simple_text(target_root, "IccInCMYKFileName", "None")

    apply_offset_delta(target_root, x_delta, y_delta)
    sync_strip_geometry_from_root(target_root)
    return target_root


def serialize_xml(root: ET.Element) -> bytes:
    xml_bytes = ET.tostring(cast(Any, root), encoding="utf-8")
    xml_text = '<?xml version="1.0" encoding="utf-8"?>\n' + xml_bytes.decode("utf-8")
    return xml_text.encode("utf-8")


def convert_one(
    source_path: Path,
    template_tree: ET.ElementTree,
    output_path: Path,
    geometry_mode: str,
    copies_mode: str,
    set_name_mode: str,
    x_delta: float,
    y_delta: float,
) -> None:
    source_tree = load_xml(source_path)
    source_root = cast(ET.Element, source_tree.getroot())
    target_root = build_converted_root(
        source_root=source_root,
        template_tree=template_tree,
        geometry_mode=geometry_mode,
        copies_mode=copies_mode,
        set_name_mode=set_name_mode,
        output_stem=output_path.stem,
        x_delta=x_delta,
        y_delta=y_delta,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(serialize_xml(target_root))


def build_preview(files: list[SourceItem], template_name: str, template_bytes: bytes) -> dict:
    template_root = parse_ksf_bytes(template_bytes)
    template_info = detect_profile(template_root)
    mapping_workbook_name, _ = load_legacy_mapping_rows()

    items = []
    for item in files:
        filename = item.relative_path.as_posix()
        try:
            root = parse_ksf_bytes(item.data)
            source_info = detect_profile(root)
            mapping_row = find_legacy_mapping_row(root)
            if mapping_row is not None:
                source_info["mapping_status"] = mapping_row.status or "mapped"
                source_info["mapping_source"] = mapping_workbook_name or "mapping workbook"
                source_info["mapped_atlas_setup"] = mapping_row.target_setup
                source_info["mapped_atlas_media"] = mapping_row.target_media
                source_info["mapped_atlas_output_icc"] = mapping_row.target_output_icc
            else:
                source_info["mapping_status"] = "review"
                source_info["mapping_source"] = "no spreadsheet match"
                source_info["mapped_atlas_setup"] = ""
                source_info["mapped_atlas_media"] = ""
                source_info["mapped_atlas_output_icc"] = ""

            items.append(
                {
                    "filename": filename,
                    "origin": item.origin,
                    "status": "ready",
                    "source": source_info,
                    "template": template_info,
                    "warnings": compare_with_template(source_info, template_info),
                    "recommended_setup": source_info["recommended_atlas_family"],
                    "error": None,
                }
            )
        except ET.ParseError as exc:
            items.append(
                {
                    "filename": filename,
                    "origin": item.origin,
                    "status": "error",
                    "source": None,
                    "template": template_info,
                    "warnings": [],
                    "recommended_setup": "review",
                    "error": f"Invalid XML in source file: {exc}",
                }
            )

    return {
        "template_filename": template_name,
        "template": template_info,
        "mapping_workbook": mapping_workbook_name,
        "items": items,
    }


def convert_sources(
    source_parts: list[SourceItem],
    template_bytes: bytes,
    geometry_mode: str,
    copies_mode: str,
    set_name_mode: str,
    x_delta: float,
    y_delta: float,
) -> list[ConvertedItem]:
    template_root = parse_ksf_bytes(template_bytes)
    template_tree = ET.ElementTree(template_root)
    results: list[ConvertedItem] = []

    for source in source_parts:
        output_path = Path("converted") / source.relative_path.name
        try:
            source_root = parse_ksf_bytes(source.data)
            converted_root = build_converted_root(
                source_root=source_root,
                template_tree=template_tree,
                geometry_mode=geometry_mode,
                copies_mode=copies_mode,
                set_name_mode=set_name_mode,
                output_stem=output_path.stem,
                x_delta=x_delta,
                y_delta=y_delta,
            )
            results.append(
                ConvertedItem(
                    relative_path=source.relative_path,
                    output_path=output_path,
                    data=serialize_xml(converted_root),
                    status="converted",
                    error=None,
                )
            )
        except Exception as exc:
            results.append(
                ConvertedItem(
                    relative_path=source.relative_path,
                    output_path=output_path,
                    data=None,
                    status="error",
                    error=str(exc),
                )
            )

    return results


def build_converted_root_cross(
    source_root: ET.Element,
    template_tree: ET.ElementTree,
    direction: str,
    geometry_mode: str,
    copies_mode: str,
    set_name_mode: str,
    output_stem: str,
    x_delta: float,
    y_delta: float,
    pallet_override: str | None = None,
) -> ET.Element:
    target_root = cast(ET.Element, copy.deepcopy(template_tree.getroot()))
    white_support_type = target_root.attrib.get("WhiteSupportType", "WBCICC")
    target_root.attrib.clear()
    for key, value in ROOT_ATTRS.items():
        target_root.set(key, value)
    target_root.set("WhiteSupportType", white_support_type)

    for tag in SOURCE_PASSTHROUGH_TAGS:
        source_node = source_root.find(tag)
        if source_node is not None:
            replace_existing_only(target_root, source_node)

    if geometry_mode == "source":
        preserve_geometry(source_root, target_root)
        sync_strip_geometry_from_root(target_root)

    if copies_mode == "source":
        preserve_copies(source_root, target_root)

    direction_error = validate_cross_direction(source_root, target_root, direction)
    if direction_error:
        raise ValueError(direction_error)

    expected_source_family, expected_target_family = get_cross_direction_families(direction)
    mapping_row = find_mapping_row(
        source_root,
        target_root,
        expected_source_family=expected_source_family,
        expected_target_family=expected_target_family,
    )
    if mapping_row is not None:
        apply_mapping_row(target_root, mapping_row)

    apply_cross_special_separation_rules(source_root, target_root)

    if set_name_mode == "source-file":
        replace_simple_text(target_root, "SetApplied", output_stem)

    if pallet_override:
        replace_simple_text(target_root, "TableName", pallet_override)

    apply_offset_delta(target_root, x_delta, y_delta)
    sync_strip_geometry_from_root(target_root)
    return target_root


def build_preview_cross(
    files: list[SourceItem],
    template_name: str,
    template_bytes: bytes,
    direction: str,
) -> dict:
    template_root = parse_ksf_bytes(template_bytes)
    template_info = detect_profile(template_root)
    mapping_workbook_name, _ = load_mapping_rows()
    expected_source_family, expected_target_family = get_cross_direction_families(direction)

    items = []
    for item in files:
        filename = item.relative_path.as_posix()
        try:
            root = parse_ksf_bytes(item.data)
            source_info = detect_profile(root)
            direction_error = validate_cross_direction(root, template_root, direction)
            if direction_error:
                items.append(
                    {
                        "filename": filename,
                        "origin": item.origin,
                        "status": "error",
                        "source": source_info,
                        "template": template_info,
                        "warnings": [],
                        "error": direction_error,
                    }
                )
                continue
            mapping_row = find_mapping_row(
                root,
                template_root,
                expected_source_family=expected_source_family,
                expected_target_family=expected_target_family,
            )
            if mapping_row is not None:
                source_info["mapping_status"] = mapping_row.status or "mapped"
                source_info["mapping_source"] = f"{mapping_row.workbook_name} / {mapping_row.sheet_name}"
                source_info["mapped_atlas_setup"] = mapping_row.target_base_setup or mapping_row.target_setup
                source_info["mapped_atlas_media"] = mapping_row.target_media
                source_info["mapped_atlas_output_icc"] = mapping_row.target_output_icc
                source_info["mapped_atlas_input_rgb"] = mapping_row.target_input_rgb
            else:
                source_info["mapping_status"] = "review"
                source_info["mapping_source"] = mapping_workbook_name or "no spreadsheet match"
                source_info["mapped_atlas_setup"] = ""
                source_info["mapped_atlas_media"] = ""
                source_info["mapped_atlas_output_icc"] = ""
                source_info["mapped_atlas_input_rgb"] = ""

            items.append(
                {
                    "filename": filename,
                    "origin": item.origin,
                    "status": "ready",
                    "source": source_info,
                    "template": template_info,
                    "warnings": compare_with_template(source_info, template_info),
                    "error": None,
                }
            )
        except ET.ParseError as exc:
            items.append(
                {
                    "filename": filename,
                    "origin": item.origin,
                    "status": "error",
                    "source": None,
                    "template": template_info,
                    "warnings": [],
                    "error": f"Invalid XML in source file: {exc}",
                }
            )

    return {
        "template_filename": template_name,
        "template": template_info,
        "mapping_workbook": mapping_workbook_name,
        "items": items,
    }


def convert_sources_cross(
    source_parts: list[SourceItem],
    template_bytes: bytes,
    direction: str,
    geometry_mode: str,
    copies_mode: str,
    set_name_mode: str,
    x_delta: float,
    y_delta: float,
    pallet_override: str | None = None,
) -> list[ConvertedItem]:
    template_root = parse_ksf_bytes(template_bytes)
    template_tree = ET.ElementTree(template_root)
    results: list[ConvertedItem] = []

    for source in source_parts:
        output_path = Path("converted") / source.relative_path.name
        try:
            source_root = parse_ksf_bytes(source.data)
            converted_root = build_converted_root_cross(
                source_root=source_root,
                template_tree=template_tree,
                direction=direction,
                geometry_mode=geometry_mode,
                copies_mode=copies_mode,
                set_name_mode=set_name_mode,
                output_stem=output_path.stem,
                x_delta=x_delta,
                y_delta=y_delta,
                pallet_override=pallet_override,
            )
            results.append(
                ConvertedItem(
                    relative_path=source.relative_path,
                    output_path=output_path,
                    data=serialize_xml(converted_root),
                    status="converted",
                    error=None,
                )
            )
        except Exception as exc:
            results.append(
                ConvertedItem(
                    relative_path=source.relative_path,
                    output_path=output_path,
                    data=None,
                    status="error",
                    error=str(exc),
                )
            )

    return results


def build_conversion_report(preview: dict, converted_items: list[ConvertedItem]) -> dict:
    status_map = {item.relative_path.as_posix(): item for item in converted_items}
    report_items = []
    for preview_item in preview["items"]:
        converted_item = status_map.get(preview_item["filename"])
        report_items.append(
            {
                **preview_item,
                "conversion_status": converted_item.status if converted_item else "not-run",
                "output_filename": converted_item.output_path.as_posix() if converted_item else None,
                "conversion_error": converted_item.error if converted_item else None,
            }
        )

    return {
        "template_filename": preview["template_filename"],
        "template": preview["template"],
        "items": report_items,
    }


def generate_zip_bundle(converted_items: list[ConvertedItem], report: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in converted_items:
            if item.data is None:
                continue
            output_path = item.output_path
            if output_path.name == ".DS_Store":
                continue
            if any(part.startswith("._") for part in output_path.parts):
                continue
            if "__MACOSX" in output_path.parts:
                continue
            zf.writestr(output_path.as_posix(), item.data)
        zf.writestr("converted/conversion-report.json", json.dumps(report, indent=2, ensure_ascii=False))
    return buffer.getvalue()


def family_label(value: str) -> str:
    labels = {
        "black": "BLACK",
        "light": "LIGHT",
        "color": "COLOR",
        "review": "REVIEW",
        "unknown": "UNKNOWN",
    }
    return labels.get(value, value.upper())


def render_kpis(source_parts: list[SourceItem], template_name: str | None, preview: dict | None) -> None:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Input", f"{len(source_parts)} file(s)")
    with col2:
        st.metric("Template", template_name or "None")
    with col3:
        if not preview:
            st.metric("Warnings", 0)
        else:
            warnings_count = sum(len(item["warnings"]) for item in preview["items"])
            invalid_count = sum(1 for item in preview["items"] if item["status"] == "error")
            st.metric("Warnings", warnings_count + invalid_count)


def render_preview_legacy(preview: dict) -> None:
    priority_warnings = [
        (item["filename"], warning)
        for item in preview["items"]
        for warning in item["warnings"]
    ]
    invalid_count = sum(1 for item in preview["items"] if item["status"] == "error")
    summary_parts = [f"{len(preview['items'])} file(s) analyzed"]
    if priority_warnings:
        summary_parts.append(f"{len(priority_warnings)} warning(s)")
    if invalid_count:
        summary_parts.append(f"{invalid_count} invalid file(s)")

    with st.expander(f"Operational review and analyzed files ({' | '.join(summary_parts)})", expanded=False):
        st.subheader("Operational review")
        if preview.get("mapping_workbook"):
            st.caption(f"Mapping workbook: {preview['mapping_workbook']}")
        else:
            st.caption("Mapping workbook: unavailable because openpyxl is not installed or no workbook was found.")
        template = preview["template"]
        st.caption(
            f"Atlas template: {template['media_name'] or 'N/A'} | "
            f"Setup: {template['last_base_setup_name'] or template['set_applied'] or 'N/A'}"
        )

        if priority_warnings:
            for filename, warning in priority_warnings:
                st.warning(f"{filename}: {warning}")
        else:
            st.success("No critical warnings detected in the initial analysis.")

        st.subheader("Analyzed files")
        for item in preview["items"]:
            with st.container(border=True):
                top_a, top_b = st.columns([2.2, 1])
                with top_a:
                    st.markdown(f"**{item['filename']}**")
                    st.caption(f"Input mode: {item['origin'].upper()}")
                    if item["status"] == "error":
                        st.error(item["error"])
                        continue
                    st.write(
                        f"Source media: `{item['source']['media_name'] or 'N/A'}`  \n"
                        f"Source setup: `{item['source']['last_base_setup_name'] or item['source']['set_applied'] or 'N/A'}`  \n"
                        f"Mapping source: `{item['source'].get('mapping_source') or 'N/A'}`  \n"
                        f"Mapped Atlas setup: `{item['source'].get('mapped_atlas_setup') or 'N/A'}`  \n"
                        f"Mapped Atlas media: `{item['source'].get('mapped_atlas_media') or 'N/A'}`  \n"
                        f"Mapped Atlas output ICC: `{item['source'].get('mapped_atlas_output_icc') or 'N/A'}`  \n"
                        "Matching priority: Vulcan output ICC first, setup second, Vulcan media as support, and input profile as a light support signal. The spreadsheet is not treated as a strict horizontal all-fields-must-match rule. Special separations in the output are forced to: Qc = 25 solid, Qw = 65 max coverage, Iw = 25 solid, Ic = 25 solid."
                    )
                with top_b:
                    st.metric("Mapping status", (item["source"].get("mapping_status") or "review").upper())
                    st.caption(
                        f"Atlas setup: {item['source'].get('mapped_atlas_setup') or 'N/A'} | "
                        f"Atlas media: {item['source'].get('mapped_atlas_media') or 'N/A'} | "
                        f"Atlas output ICC: {item['source'].get('mapped_atlas_output_icc') or 'N/A'}"
                    )

                st.caption(
                    f"X: {item['source']['x_offset'] or 'N/A'} | "
                    f"Y: {item['source']['y_offset'] or 'N/A'} | "
                    f"Spray: {item['source']['spray_amount'] or 'N/A'} | "
                    f"Linear Spray: {item['source']['linear_spray_amount'] or 'N/A'} | "
                    f"MaxOpacity: {item['source']['max_opacity'] or 'N/A'} | "
                    f"MinOpacity: {item['source']['min_opacity'] or 'N/A'} | "
                    f"ChokeWhitePixels: {item['source']['choke_white_pixels'] or 'N/A'} | "
                    f"HighlightOpacity: {item['source']['highlight_opacity'] or 'N/A'} | "
                    f"PrintSpeed: {item['source']['print_speed'] or 'N/A'} | "
                    f"PrintDirection: {item['source']['print_direction'] or 'N/A'}"
                )

                if item["warnings"]:
                    for warning in item["warnings"]:
                        st.warning(warning)
                else:
                    st.success("Spreadsheet mapping found. Conversion is ready for initial testing with preserved source coordinates and other compatible variable values.")


def render_preview_cross(preview: dict) -> None:
    priority_warnings = [
        (item["filename"], warning)
        for item in preview["items"]
        for warning in item["warnings"]
    ]
    invalid_count = sum(1 for item in preview["items"] if item["status"] == "error")
    summary_parts = [f"{len(preview['items'])} file(s) analyzed"]
    if priority_warnings:
        summary_parts.append(f"{len(priority_warnings)} warning(s)")
    if invalid_count:
        summary_parts.append(f"{invalid_count} invalid file(s)")

    with st.expander(f"Operational review and analyzed files ({' | '.join(summary_parts)})", expanded=False):
        st.subheader("Operational review")
        if preview.get("mapping_workbook"):
            st.caption(f"Mapping workbook: {preview['mapping_workbook']}")
        else:
            st.caption("Mapping workbook: unavailable because openpyxl is not installed or no workbook was found.")
        template = preview["template"]
        st.caption(
            f"Output template: {template['media_name'] or 'N/A'} | "
            f"Setup: {template['last_base_setup_name'] or template['set_applied'] or 'N/A'}"
        )

        if priority_warnings:
            for filename, warning in priority_warnings:
                st.warning(f"{filename}: {warning}")
        else:
            st.success("No critical warnings detected in the initial analysis.")

        st.subheader("Analyzed files")
        for item in preview["items"]:
            with st.container(border=True):
                top_a, top_b = st.columns([2.2, 1])
                with top_a:
                    st.markdown(f"**{item['filename']}**")
                    st.caption(f"Input mode: {item['origin'].upper()}")
                    if item["status"] == "error":
                        st.error(item["error"])
                        continue
                    st.write(
                        f"Source base setup: `{item['source']['last_base_setup_name'] or 'N/A'}`  \n"
                        f"Source media: `{item['source']['media_name'] or 'N/A'}`  \n"
                        f"Source output ICC: `{item['source']['icc_out'] or 'N/A'}`  \n"
                        f"Source input RGB: `{item['source']['icc_in_rgb'] or 'N/A'}`  \n"
                        f"Mapping source: `{item['source'].get('mapping_source') or 'N/A'}`  \n"
                        f"Mapped target setup: `{item['source'].get('mapped_atlas_setup') or 'N/A'}`  \n"
                        f"Mapped target media: `{item['source'].get('mapped_atlas_media') or 'N/A'}`  \n"
                        f"Mapped target output ICC: `{item['source'].get('mapped_atlas_output_icc') or 'N/A'}`  \n"
                        f"Mapped target input RGB: `{item['source'].get('mapped_atlas_input_rgb') or 'N/A'}`  \n"
                        "Cross-conversion mapping follows the workbook entries. Matching priority is: Base Setup first, Media second, Output ICC third, and Input RGB as a support signal. When one reliable match identifies the row, the app applies the full mapped target package from that spreadsheet row."
                    )
                with top_b:
                    st.metric("Mapping status", (item["source"].get("mapping_status") or "review").upper())
                    st.caption(
                        f"Target setup: {item['source'].get('mapped_atlas_setup') or 'N/A'} | "
                        f"Target media: {item['source'].get('mapped_atlas_media') or 'N/A'} | "
                        f"Target output ICC: {item['source'].get('mapped_atlas_output_icc') or 'N/A'} | "
                        f"Target input RGB: {item['source'].get('mapped_atlas_input_rgb') or 'N/A'}"
                    )

                st.caption(
                    f"X: {item['source']['x_offset'] or 'N/A'} | "
                    f"Y: {item['source']['y_offset'] or 'N/A'} | "
                    f"Spray: {item['source']['spray_amount'] or 'N/A'} | "
                    f"Linear Spray: {item['source']['linear_spray_amount'] or 'N/A'} | "
                    f"MaxOpacity: {item['source']['max_opacity'] or 'N/A'} | "
                    f"MinOpacity: {item['source']['min_opacity'] or 'N/A'} | "
                    f"ChokeWhitePixels: {item['source']['choke_white_pixels'] or 'N/A'} | "
                    f"HighlightOpacity: {item['source']['highlight_opacity'] or 'N/A'} | "
                    f"PrintSpeed: {item['source']['print_speed'] or 'N/A'} | "
                    f"PrintDirection: {item['source']['print_direction'] or 'N/A'}"
                )

                if item["warnings"]:
                    for warning in item["warnings"]:
                        st.warning(warning)
                else:
                    st.success("Spreadsheet mapping found. Conversion is ready for initial testing with preserved source coordinates and other compatible variable values.")


def render_conversion_results(converted_items: list[ConvertedItem], report: dict) -> None:
    st.subheader("Conversion output")
    success_count = sum(1 for item in converted_items if item.status == "converted")
    error_count = sum(1 for item in converted_items if item.status == "error")
    st.caption(f"Converted: {success_count} | Failed: {error_count}")
    failed_items = [item for item in converted_items if item.status == "error"]
    if failed_items:
        with st.container(border=True):
            st.markdown("**Failed files**")
            for item in failed_items[:10]:
                st.error(f"{item.relative_path.as_posix()}: {item.error or 'Conversion failed.'}")
            if len(failed_items) > 10:
                st.caption(f"And {len(failed_items) - 10} more failed file(s). Check `conversion-report.json` inside the ZIP.")
    else:
        st.success("All files were converted successfully. Download the ZIP package below.")


def render_conversion_workspace(
    *,
    session_prefix: str,
    template_heading: str,
    template_toggle_label: str,
    template_upload_caption: str,
    template_upload_label: str,
    source_caption: str,
    source_label: str,
    workflow_info: str,
    analyze_error: str,
    build_preview_fn: Any,
    convert_sources_fn: Any,
    render_preview_fn: Any,
    theme: str = "legacy",
    theme_variant: str | None = None,
    direction_options: list[tuple[str, str]] | None = None,
    hero_kicker: str | None = None,
    hero_title: str | None = None,
    hero_copy: str | None = None,
    hero_chips: list[str] | None = None,
) -> None:
    geometry_mode = "source"
    copies_mode = "source"
    set_name_mode = "template"
    x_delta = 0.0
    y_delta = 0.0

    default_template_name, default_template_bytes = load_default_template_bytes()
    uploader_nonce_key = f"{session_prefix}_uploader_nonce"
    uploader_nonce = st.session_state.setdefault(uploader_nonce_key, 0)

    resolved_theme_variant = theme_variant or theme
    section_card_class = "section-card cross-section-card" if theme == "cross" else "section-card"
    if theme == "cross":
        section_card_class = f"{section_card_class} theme-{resolved_theme_variant}-card"
        workspace_class = f"cross-workspace theme-{resolved_theme_variant}-workspace"
        hero_class = f"cross-hero theme-{resolved_theme_variant}-hero"
    else:
        section_card_class = f"{section_card_class} theme-{resolved_theme_variant}-card"
        workspace_class = f"legacy-workspace theme-{resolved_theme_variant}-workspace"
        hero_class = ""
    if theme == "cross":
        resolved_hero_kicker = hero_kicker or "Dedicated Cross-Mapping Workspace"
        resolved_hero_title = hero_title or "Atlas Max+ <-> Poly Mapping Station"
        resolved_hero_copy = hero_copy or (
            "Spreadsheet-driven conversion for stable setup/media/ICC mappings. This workspace is isolated "
            "from the approved Vulcan flow and is meant for directional mapping validation and controlled rollout."
        )
        resolved_hero_chips = hero_chips or [
            "Base Setup Priority",
            "Media Fallback",
            "ICC-Led Recovery",
            "Template-Safe Output",
        ]
        chips_html = "".join(f"<span class='cross-chip'>{chip}</span>" for chip in resolved_hero_chips)
        st.markdown(
            f"""
            <div class="{hero_class}">
                <div class="cross-hero-kicker">{resolved_hero_kicker}</div>
                <div class="cross-hero-title">{resolved_hero_title}</div>
                <div class="cross-hero-copy">{resolved_hero_copy}</div>
                <div class="cross-chip-row">
                    {chips_html}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(f"<div class='{workspace_class}'>", unsafe_allow_html=True)

    direction_value: str | None = None
    if direction_options:
        direction_labels = [label for label, _ in direction_options]
        direction_map = {label: value for label, value in direction_options}
        st.markdown(f"<div class='{section_card_class}'>", unsafe_allow_html=True)
        st.subheader("Conversion direction")
        selected_direction_label = st.radio(
            "Direction",
            options=direction_labels,
            horizontal=True,
            key=f"{session_prefix}_direction",
            label_visibility="collapsed",
        )
        direction_value = direction_map[selected_direction_label]
        st.caption(
            "Select the conversion direction explicitly so the app uses the correct spreadsheet side and expected output template."
        )
        st.markdown("</div>", unsafe_allow_html=True)

    active_template_heading = template_heading
    active_template_toggle_label = template_toggle_label
    active_template_upload_caption = template_upload_caption
    active_template_upload_label = template_upload_label
    active_source_caption = source_caption
    active_source_label = source_label
    active_workflow_info = workflow_info
    active_default_template_name = default_template_name
    active_default_template_bytes = default_template_bytes
    active_preferred_template_names: list[str] = []

    if theme == "cross" and direction_value == "plus_to_poly":
        active_preferred_template_names = PREFERRED_CROSS_TEMPLATE_NAMES["plus_to_poly"]
        active_template_heading = "Poly output template"
        active_template_toggle_label = "Use built-in Poly output template"
        active_template_upload_caption = "Upload a Poly KSF output template."
        active_template_upload_label = "Poly output template"
        active_source_caption = "Upload one or more Atlas Max+ KSF files to convert into Poly."
        active_source_label = "Atlas Max+ source files"
        active_workflow_info = (
            "Direction selected: Plus -> Poly. The app reads Atlas Max+ source fields and searches the "
            "Plus_to_Poly_Mapping sheet by Base Setup first, Media second, Output ICC third, and Input RGB as "
            "a support signal. Once a reliable match is found, the full Poly target package from that row is applied."
        )
        active_default_template_name, active_default_template_bytes = load_preferred_template_bytes(
            PREFERRED_CROSS_TEMPLATE_NAMES["plus_to_poly"]
        )
    elif theme == "cross" and direction_value == "max_to_poly":
        active_preferred_template_names = PREFERRED_CROSS_TEMPLATE_NAMES["max_to_poly"]
        active_template_heading = "Poly output template"
        active_template_toggle_label = "Use built-in Poly output template"
        active_template_upload_caption = "Upload a Poly KSF output template."
        active_template_upload_label = "Poly output template"
        active_source_caption = "Upload one or more Atlas Max KSF files to convert into Poly."
        active_source_label = "Atlas Max source files"
        active_workflow_info = (
            "Direction selected: Max -> Poly. The app reads Atlas Max source fields and searches the "
            "MAX_TO_POLY sheet by Base Setup first, Media second, Output ICC third, and Input RGB as "
            "a support signal. Once a reliable match is found, the full Poly target package from that row is applied."
        )
        active_default_template_name, active_default_template_bytes = load_preferred_template_bytes(
            PREFERRED_CROSS_TEMPLATE_NAMES["max_to_poly"]
        )
    elif theme == "cross" and direction_value == "poly_to_plus":
        active_preferred_template_names = PREFERRED_CROSS_TEMPLATE_NAMES["poly_to_plus"]
        active_template_heading = "Atlas Max+ output template"
        active_template_toggle_label = "Use built-in Atlas Max+ output template"
        active_template_upload_caption = "Upload an Atlas Max+ KSF output template."
        active_template_upload_label = "Atlas Max+ output template"
        active_source_caption = "Upload one or more Poly KSF files to convert into Atlas Max+."
        active_source_label = "Poly source files"
        active_workflow_info = (
            "Direction selected: Poly -> Plus. The app reads Poly source fields and searches the "
            "Poly_to_Plus_Mapping sheet by Base Setup first, Media second, Output ICC third, and Input RGB as "
            "a support signal. Once a reliable match is found, the full Atlas Max+ target package from that row is applied."
        )
        active_default_template_name, active_default_template_bytes = load_preferred_template_bytes(
            PREFERRED_CROSS_TEMPLATE_NAMES["poly_to_plus"]
        )
    elif direction_value == "avhd6_to_plus":
        active_preferred_template_names = PREFERRED_CROSS_TEMPLATE_NAMES["avhd6_to_plus"]
        active_template_heading = "Atlas Max+ output template"
        active_template_toggle_label = "Use built-in Atlas Max+ output template"
        active_template_upload_caption = "Upload an Atlas Max+ KSF output template."
        active_template_upload_label = "Atlas Max+ output template"
        active_source_caption = "Upload one or more AVHD6 KSF files to convert into Atlas Max+."
        active_source_label = "AVHD6 source files"
        active_workflow_info = (
            "Direction selected: AVHD6 -> Plus. The app reads AVHD6 source fields and searches the "
            "AVHD6_TO_PLUS sheet by Base Setup first, Media second, Output ICC third, and Input RGB as "
            "a support signal. Once a reliable match is found, the full Atlas Max+ target package from that row is applied."
        )
        active_default_template_name, active_default_template_bytes = load_preferred_template_bytes(
            PREFERRED_CROSS_TEMPLATE_NAMES["avhd6_to_plus"]
        )
    elif direction_value == "plus_to_avhd6":
        active_preferred_template_names = PREFERRED_CROSS_TEMPLATE_NAMES["plus_to_avhd6"]
        active_template_heading = "AVHD6 output template"
        active_template_toggle_label = "Use built-in AVHD6 output template"
        active_template_upload_caption = "Upload an AVHD6 KSF output template."
        active_template_upload_label = "AVHD6 output template"
        active_source_caption = "Upload one or more Atlas Max+ KSF files to convert into AVHD6."
        active_source_label = "Atlas Max+ source files"
        active_workflow_info = (
            "Direction selected: Plus -> AVHD6. The app uses the AVHD6_TO_PLUS sheet in reverse, matching Atlas Max+ "
            "source fields by Base Setup first, Media second, Output ICC third, and Input RGB as a support signal. "
            "Once a reliable match is found, the full AVHD6 target package from that row is applied."
        )
        active_default_template_name, active_default_template_bytes = load_preferred_template_bytes(
            PREFERRED_CROSS_TEMPLATE_NAMES["plus_to_avhd6"]
        )

    top_left, top_right = st.columns([1.5, 1])
    with top_left:
        st.markdown(f"<div class='{section_card_class}'>", unsafe_allow_html=True)
        st.subheader("Source files")
        input_mode = st.radio(
            "Input mode",
            options=["Single files", "ZIP", "Mixed"],
            horizontal=True,
            key=f"{session_prefix}_input_mode",
        )
        st.caption(
            "Single files: upload one or more `.ksf` files directly. "
            "ZIP: upload a `.zip` and scan all `.ksf` files inside it recursively. "
            "Mixed: combine direct `.ksf` uploads with `.zip` packages in the same batch."
        )
        source_uploads = None
        zip_uploads = None
        if input_mode in {"Single files", "Mixed"}:
            st.caption(active_source_caption)
            source_uploads = st.file_uploader(
                active_source_label,
                type=["ksf"],
                accept_multiple_files=True,
                label_visibility="collapsed",
                key=f"{session_prefix}_source_ksf_{uploader_nonce}",
            )
        if input_mode in {"ZIP", "Mixed"}:
            st.caption("Upload one or more ZIP files. The app scans recursively for `.ksf` files.")
            zip_uploads = st.file_uploader(
                "ZIP source packages",
                type=["zip"],
                accept_multiple_files=True,
                label_visibility="collapsed",
                key=f"{session_prefix}_source_zip_{uploader_nonce}",
            )
        st.markdown("</div>", unsafe_allow_html=True)
    with top_right:
        st.markdown(f"<div class='{section_card_class}'>", unsafe_allow_html=True)
        st.subheader(active_template_heading)
        use_default_template = st.toggle(
            active_template_toggle_label,
            value=active_default_template_bytes is not None,
            help="If enabled, the app looks for the preferred built-in template for the selected direction inside templates/.",
            key=f"{session_prefix}_use_default_template",
        )

        template_upload = None
        selected_builtin_template_name = active_default_template_name
        selected_builtin_template_bytes = active_default_template_bytes
        if use_default_template:
            builtin_template_options = (
                load_available_template_options(active_preferred_template_names)
                if active_preferred_template_names
                else {}
            )
            if builtin_template_options:
                selected_builtin_template_name = st.selectbox(
                    "Built-in template",
                    options=list(builtin_template_options.keys()),
                    index=0,
                    key=f"{session_prefix}_builtin_template",
                )
                selected_builtin_template_bytes = builtin_template_options[selected_builtin_template_name]
                st.success(f"Built-in template loaded: {selected_builtin_template_name}")
            elif active_default_template_bytes is not None:
                st.success(f"Built-in template loaded: {active_default_template_name}")
            else:
                st.warning(
                    "Built-in template for the selected direction was not found inside templates/. Upload the correct output template manually."
                )
        else:
            st.caption(active_template_upload_caption)
            template_upload = st.file_uploader(
                active_template_upload_label,
                type=["ksf", "kst"],
                accept_multiple_files=False,
                label_visibility="collapsed",
                key=f"{session_prefix}_template_{uploader_nonce}",
            )
        st.markdown("</div>", unsafe_allow_html=True)

    source_parts: list[SourceItem] = []
    source_collection_issues: list[str] = []
    source_error: str | None = None
    try:
        source_parts, source_collection_issues = collect_source_items(source_uploads, zip_uploads)
    except zipfile.BadZipFile:
        source_error = "One of the uploaded ZIP files is invalid or corrupted."
    else:
        source_error = detect_missing_source_error(source_uploads, zip_uploads, source_parts)

    if use_default_template and selected_builtin_template_bytes is not None:
        template_name = selected_builtin_template_name
        template_bytes = selected_builtin_template_bytes
    else:
        template_name = template_upload.name if template_upload else None
        template_bytes = template_upload.getvalue() if template_upload else None

    preview_key = f"{session_prefix}_preview"
    converted_items_key = f"{session_prefix}_converted_items"
    conversion_report_key = f"{session_prefix}_conversion_report"
    zip_bytes_key = f"{session_prefix}_zip_bytes"

    render_kpis(source_parts, template_name, st.session_state.get(preview_key))

    selected_pallet_override: str | None = None
    show_pallet_override = False
    if direction_value is not None:
        _, expected_target_family = get_cross_direction_families(direction_value)
        show_pallet_override = expected_target_family == "poly"

    if show_pallet_override:
        st.markdown(f"<div class='{section_card_class}'>", unsafe_allow_html=True)
        st.subheader("Pallet override")
        selected_pallet = st.selectbox(
            "Pallet name",
            options=POLY_PALLET_OPTIONS,
            index=0,
            help="If selected, this value is written to <TableName> in every converted KSF. Leave as mapping value to use the spreadsheet.",
            key=f"{session_prefix}_pallet_override",
        )
        if selected_pallet != PALLET_OVERRIDE_DEFAULT:
            selected_pallet_override = selected_pallet
            st.caption(f"Output KSF files will use TableName: `{selected_pallet_override}`")
        else:
            st.caption("Output KSF files will use the pallet from the mapping spreadsheet.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(f"<div class='{section_card_class}'>", unsafe_allow_html=True)
    st.subheader("Conversion workflow")
    st.info(active_workflow_info)
    st.caption("Output is always generated as a single ZIP package with the converted KSF files and `conversion-report.json`.")
    st.markdown("</div>", unsafe_allow_html=True)

    action_a, action_b, action_c = st.columns([1, 1.2, 0.8])
    with action_a:
        analyze_clicked = st.button("Analyze files", use_container_width=True, key=f"{session_prefix}_analyze")
    with action_b:
        convert_clicked = st.button("Convert and export ZIP", type="primary", use_container_width=True, key=f"{session_prefix}_convert")
    with action_c:
        clear_clicked = st.button("Clear", use_container_width=True, key=f"{session_prefix}_clear")

    if clear_clicked:
        for key in [preview_key, converted_items_key, conversion_report_key, zip_bytes_key]:
            st.session_state.pop(key, None)
        st.session_state[uploader_nonce_key] = uploader_nonce + 1
        safe_rerun()

    if source_error:
        st.error(source_error)
    for issue in source_collection_issues:
        st.error(issue)

    if analyze_clicked:
        if not source_parts or not template_bytes:
            if not source_parts and source_error:
                st.error(source_error)
            else:
                st.error(analyze_error)
        else:
            resolved_template_name = template_name or "atlas-template.ksf"
            if direction_value is None:
                st.session_state[preview_key] = build_preview_fn(source_parts, resolved_template_name, template_bytes)
            else:
                st.session_state[preview_key] = build_preview_fn(
                    source_parts,
                    resolved_template_name,
                    template_bytes,
                    direction_value,
                )

    preview = st.session_state.get(preview_key)
    if preview:
        render_preview_fn(preview)

    if convert_clicked:
        if not source_parts or not template_bytes:
            if not source_parts and source_error:
                st.error(source_error)
            else:
                st.error(analyze_error)
        else:
            resolved_template_name = template_name or "atlas-template.ksf"
            if direction_value is None:
                preview = build_preview_fn(source_parts, resolved_template_name, template_bytes)
            else:
                preview = build_preview_fn(
                    source_parts,
                    resolved_template_name,
                    template_bytes,
                    direction_value,
                )
            st.session_state[preview_key] = preview
            convert_kwargs = dict(
                source_parts=source_parts,
                template_bytes=template_bytes,
                geometry_mode=geometry_mode,
                copies_mode=copies_mode,
                set_name_mode=set_name_mode,
                x_delta=float(x_delta),
                y_delta=float(y_delta),
            )
            if direction_value is not None:
                convert_kwargs["direction"] = direction_value
                convert_kwargs["pallet_override"] = selected_pallet_override
            converted_items = convert_sources_fn(**convert_kwargs)
            report = build_conversion_report(preview, converted_items)
            st.session_state[converted_items_key] = converted_items
            st.session_state[conversion_report_key] = report
            st.session_state[zip_bytes_key] = generate_zip_bundle(converted_items, report)
            success_count = sum(1 for item in converted_items if item.status == "converted")
            error_count = sum(1 for item in converted_items if item.status == "error")
            if success_count:
                st.success(f"Conversion completed. Success: {success_count} | Failed: {error_count}")
            else:
                st.error("No files were converted successfully.")

    zip_bytes = st.session_state.get(zip_bytes_key)
    if zip_bytes:
        st.download_button(
            "Download atlas-max-converted.zip",
            data=zip_bytes,
            file_name="atlas-max-converted.zip",
            mime="application/zip",
            use_container_width=True,
            key=f"{session_prefix}_download",
        )

    converted_items = st.session_state.get(converted_items_key)
    report = st.session_state.get(conversion_report_key)
    if converted_items and report:
        render_conversion_results(converted_items, report)

    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(
        page_title="Atlas Max KSF Converter",
        page_icon="🧩",
        layout="wide",
    )

    st.markdown(
        """
        <style>
        .stApp {
            color: #2f3447;
            background:
                radial-gradient(circle at 12% 18%, rgba(255, 184, 168, 0.34), transparent 26%),
                radial-gradient(circle at 88% 14%, rgba(153, 215, 209, 0.30), transparent 24%),
                radial-gradient(circle at 78% 78%, rgba(253, 221, 146, 0.26), transparent 24%),
                radial-gradient(circle at 20% 82%, rgba(196, 214, 169, 0.24), transparent 22%),
                linear-gradient(180deg, #fffaf5 0%, #fdf7f0 48%, #f8f3ee 100%);
        }
        .block-container {
            padding-top: 1.6rem;
            padding-bottom: 2.8rem;
            max-width: 1220px;
        }
        .hero-card {
            background:
                linear-gradient(135deg, rgba(255, 255, 255, 0.92) 0%, rgba(255, 247, 240, 0.88) 52%, rgba(239, 248, 245, 0.82) 100%);
            border: 1px solid rgba(112, 126, 154, 0.16);
            border-radius: 24px;
            padding: 1.35rem 1.45rem;
            box-shadow: 0 18px 42px rgba(88, 97, 129, 0.10);
            margin-bottom: 1rem;
            backdrop-filter: blur(10px);
        }
        .hero-title {
            font-size: 2rem;
            font-weight: 700;
            color: #31374a;
            margin-bottom: 0.2rem;
            letter-spacing: -0.03em;
        }
        .hero-subtitle {
            font-size: 1rem;
            color: #5d667f;
            line-height: 1.55;
        }
        .section-card {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.90) 0%, rgba(255, 251, 247, 0.78) 100%);
            border: 1px solid rgba(116, 133, 160, 0.14);
            border-radius: 22px;
            padding: 1rem 1rem 0.9rem 1rem;
            box-shadow: 0 14px 34px rgba(95, 106, 138, 0.08);
            margin-bottom: 1rem;
            backdrop-filter: blur(8px);
        }
        .cross-section-card {
            background:
                linear-gradient(180deg, rgba(244, 251, 253, 0.95) 0%, rgba(234, 245, 249, 0.82) 100%);
            border: 1px solid rgba(64, 123, 142, 0.20);
            box-shadow: 0 16px 34px rgba(49, 86, 108, 0.10);
        }
        .cross-hero {
            background:
                radial-gradient(circle at 12% 18%, rgba(135, 215, 228, 0.18), transparent 24%),
                radial-gradient(circle at 84% 30%, rgba(255, 210, 143, 0.16), transparent 26%),
                linear-gradient(135deg, rgba(18, 60, 78, 0.96) 0%, rgba(24, 86, 97, 0.94) 54%, rgba(40, 112, 118, 0.92) 100%);
            border: 1px solid rgba(89, 169, 186, 0.22);
            border-radius: 26px;
            padding: 1.3rem 1.4rem;
            box-shadow: 0 22px 40px rgba(31, 67, 82, 0.18);
            margin-bottom: 1rem;
            position: relative;
            overflow: hidden;
        }
        .cross-hero-kicker {
            display: inline-block;
            padding: 0.26rem 0.6rem;
            border-radius: 999px;
            background: rgba(216, 244, 248, 0.14);
            border: 1px solid rgba(216, 244, 248, 0.18);
            color: #d9f4f8;
            font-size: 0.78rem;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            margin-bottom: 0.65rem;
        }
        .cross-hero-title {
            color: #f4fbfc;
            font-size: 1.9rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            margin-bottom: 0.35rem;
        }
        .cross-hero-copy {
            color: rgba(233, 246, 248, 0.88);
            max-width: 760px;
            line-height: 1.58;
            margin-bottom: 0.9rem;
        }
        .cross-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
        }
        .cross-chip {
            display: inline-flex;
            align-items: center;
            padding: 0.34rem 0.7rem;
            border-radius: 999px;
            background: rgba(246, 252, 253, 0.12);
            border: 1px solid rgba(246, 252, 253, 0.16);
            color: #f1fbfd;
            font-size: 0.82rem;
            font-weight: 600;
            letter-spacing: 0.01em;
        }
        .cross-workspace div[data-testid="stMetric"] {
            background:
                linear-gradient(160deg, rgba(227, 244, 247, 0.96) 0%, rgba(212, 236, 241, 0.92) 100%);
            border: 1px solid rgba(80, 135, 152, 0.18);
            box-shadow: 0 14px 28px rgba(50, 93, 109, 0.10);
        }
        .cross-workspace div[data-testid="stAlert"] {
            border-color: rgba(76, 134, 152, 0.20);
            box-shadow: 0 14px 26px rgba(46, 87, 102, 0.08);
        }
        .cross-workspace div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #1f7582 0%, #175966 100%);
            color: #eef9fb;
            border-color: rgba(28, 95, 107, 0.32);
            box-shadow: 0 14px 26px rgba(28, 84, 95, 0.18);
        }
        .cross-workspace div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(180deg, #f4c66f 0%, #dfa24e 100%);
            color: #553b0f;
            border-color: rgba(148, 104, 39, 0.26);
        }
        .cross-workspace div[data-testid="stDownloadButton"] > button {
            background: linear-gradient(180deg, #c5ece4 0%, #9fd7cb 100%);
            color: #194c48;
            border-color: rgba(60, 132, 122, 0.20);
            box-shadow: 0 14px 26px rgba(54, 113, 106, 0.14);
        }
        .cross-workspace div[data-testid="stButton"] > button:hover,
        .cross-workspace div[data-testid="stDownloadButton"] > button:hover {
            filter: saturate(1.06) brightness(1.01);
            box-shadow: 0 18px 30px rgba(31, 78, 89, 0.18);
        }
        .cross-workspace div[data-testid="stFileUploader"] {
            background:
                linear-gradient(180deg, rgba(243, 251, 252, 0.92) 0%, rgba(232, 246, 248, 0.82) 100%);
            border-color: rgba(70, 126, 145, 0.28);
        }
        .cross-workspace div[data-testid="stExpander"] {
            border: 1px solid rgba(83, 138, 156, 0.18);
            box-shadow: 0 14px 28px rgba(52, 92, 109, 0.08);
            background: linear-gradient(180deg, rgba(248, 252, 253, 0.90) 0%, rgba(239, 247, 249, 0.88) 100%);
        }
        .cross-workspace div[data-testid="stMarkdownContainer"] code {
            background: rgba(26, 87, 97, 0.08);
            color: #144852;
            border-radius: 8px;
            padding: 0.08rem 0.34rem;
        }
        .cross-workspace .stSubheader {
            color: #1d4f5e;
        }
        .theme-cross-card {
            background:
                linear-gradient(180deg, rgba(238, 250, 252, 0.96) 0%, rgba(226, 243, 247, 0.84) 100%);
            border: 1px solid rgba(66, 131, 151, 0.22);
            box-shadow: 0 18px 34px rgba(44, 92, 111, 0.10);
        }
        .theme-cross-hero {
            background:
                radial-gradient(circle at 12% 18%, rgba(123, 216, 224, 0.18), transparent 24%),
                radial-gradient(circle at 84% 30%, rgba(255, 205, 126, 0.18), transparent 26%),
                linear-gradient(135deg, rgba(11, 67, 86, 0.98) 0%, rgba(16, 104, 115, 0.95) 54%, rgba(55, 148, 150, 0.92) 100%);
            border-color: rgba(87, 184, 196, 0.24);
            box-shadow: 0 24px 42px rgba(20, 76, 92, 0.22);
        }
        .theme-cross-workspace div[data-testid="stMetric"] {
            background:
                linear-gradient(160deg, rgba(219, 244, 247, 0.98) 0%, rgba(193, 232, 238, 0.94) 100%);
            border: 1px solid rgba(69, 139, 156, 0.20);
            box-shadow: 0 14px 28px rgba(37, 91, 107, 0.12);
        }
        .theme-cross-workspace div[data-testid="stAlert"] {
            border-color: rgba(68, 140, 154, 0.24);
            box-shadow: 0 14px 26px rgba(46, 92, 104, 0.10);
        }
        .theme-cross-workspace div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #1a7f8c 0%, #145e6a 100%);
            color: #eefbfd;
            border-color: rgba(23, 100, 112, 0.34);
            box-shadow: 0 14px 26px rgba(18, 88, 99, 0.20);
        }
        .theme-cross-workspace div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(180deg, #ffd07b 0%, #e5a94d 100%);
            color: #5a3f10;
            border-color: rgba(153, 109, 42, 0.28);
        }
        .theme-cross-workspace div[data-testid="stDownloadButton"] > button {
            background: linear-gradient(180deg, #bdece1 0%, #94d4c8 100%);
            color: #174c49;
            border-color: rgba(54, 131, 121, 0.24);
            box-shadow: 0 14px 26px rgba(45, 111, 104, 0.16);
        }
        .theme-cross-workspace div[data-testid="stFileUploader"] {
            background:
                linear-gradient(180deg, rgba(239, 251, 252, 0.94) 0%, rgba(224, 244, 247, 0.84) 100%);
            border-color: rgba(74, 136, 151, 0.30);
        }
        .theme-cross-workspace div[data-testid="stExpander"] {
            border: 1px solid rgba(79, 143, 159, 0.20);
            box-shadow: 0 14px 28px rgba(44, 92, 109, 0.08);
            background: linear-gradient(180deg, rgba(245, 252, 253, 0.92) 0%, rgba(233, 246, 249, 0.90) 100%);
        }
        .theme-cross-workspace div[data-testid="stMarkdownContainer"] code {
            background: rgba(24, 98, 110, 0.10);
            color: #135360;
        }
        .theme-cross-workspace .stSubheader {
            color: #145564;
        }
        .theme-avhd6-card {
            background:
                linear-gradient(180deg, rgba(255, 248, 228, 0.96) 0%, rgba(255, 241, 208, 0.86) 100%);
            border: 1px solid rgba(187, 145, 47, 0.24);
            box-shadow: 0 18px 34px rgba(145, 113, 37, 0.10);
        }
        .theme-avhd6-hero {
            background:
                radial-gradient(circle at 10% 16%, rgba(255, 221, 128, 0.18), transparent 24%),
                radial-gradient(circle at 86% 24%, rgba(255, 246, 206, 0.12), transparent 28%),
                linear-gradient(135deg, rgba(122, 75, 14, 0.98) 0%, rgba(174, 118, 23, 0.95) 48%, rgba(224, 170, 52, 0.92) 100%);
            border-color: rgba(214, 167, 62, 0.28);
            box-shadow: 0 24px 42px rgba(123, 83, 18, 0.24);
        }
        .theme-avhd6-hero .cross-hero-kicker {
            background: rgba(255, 247, 222, 0.14);
            border-color: rgba(255, 244, 208, 0.20);
            color: #fff5dc;
        }
        .theme-avhd6-hero .cross-hero-title {
            color: #fffaf0;
        }
        .theme-avhd6-hero .cross-hero-copy {
            color: rgba(255, 247, 226, 0.88);
        }
        .theme-avhd6-hero .cross-chip {
            background: rgba(255, 249, 233, 0.14);
            border-color: rgba(255, 245, 217, 0.18);
            color: #fff8e8;
        }
        .theme-avhd6-workspace div[data-testid="stMetric"] {
            background:
                linear-gradient(160deg, rgba(255, 243, 204, 0.98) 0%, rgba(255, 232, 173, 0.94) 100%);
            border: 1px solid rgba(188, 145, 39, 0.22);
            box-shadow: 0 14px 28px rgba(155, 117, 28, 0.12);
        }
        .theme-avhd6-workspace div[data-testid="stAlert"] {
            border-color: rgba(191, 147, 42, 0.24);
            box-shadow: 0 14px 26px rgba(150, 114, 31, 0.10);
        }
        .theme-avhd6-workspace div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #c88c20 0%, #8f6112 100%);
            color: #fff8eb;
            border-color: rgba(144, 100, 18, 0.34);
            box-shadow: 0 14px 26px rgba(144, 99, 17, 0.20);
        }
        .theme-avhd6-workspace div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(180deg, #fff2b9 0%, #f2cf67 100%);
            color: #654708;
            border-color: rgba(173, 132, 32, 0.28);
        }
        .theme-avhd6-workspace div[data-testid="stDownloadButton"] > button {
            background: linear-gradient(180deg, #ffe1a6 0%, #f0ba56 100%);
            color: #6d4b09;
            border-color: rgba(184, 135, 29, 0.24);
            box-shadow: 0 14px 26px rgba(175, 128, 28, 0.16);
        }
        .theme-avhd6-workspace div[data-testid="stFileUploader"] {
            background:
                linear-gradient(180deg, rgba(255, 250, 236, 0.94) 0%, rgba(255, 241, 209, 0.86) 100%);
            border-color: rgba(197, 154, 53, 0.30);
        }
        .theme-avhd6-workspace div[data-testid="stExpander"] {
            border: 1px solid rgba(188, 145, 48, 0.20);
            box-shadow: 0 14px 28px rgba(153, 116, 35, 0.08);
            background: linear-gradient(180deg, rgba(255, 252, 241, 0.92) 0%, rgba(255, 245, 220, 0.90) 100%);
        }
        .theme-avhd6-workspace div[data-testid="stMarkdownContainer"] code {
            background: rgba(150, 104, 15, 0.10);
            color: #7a5308;
        }
        .theme-avhd6-workspace .stSubheader {
            color: #7b5207;
        }
        div[data-testid="stMetric"] {
            background:
                linear-gradient(160deg, rgba(255, 241, 234, 0.92) 0%, rgba(239, 248, 245, 0.92) 100%);
            border: 1px solid rgba(118, 134, 161, 0.14);
            padding: 1rem;
            border-radius: 18px;
            box-shadow: 0 12px 28px rgba(90, 101, 132, 0.08);
        }
        div[data-testid="stFileUploader"] {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.82) 0%, rgba(250, 246, 242, 0.72) 100%);
            border-radius: 18px;
            padding: 0.45rem;
            border: 1px dashed rgba(109, 126, 154, 0.28);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
        }
        div[data-testid="stFileUploader"] section {
            background: transparent;
        }
        div[data-baseweb="radio"] > div {
            gap: 0.7rem;
        }
        div[data-baseweb="radio"] label {
            background: rgba(255, 255, 255, 0.52);
            border: 1px solid rgba(118, 134, 161, 0.16);
            border-radius: 999px;
            padding: 0.28rem 0.8rem 0.28rem 0.22rem;
            box-shadow: 0 8px 18px rgba(94, 106, 136, 0.05);
        }
        div[data-baseweb="radio"] label:hover {
            background: rgba(255, 249, 244, 0.8);
        }
        div[data-testid="stButton"] > button, div[data-testid="stDownloadButton"] > button {
            border-radius: 14px;
            border: 1px solid rgba(103, 121, 149, 0.18);
            padding-top: 0.7rem;
            padding-bottom: 0.7rem;
            font-weight: 600;
            box-shadow: 0 12px 24px rgba(93, 104, 134, 0.10);
            transition: transform 120ms ease, box-shadow 120ms ease, filter 120ms ease;
        }
        div[data-testid="stButton"] > button {
            background: linear-gradient(180deg, #ffd9cb 0%, #f8c8b8 100%);
            color: #5b3d44;
        }
        div[data-testid="stDownloadButton"] > button,
        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(180deg, #bfe8df 0%, #9fd9cf 100%);
            color: #214b4c;
        }
        div[data-testid="stDownloadButton"] > button {
            background: linear-gradient(180deg, #ffe6a8 0%, #f3d37a 100%);
            color: #584719;
            border-color: rgba(158, 128, 52, 0.22);
        }
        div[data-testid="stButton"] > button:hover,
        div[data-testid="stDownloadButton"] > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 16px 28px rgba(93, 104, 134, 0.14);
            filter: saturate(1.03);
        }
        h1, h2, h3, .stSubheader {
            color: #31374a;
            letter-spacing: -0.02em;
        }
        p, label, .stCaption, .stMarkdown, .stText {
            color: #59637b;
        }
        div[data-testid="stAlert"] {
            border-radius: 18px;
            border-width: 1px;
            box-shadow: 0 12px 24px rgba(95, 106, 138, 0.05);
        }
        div[data-testid="stExpander"] {
            border-radius: 20px;
            overflow: hidden;
        }
        div[data-baseweb="tab-list"] {
            gap: 0.5rem;
            display: flex;
            align-items: stretch;
        }
        div[data-baseweb="tab-list"] button {
            flex: 1 1 0;
            min-width: 17rem;
            min-height: 4.1rem;
            border-radius: 999px !important;
            justify-content: center;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            color: #4c566f !important;
            font-weight: 700 !important;
            font-size: 1.02rem !important;
            letter-spacing: -0.015em;
            background: rgba(255, 255, 255, 0.42) !important;
            border: 1px solid rgba(116, 133, 160, 0.14) !important;
            transition: transform 140ms ease, background 140ms ease, border-color 140ms ease, box-shadow 140ms ease, color 140ms ease;
        }
        div[data-baseweb="tab-list"] button:first-child {
            background: linear-gradient(180deg, rgba(255, 222, 210, 0.98) 0%, rgba(255, 238, 229, 0.86) 100%) !important;
            border-color: rgba(220, 116, 88, 0.34) !important;
            color: #764038 !important;
        }
        div[data-baseweb="tab-list"] button:nth-child(2) {
            background: linear-gradient(180deg, rgba(208, 240, 234, 0.98) 0%, rgba(231, 248, 244, 0.86) 100%) !important;
            border-color: rgba(54, 145, 132, 0.34) !important;
            color: #1f5d59 !important;
        }
        div[data-baseweb="tab-list"] button:nth-child(3) {
            background: linear-gradient(180deg, rgba(255, 235, 184, 0.98) 0%, rgba(255, 246, 214, 0.88) 100%) !important;
            border-color: rgba(196, 145, 41, 0.34) !important;
            color: #6e5312 !important;
        }
        div[data-baseweb="tab-list"] button[aria-selected="true"] {
            box-shadow: 0 10px 20px rgba(93, 104, 134, 0.10);
        }
        div[data-baseweb="tab-list"] button:hover {
            transform: translateY(-1px);
        }
        div[data-baseweb="tab-list"] button:first-child:hover {
            background: linear-gradient(180deg, rgba(255, 210, 196, 1) 0%, rgba(255, 231, 220, 0.92) 100%) !important;
            border-color: rgba(212, 104, 75, 0.40) !important;
            box-shadow: 0 10px 22px rgba(214, 112, 86, 0.16) !important;
        }
        div[data-baseweb="tab-list"] button:nth-child(2):hover {
            background: linear-gradient(180deg, rgba(194, 234, 225, 1) 0%, rgba(223, 245, 238, 0.92) 100%) !important;
            border-color: rgba(41, 132, 119, 0.40) !important;
            box-shadow: 0 10px 22px rgba(55, 136, 124, 0.16) !important;
        }
        div[data-baseweb="tab-list"] button:nth-child(3):hover {
            background: linear-gradient(180deg, rgba(255, 226, 156, 1) 0%, rgba(255, 241, 196, 0.92) 100%) !important;
            border-color: rgba(184, 132, 24, 0.40) !important;
            box-shadow: 0 10px 22px rgba(191, 145, 43, 0.16) !important;
        }
        div[data-baseweb="tab-list"] button:first-child[aria-selected="true"] {
            background: linear-gradient(180deg, #ffbea8 0%, #f29d80 100%) !important;
            border-color: rgba(200, 93, 63, 0.48) !important;
            color: #5f2f28 !important;
            box-shadow: 0 12px 24px rgba(212, 108, 78, 0.22) !important;
        }
        div[data-baseweb="tab-list"] button:nth-child(2)[aria-selected="true"] {
            background: linear-gradient(180deg, #9fded2 0%, #69bfaf 100%) !important;
            border-color: rgba(31, 120, 107, 0.46) !important;
            color: #124843 !important;
            box-shadow: 0 12px 24px rgba(47, 129, 117, 0.20) !important;
        }
        div[data-baseweb="tab-list"] button:nth-child(3)[aria-selected="true"] {
            background: linear-gradient(180deg, #ffd36f 0%, #e7ab2f 100%) !important;
            border-color: rgba(169, 117, 10, 0.46) !important;
            color: #5a4008 !important;
            box-shadow: 0 12px 24px rgba(187, 132, 24, 0.20) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-title">Atlas Max KSF Converter</div>
            <div class="hero-subtitle">
                Professional KSF conversion tool with separate workflows for Vulcan to Atlas Max+,
                Atlas Max family to Poly, and AVHD6 to Atlas Max+.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    vulcan_tab, cross_tab, avhd6_tab = st.tabs(
        ["Vulcan -> Atlas Max+", "Atlas Max+ <-> Poly", "AVHD6 <-> Atlas Max+"]
    )

    with vulcan_tab:
        render_conversion_workspace(
            session_prefix="legacy",
            template_heading="Atlas template",
            template_toggle_label="Use built-in Atlas Max template",
            template_upload_caption="Upload a custom Atlas Max KSF template.",
            template_upload_label="Atlas Max template",
            source_caption="Upload one or more Vulcan KSF files to convert.",
            source_label="Vulcan source files",
            workflow_info="The converted file uses the Atlas Max template only as the structural mirror. Mapping priority now follows this order: Vulcan output ICC first, setup second, Vulcan media as support, and input profile as a light support signal. The workbook is not treated as a strict horizontal row where every source field must match exactly. Atlas setup, Atlas media and Atlas output ICC come from the selected workbook row whenever a reliable match is found.",
            analyze_error="Please provide at least one source file and a valid Atlas Max template.",
            build_preview_fn=build_preview,
            convert_sources_fn=convert_sources,
            render_preview_fn=render_preview_legacy,
            theme="legacy",
            theme_variant="legacy",
        )

    with cross_tab:
        render_conversion_workspace(
            session_prefix="cross",
            template_heading="Output template",
            template_toggle_label="Use built-in output template",
            template_upload_caption="Upload a custom target KSF template.",
            template_upload_label="Target KSF template",
            source_caption="Upload one or more Atlas Max+, Atlas Max, or Poly KSF files to convert.",
            source_label="Atlas Max+ / Atlas Max / Poly source files",
            workflow_info="This workflow is dedicated to Atlas Max+ to Poly, Atlas Max to Poly, and Poly to Atlas Max+. It uses the dedicated workbook and searches the input KSF in this order: Base Setup first, Media second, Output ICC third, and Input RGB as a support signal. Once one reliable match identifies the row, the app applies the full mapped target values from that spreadsheet row without touching the approved Vulcan workflow.",
            analyze_error="Please provide at least one source file and a valid target template.",
            build_preview_fn=build_preview_cross,
            convert_sources_fn=convert_sources_cross,
            render_preview_fn=render_preview_cross,
            theme="cross",
            theme_variant="cross",
            direction_options=[
                ("Convert Plus -> Poly", "plus_to_poly"),
                ("Convert Max -> Poly", "max_to_poly"),
                ("Convert Poly -> Plus", "poly_to_plus"),
            ],
            hero_title="Atlas Max+ <-> Poly Mapping Station",
            hero_copy="Spreadsheet-driven conversion for Atlas Max+, Atlas Max, and Poly mappings. This workspace is isolated from the approved Vulcan flow and is meant for directional mapping validation and controlled rollout.",
            hero_chips=["Plus to Poly", "Max to Poly", "Poly to Plus", "Template-Safe Output"],
        )

    with avhd6_tab:
        render_conversion_workspace(
            session_prefix="avhd6",
            template_heading="Output template",
            template_toggle_label="Use built-in output template",
            template_upload_caption="Upload a custom target KSF template.",
            template_upload_label="Target KSF template",
            source_caption="Upload one or more AVHD6 or Atlas Max+ KSF files to convert.",
            source_label="AVHD6 / Atlas Max+ source files",
            workflow_info="This workflow is dedicated to AVHD6 to Atlas Max+ and Atlas Max+ to AVHD6. It uses the dedicated workbook and searches the input KSF in this order: Base Setup first, Media second, Output ICC third, and Input RGB as a support signal. Once one reliable match identifies the row, the app applies the full mapped target values from that spreadsheet row.",
            analyze_error="Please provide at least one source file and a valid target template.",
            build_preview_fn=build_preview_cross,
            convert_sources_fn=convert_sources_cross,
            render_preview_fn=render_preview_cross,
            theme="cross",
            theme_variant="avhd6",
            direction_options=[
                ("Convert AVHD6 -> Plus", "avhd6_to_plus"),
                ("Convert Plus -> AVHD6", "plus_to_avhd6"),
            ],
            hero_kicker="Dedicated AVHD6 Workspace",
            hero_title="AVHD6 <-> Atlas Max+ Mapping Station",
            hero_copy="Spreadsheet-driven conversion for AVHD6 and Atlas Max+ mappings. This workspace mirrors the cross-conversion flow and keeps directional mapping isolated for validation and controlled rollout.",
            hero_chips=["AVHD6 to Plus", "Plus to AVHD6", "Setup-First Match", "Template-Safe Output"],
        )


if __name__ == "__main__":
    main()
