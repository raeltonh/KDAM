#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


TEMPLATE_OWNED_TAGS = {
    "ShouldIgnoreAdaptiveFrequency",
    "Factory",
    "TableName",
    "MediaName",
    "MediaPrintHeight",
    "MediaThickness",
    "ActionItem",
    "ColorPass",
    "ColorSaturation",
    "ColorHighlight",
    "WhitePass",
    "WithWhiteInterlace",
    "White4DInterlace",
    "Color4DInterlace",
    "UseImageWhiteLayer",
    "WBCMaxOpacity",
    "WBCLUTMaxWhite",
    "WBCMinOpacity",
    "WBCPivot",
    "WBCWhiteness",
    "MaxOpacity",
    "MinOpacity",
    "HighlightOpacity",
    "ChokeWhitePixels",
    "GradedEdgesWhitePixels",
    "OutXRes",
    "OutYRes",
    "OutXResHighlight",
    "OutYResHighlight",
    "WhiteChokeOnlyUnderColor",
    "PrintSpeed",
    "PrintSpeed2",
    "PrintDirection",
    "SprayAmount",
    "LinearSprayAmount",
    "TagSprayAddition",
    "IsSpray",
    "IsWipe",
    "UseFofColor",
    "FofColorOpacity",
    "StrokeFofColorPixels",
    "UseFofWhite",
    "FofWhiteOpacity",
    "StrokeFofWhitePixels",
    "FofWhiteunderCmykOpacity",
    "UseMediaThicknessSmartDryer",
    "PrintWhiteAreas",
    "Sharpen",
    "IccInRGBFileName",
    "IccInCMYKFileName",
    "IccOutFileName",
    "RenderingIntent",
    "LastBaseSetupName",
    "IsRoller",
    "IsAK",
    "DelaySprayToPrint",
    "LayerDelay1to2",
    "LayerDelay2To3",
    "UseDischarge",
    "MaxDischarge",
    "DischargeOpacity",
    "ChokeDischargePixels",
    "MinDischarge",
    "ColorKnockout",
    "WhiteKnockout",
    "RotateSmallDegree",
    "SpotColors",
    "OutXResPolyEnhancerAboveWhite",
    "OutYResPolyEnhancerAboveWhite",
    "OutXResPolyEnhancerAboveColor",
    "OutYResPolyEnhancerAboveColor",
    "GarmentType",
    "SpecialSeparations",
    "SprayAndWipeItemsList",
    "ChecksumList",
    "IsDTFilm",
    "RipSource",
    "IsProofing",
    "EstimatedInkConsump",
    "MachineType",
    "SetAuthor",
    "SetApplied",
}

