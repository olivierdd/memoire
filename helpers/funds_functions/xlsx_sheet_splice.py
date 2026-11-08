"""Losslessly add a worksheet to an existing .xlsx (zip) without re-saving via openpyxl."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_WB_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_WORKSHEET = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
)
SHEET_CT = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)


def col_letter(col_idx: int) -> str:
    """1-based column index to Excel letter."""
    letters = ""
    n = col_idx
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _section_count(styles_text: str, tag: str) -> int:
    match = re.search(rf"<{tag}\b[^>]*\bcount=\"(\d+)\"", styles_text)
    if not match:
        raise ValueError(f"Could not find <{tag} count=...> in styles.xml")
    return int(match.group(1))


def _ensure_dxfs_section(styles_text: str) -> str:
    if re.search(r"<dxfs\b", styles_text):
        return styles_text
    block = "<dxfs count=\"0\"/>"
    for anchor in ("<tableStyles", "</styleSheet>"):
        idx = styles_text.find(anchor)
        if idx != -1:
            return styles_text[:idx] + block + styles_text[idx:]
    return styles_text + block


def _insert_styles_fragment(styles_text: str, tag: str, fragment: str, added: int) -> str:
    close = f"</{tag}>"
    idx = styles_text.rfind(close)
    if idx == -1:
        raise ValueError(f"Missing {close} in styles.xml")
    updated = styles_text[:idx] + fragment + styles_text[idx:]
    return re.sub(
        rf"(<{tag}\b[^>]*\bcount=\")(\d+)(\")",
        lambda m: f"{m.group(1)}{int(m.group(2)) + added}{m.group(3)}",
        updated,
        count=1,
    )


BANNER_FILL_RGB = {
    "Fund (Lipper)": "FFD9E2F3",
    "EDGAR identification": "FFB4C6E7",
    "EDGAR N-CEN": "FF9BC2E6",
    "EDGAR prospectus": "FFDDEBF7",
    "Check: fund_wrapper": "FFFFE699",
    "Check: fund_type": "FFC6E0B4",
    "Check: benchmark": "FFD9D2E9",
}


@dataclass
class SheetStyleSet:
    xf_header: int
    xf_body: int
    xf_body_wrap: int
    xf_gap: int
    xf_number: int
    xf_bool: int
    xf_banner: dict[str, int] = field(default_factory=dict)
    dxf_band: int = 0
    dxf_match: int = 0
    dxf_mismatch: int = 0


def _font_xml(*, bold: bool = False, rgb: str = "FF000000", size: int = 10) -> str:
    bold_tag = "<b/>" if bold else ""
    return (
        f"<font>{bold_tag}<sz val=\"{size}\"/><color rgb=\"{rgb}\"/>"
        f"<name val=\"Calibri\"/><family val=\"2\"/></font>"
    )


def _fill_xml(rgb: str) -> str:
    return (
        f"<fill><patternFill patternType=\"solid\"><fgColor rgb=\"{rgb}\"/>"
        f"<bgColor indexed=\"64\"/></patternFill></fill>"
    )


def _border_xml() -> str:
    sides = "".join(
        f"<{side} style=\"thin\"><color auto=\"1\"/></{side}>"
        for side in ("left", "right", "top", "bottom")
    )
    return f"<border>{sides}<diagonal/></border>"


def _xf_xml(
    font_id: int,
    fill_id: int,
    border_id: int,
    *,
    num_fmt_id: int = 0,
    wrap: bool = False,
    center: bool = False,
    num_fmt_apply: bool = False,
) -> str:
    attrs = [
        f"numFmtId=\"{num_fmt_id}\"",
        f"fontId=\"{font_id}\"",
        f"fillId=\"{fill_id}\"",
        f"borderId=\"{border_id}\"",
        'xfId="0"',
        'applyFont="1"',
        'applyFill="1"',
        'applyBorder="1"',
    ]
    if num_fmt_apply:
        attrs.append('applyNumberFormat="1"')
    if wrap or center:
        attrs.append('applyAlignment="1"')
    align = ""
    if wrap or center:
        parts = []
        if wrap:
            parts.append('wrapText="1"')
        if center:
            parts.extend(['horizontal="center"', 'vertical="center"'])
        align = f"<alignment {' '.join(parts)}/>"
    return f"<xf {' '.join(attrs)}>{align}</xf>"


def _dxf_band_xml() -> str:
    return (
        "<dxf><fill><patternFill patternType=\"solid\"><fgColor indexed=\"64\"/>"
        "<bgColor rgb=\"FFEEF3FA\"/></patternFill></fill></dxf>"
    )


def _dxf_result_xml(*, match: bool) -> str:
    font_rgb = "FF008000" if match else "FF9C0006"
    fill_rgb = "FFE2EFDA" if match else "FFFFC7CE"
    return (
        f"<dxf><font><b/><color rgb=\"{font_rgb}\"/></font><fill>"
        f"<patternFill patternType=\"solid\"><fgColor indexed=\"64\"/>"
        f"<bgColor rgb=\"{fill_rgb}\"/></patternFill></fill></dxf>"
    )


def _inner_xml(styles_text: str, tag: str) -> str:
    match = re.search(rf"<{tag}\b[^>]*>(.*)</{tag}>", styles_text, re.DOTALL)
    return match.group(1) if match else ""


def _tag_items(inner: str, item_tag: str) -> list[str]:
    return re.findall(rf"<{item_tag}\b[^>]*>.*?</{item_tag}>", inner, re.DOTALL)


def _remap_xf_ids(xf_xml: str, *, font_base: int, fill_base: int, border_base: int) -> str:
    def bump(attr: str, base: int, text: str) -> str:
        return re.sub(
            rf'(\b{attr}=")(\d+)(")',
            lambda m: f"{m.group(1)}{int(m.group(2)) + base}{m.group(3)}",
            text,
            count=1,
        )

    out = bump("fontId", font_base, xf_xml)
    out = bump("fillId", fill_base, out)
    return bump("borderId", border_base, out)


def merge_openpyxl_styles(orig_styles: bytes, temp_styles: bytes) -> tuple[bytes, int, int]:
    """Append openpyxl-generated style parts onto the original stylesheet; return xf/dxf offsets."""
    orig_text = orig_styles.decode("utf-8")
    temp_text = temp_styles.decode("utf-8")
    orig_text = _ensure_dxfs_section(orig_text)

    font_base = _section_count(orig_text, "fonts")
    fill_base = _section_count(orig_text, "fills")
    border_base = _section_count(orig_text, "borders")
    xf_base = _section_count(orig_text, "cellXfs")
    dxf_base = _section_count(orig_text, "dxfs")

    for tag, item_tag in (("fonts", "font"), ("fills", "fill"), ("borders", "border")):
        items = _tag_items(_inner_xml(temp_text, tag), item_tag)
        if items:
            orig_text = _insert_styles_fragment(orig_text, tag, "".join(items), len(items))

    xf_items = _tag_items(_inner_xml(temp_text, "cellXfs"), "xf")
    remapped = [
        _remap_xf_ids(xf, font_base=font_base, fill_base=fill_base, border_base=border_base)
        for xf in xf_items
    ]
    if remapped:
        orig_text = _insert_styles_fragment(orig_text, "cellXfs", "".join(remapped), len(remapped))

    dxf_items = _tag_items(_inner_xml(temp_text, "dxfs"), "dxf")
    if dxf_items:
        fragment = "".join(dxf_items)
        if re.search(r"<dxfs count=\"0\"\s*/>", orig_text):
            orig_text = re.sub(
                r"<dxfs count=\"0\"\s*/>",
                f"<dxfs count=\"{len(dxf_items)}\">{fragment}</dxfs>",
                orig_text,
                count=1,
            )
        else:
            orig_text = _insert_styles_fragment(orig_text, "dxfs", fragment, len(dxf_items))

    return orig_text.encode("utf-8"), xf_base, dxf_base


def remap_worksheet_style_indices(sheet_xml: bytes, *, xf_offset: int, dxf_offset: int) -> bytes:
    text = sheet_xml.decode("utf-8")
    text = re.sub(
        r'(\ss=")(\d+)(")',
        lambda m: f'{m.group(1)}{int(m.group(2)) + xf_offset}{m.group(3)}',
        text,
    )
    text = re.sub(
        r'(dxfId=")(\d+)(")',
        lambda m: f'{m.group(1)}{int(m.group(2)) + dxf_offset}{m.group(3)}',
        text,
    )
    return text.encode("utf-8")


def append_edgar_sheet_styles(styles_xml: bytes, banner_families: list[str]) -> tuple[bytes, SheetStyleSet]:
    """Append fonts, fills, borders, xfs and dxfs without re-serializing the stylesheet root."""
    text = styles_xml.decode("utf-8")
    text = _ensure_dxfs_section(text)

    font_base = _section_count(text, "fonts")
    fill_base = _section_count(text, "fills")
    border_base = _section_count(text, "borders")
    xf_base = _section_count(text, "cellXfs")
    dxf_base = _section_count(text, "dxfs")

    font_body = font_base
    font_header = font_base + 1
    font_banner = font_base + 2
    fonts_fragment = (
        _font_xml(bold=False)
        + _font_xml(bold=True, rgb="FFFFFFFF")
        + _font_xml(bold=True, rgb="FF1F3864")
    )
    text = _insert_styles_fragment(text, "fonts", fonts_fragment, 3)

    fill_navy = fill_base
    fill_banners: dict[str, int] = {}
    fills_fragment = _fill_xml("FF1F3864")
    next_fill = fill_base + 1
    for fam in banner_families:
        rgb = BANNER_FILL_RGB.get(fam, "FFE7E6E6")
        fill_banners[fam] = next_fill
        fills_fragment += _fill_xml(rgb)
        next_fill += 1
    text = _insert_styles_fragment(text, "fills", fills_fragment, 1 + len(banner_families))

    border_thin = border_base
    text = _insert_styles_fragment(text, "borders", _border_xml(), 1)

    fill_none = 0
    xf_header = xf_base
    xf_body = xf_base + 1
    xf_body_wrap = xf_base + 2
    xf_gap = xf_base + 3
    xf_number = xf_base + 4
    xfs_fragment = (
        _xf_xml(font_header, fill_navy, border_thin, wrap=True, center=True)
        + _xf_xml(font_body, fill_none, border_thin)
        + _xf_xml(font_body, fill_none, border_thin, wrap=True)
        + _xf_xml(font_body, fill_none, 0)
        + _xf_xml(font_body, fill_none, border_thin, num_fmt_id=2, num_fmt_apply=True)
    )
    xf_banner_map: dict[str, int] = {}
    next_xf = xf_base + 5
    for fam, fill_id in fill_banners.items():
        xf_banner_map[fam] = next_xf
        xfs_fragment += _xf_xml(font_banner, fill_id, border_thin, wrap=True, center=True)
        next_xf += 1
    text = _insert_styles_fragment(text, "cellXfs", xfs_fragment, next_xf - xf_base)

    dxf_band = dxf_base
    dxf_match = dxf_base + 1
    dxf_mismatch = dxf_base + 2
    dxfs_fragment = _dxf_band_xml() + _dxf_result_xml(match=True) + _dxf_result_xml(match=False)
    if re.search(r"<dxfs count=\"0\"\s*/>", text):
        text = re.sub(
            r"<dxfs count=\"0\"\s*/>",
            f"<dxfs count=\"3\">{dxfs_fragment}</dxfs>",
            text,
            count=1,
        )
    else:
        text = _insert_styles_fragment(text, "dxfs", dxfs_fragment, 3)

    styles = SheetStyleSet(
        xf_header=xf_header,
        xf_body=xf_body,
        xf_body_wrap=xf_body_wrap,
        xf_gap=xf_gap,
        xf_number=xf_number,
        xf_bool=xf_body,
        xf_banner=xf_banner_map,
        dxf_band=dxf_band,
        dxf_match=dxf_match,
        dxf_mismatch=dxf_mismatch,
    )
    return text.encode("utf-8"), styles


def _next_sheet_part(existing_names: list[str]) -> str:
    nums = []
    for name in existing_names:
        m = re.match(r"xl/worksheets/sheet(\d+)\.xml", name)
        if m:
            nums.append(int(m.group(1)))
    n = max(nums) + 1 if nums else 1
    return f"xl/worksheets/sheet{n}.xml"


def _next_rid(rels_xml: bytes) -> str:
    ids = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels_xml.decode())]
    return f"rId{max(ids) + 1 if ids else 1}"


def _next_sheet_id(workbook_xml: bytes) -> int:
    ids = [int(m) for m in re.findall(r'sheetId="(\d+)"', workbook_xml.decode())]
    return max(ids) + 1 if ids else 1


def _patch_workbook(
    workbook_xml: bytes,
    *,
    sheet_name: str,
    rel_id: str,
    sheet_id: int,
    filter_defined_name: str,
    local_sheet_id: int,
) -> bytes:
    text = workbook_xml.decode()
    wb_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    wb_open = re.search(r"<workbook[^>]*>", text)
    if wb_open and "xmlns:r=" not in wb_open.group(0):
        tag = wb_open.group(0)
        patched = tag[:-1] + f' xmlns:r="{wb_rel}">'
        text = text[: wb_open.start()] + patched + text[wb_open.end() :]
    insert = f'<sheet name="{sheet_name}" sheetId="{sheet_id}" r:id="{rel_id}"/>'
    text = text.replace("</sheets>", insert + "</sheets>", 1)
    dn = (
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="{local_sheet_id}" '
        f'hidden="1">{filter_defined_name}</definedName>'
    )
    if "<definedNames/>" in text:
        text = text.replace("<definedNames/>", f"<definedNames>{dn}</definedNames>", 1)
    else:
        text = text.replace("</definedNames>", dn + "</definedNames>", 1)
    return text.encode()


def _patch_rels(rels_xml: bytes, *, rel_id: str, target: str) -> bytes:
    text = rels_xml.decode()
    rel = (
        f'<Relationship Id="{rel_id}" Type="{REL_WORKSHEET}" Target="{target}"/>'
    )
    text = text.replace("</Relationships>", rel + "</Relationships>", 1)
    return text.encode()


def _patch_content_types(ct_xml: bytes, *, part_name: str) -> bytes:
    text = ct_xml.decode()
    override = f'<Override PartName="{part_name}" ContentType="{SHEET_CT}"/>'
    text = text.replace("</Types>", override + "</Types>", 1)
    return text.encode()


def splice_add_worksheet(
    src_path: Path,
    dst_path: Path,
    *,
    sheet_name: str,
    sheet_xml: bytes,
    styles_xml: bytes | None,
    filter_defined_name: str,
) -> None:
    """Copy ``src_path`` to ``dst_path``, optionally replacing styles and adding one sheet."""
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src_path, "r") as zin:
        names = zin.namelist()
        sheet_part = _next_sheet_part(names)
        sheet_filename = sheet_part.split("/")[-1]
        rels_xml = zin.read("xl/_rels/workbook.xml.rels")
        workbook_xml = zin.read("xl/workbook.xml")
        ct_xml = zin.read("[Content_Types].xml")

        rel_id = _next_rid(rels_xml)
        sheet_id = _next_sheet_id(workbook_xml)
        local_sheet_id = len(re.findall(r"<sheet ", workbook_xml.decode()))

        new_rels = _patch_rels(
            rels_xml, rel_id=rel_id, target=f"worksheets/{sheet_filename}"
        )
        new_wb = _patch_workbook(
            workbook_xml,
            sheet_name=sheet_name,
            rel_id=rel_id,
            sheet_id=sheet_id,
            filter_defined_name=filter_defined_name,
            local_sheet_id=local_sheet_id,
        )
        part_name = "/" + sheet_part
        new_ct = _patch_content_types(ct_xml, part_name=part_name)

        modified = {"xl/styles.xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml", sheet_part}

        with zipfile.ZipFile(dst_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                name = info.filename
                if name in modified:
                    continue
                zout.writestr(info, zin.read(name))

            zout.writestr(sheet_part, sheet_xml)
            zout.writestr("xl/workbook.xml", new_wb)
            zout.writestr("xl/_rels/workbook.xml.rels", new_rels)
            zout.writestr("[Content_Types].xml", new_ct)
            if styles_xml is not None:
                zout.writestr("xl/styles.xml", styles_xml)
            else:
                zout.writestr("xl/styles.xml", zin.read("xl/styles.xml"))


def add_sheet_to_xlsx(
    src_path: Path,
    dst_path: Path,
    sheet_name: str,
    build_sheet_xml: Callable[[SheetStyleSet], bytes],
    banner_families: list[str],
    filter_defined_name: str,
) -> SheetStyleSet:
    """Append styles, build sheet XML, and write a lossless copy with the new sheet."""
    with zipfile.ZipFile(src_path, "r") as zin:
        styles_in = zin.read("xl/styles.xml")
    new_styles, style_set = append_edgar_sheet_styles(styles_in, banner_families)
    sheet_xml = build_sheet_xml(style_set)
    splice_add_worksheet(
        src_path,
        dst_path,
        sheet_name=sheet_name,
        sheet_xml=sheet_xml,
        styles_xml=new_styles,
        filter_defined_name=filter_defined_name,
    )
    return style_set