GEOMETRY_TAGS = {
    "XOffsetMM",
    "YOffsetMM",
    "WidthMM",
    "HeightMM",
    "Rotate90",
    "Rotate180",
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

COPY_TAGS = {"TotalCopies"}
ROOT_ATTRS = {
    "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
    "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

ALLOWED_SPECIAL_SEPARATIONS = {"Qc", "Ic", "Iw"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Converte KSFs antigos para formato Atlas Max baseado em um KSF template."
    )
    parser.add_argument("source", help="Arquivo .ksf ou diretório com .ksf de origem")
    parser.add_argument("template", help="Arquivo .ksf Atlas Max Plus usado como template")
    parser.add_argument("output", help="Arquivo de saída ou diretório de saída")
    parser.add_argument(
        "--x-offset-delta",
        type=float,
        default=0.0,
        help="Ajuste adicional em mm aplicado ao XOffsetMM do arquivo convertido",
    )
    parser.add_argument(
        "--y-offset-delta",
        type=float,
        default=0.0,
        help="Ajuste adicional em mm aplicado ao YOffsetMM do arquivo convertido",
    )
    parser.add_argument(
        "--geometry-mode",
        choices=["source", "template"],
        default="source",
        help="Usa geometria do arquivo de origem ou do template",
    )
    parser.add_argument(
        "--copies-mode",
        choices=["source", "template"],
        default="source",
        help="Usa quantidade de cópias do arquivo de origem ou do template",
    )
    parser.add_argument(
        "--set-name-mode",
        choices=["template", "source-file"],
        default="template",
        help="Define SetApplied com o nome do template ou com o nome do arquivo convertido",
    )
    parser.add_argument(
        "--suffix",
        default="",
        help="Sufixo adicionado ao nome do arquivo quando a saída é diretório. Vazio preserva o mesmo nome da origem.",
    )
    return parser.parse_args()


def collect_sources(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.ksf") if p.is_file())


def load_xml(path: Path) -> ET.ElementTree:
    try:
        return ET.parse(path)
    except ET.ParseError as exc:
        raise SystemExit(f"Erro ao ler XML de {path}: {exc}") from exc


def replace_or_append(root: ET.Element, element: ET.Element) -> None:
    existing = root.find(element.tag)
    element_copy = copy.deepcopy(element)
    if existing is None:
        root.append(element_copy)
    else:
        index = list(root).index(existing)
        root.remove(existing)
        root.insert(index, element_copy)


def replace_simple_text(root: ET.Element, tag: str, value: str) -> None:
    node = root.find(tag)
    if node is None:
        node = ET.SubElement(root, tag)
    node.text = value


def build_filtered_special_separations(source_root: ET.Element) -> ET.Element:
    source_special_separations = source_root.find("SpecialSeparations")
    target_special_separations = ET.Element("SpecialSeparations")

    if source_special_separations is None:
        return target_special_separations

    for model in list(source_special_separations):
        name_node = model.find("Name")
        name = name_node.text.strip() if name_node is not None and name_node.text else ""
        if name in ALLOWED_SPECIAL_SEPARATIONS:
            target_special_separations.append(copy.deepcopy(model))

    return target_special_separations


def replace_special_separations_from_source(source_root: ET.Element, target_root: ET.Element) -> None:
    replace_or_append(target_root, build_filtered_special_separations(source_root))


def preserve_geometry(source_root: ET.Element, target_root: ET.Element) -> None:
    for tag in GEOMETRY_TAGS:
        source_node = source_root.find(tag)
        if source_node is not None:
            replace_or_append(target_root, source_node)


def preserve_copies(source_root: ET.Element, target_root: ET.Element) -> None:
    for tag in COPY_TAGS:
        source_node = source_root.find(tag)
        if source_node is not None:
            replace_or_append(target_root, source_node)


def format_number(value: float, original_text: str | None) -> str:
    if original_text and "." in original_text:
        decimals = len(original_text.split(".")[-1])
        return f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def apply_offset_delta(root: ET.Element, x_delta: float, y_delta: float) -> None:
    if x_delta:
        apply_delta_to_tag(root, "XOffsetMM", x_delta)
        for strip in root.findall("./Strips/StripParam"):
            apply_delta_to_tag(strip, "XOffsetMM", x_delta)
    if y_delta:
        apply_delta_to_tag(root, "YOffsetMM", y_delta)
        for strip in root.findall("./Strips/StripParam"):
            apply_delta_to_tag(strip, "YOffsetMM", y_delta)


def apply_delta_to_tag(parent: ET.Element, tag: str, delta: float) -> None:
    node = parent.find(tag)
    if node is None or node.text is None:
        return
    original = node.text.strip()
    value = float(original)
    node.text = format_number(value + delta, original)


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
    source_root = source_tree.getroot()
    target_root = copy.deepcopy(template_tree.getroot())
    for key, value in ROOT_ATTRS.items():
        target_root.set(key, value)

    source_owned_tags = set()
    if geometry_mode == "template":
        source_owned_tags.update(GEOMETRY_TAGS)
    if copies_mode == "template":
        source_owned_tags.update(COPY_TAGS)

    for child in source_root:
        if child.tag in TEMPLATE_OWNED_TAGS or child.tag in source_owned_tags:
            continue
        replace_or_append(target_root, child)

    if geometry_mode == "source":
        preserve_geometry(source_root, target_root)

    if copies_mode == "source":
        preserve_copies(source_root, target_root)

    if set_name_mode == "source-file":
        replace_simple_text(target_root, "SetApplied", output_path.stem)
    replace_special_separations_from_source(source_root, target_root)

    apply_offset_delta(target_root, x_delta, y_delta)
    ET.indent(target_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(target_root).write(output_path, encoding="utf-8", xml_declaration=True)


def resolve_output_path(source: Path, source_root: Path, output_base: Path, suffix: str) -> Path:
    if output_base.suffix.lower() == ".ksf":
        return output_base
    relative = source.relative_to(source_root) if source_root.is_dir() else Path(source.name)
    filename = f"{relative.stem}{suffix}.ksf" if suffix else relative.name
    return output_base / relative.with_name(filename)


def main() -> int:
    args = parse_args()
    source_path = Path(args.source).expanduser()
    template_path = Path(args.template).expanduser()
    output_path = Path(args.output).expanduser()

    if not source_path.exists():
        raise SystemExit(f"Origem nao encontrada: {source_path}")
    if not template_path.is_file():
        raise SystemExit(f"Template invalido: {template_path}")

    sources = collect_sources(source_path)
    if not sources:
        raise SystemExit("Nenhum arquivo .ksf encontrado na origem")

    template_tree = load_xml(template_path)

    for source in sources:
        destination = resolve_output_path(source, source_path, output_path, args.suffix)
        convert_one(
            source_path=source,
            template_tree=template_tree,
            output_path=destination,
            geometry_mode=args.geometry_mode,
            copies_mode=args.copies_mode,
            set_name_mode=args.set_name_mode,
            x_delta=args.x_offset_delta,
            y_delta=args.y_offset_delta,
        )
        print(f"Convertido: {source} -> {destination}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
