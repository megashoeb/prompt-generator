"""Export prompts to .txt and .xlsx formats."""

import io
import re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


def remove_duplicate_style(text: str) -> str:
    """Remove duplicate style blocks from prompt text, keeping only the last one.

    Handles all four built-in style line patterns:
      • Dark Fantasy  — starts with "Hyper-detailed dark fantasy digital painting"
      • History 1     — starts with "Hand-painted oil illustration on aged"
      • Woodcut       — starts with "woodcut linocut relief print"
      • Victorian     — starts with "vintage 19th century newspaper engraving"
    """
    style_patterns = [
        r'(Hyper-detailed dark fantasy digital painting.*?16:9 aspect ratio\.?)',
        r'(Hand-painted oil illustration on aged.*?16:9 aspect ratio\.?)',
        r'(digital oil-paint realism.*?16:9 aspect ratio\.?)',           # History 2 Color
        r'(vintage monochrome charcoal sketch.*?16:9 aspect ratio\.?)',  # History 2 B&W
        r'(Classic impasto oil painting.*?16:9 aspect ratio\.?)',        # History 3
        r'(Ancient fresco on aged cracked plaster.*?16:9 aspect ratio\.?)',  # History 4
        r'(Hand-drawn 2D animation-style digital illustration.*?16:9 aspect ratio\.?)',  # History 5
        r'(woodcut linocut relief print.*?16:9)',
        r'(vintage 19th century newspaper engraving.*?16:9)',
    ]
    for style_pattern in style_patterns:
        matches = list(re.finditer(style_pattern, text, re.DOTALL | re.IGNORECASE))
        if len(matches) >= 2:
            # Remove all but the last occurrence
            for match in matches[:-1]:
                start = match.start()
                end = match.end()
                # Also eat any trailing punctuation/spaces before the next block
                while start > 0 and text[start - 1] in ' ,.\n':
                    start -= 1
                text = text[:start] + ' ' + text[end:]
            # Clean up any double spaces or ". ." artifacts left behind
            text = re.sub(r' {2,}', ' ', text)
            text = re.sub(r'\. \.', '.', text)
    return text.strip()


def count_color_bw(prompts: list[dict]) -> tuple[int, int]:
    """Count Color vs B&W prompts for History 2 style.

    Returns (color_count, bw_count).
    Detection is keyword-based on the generated prompt text.
    """
    _BW_KEYWORDS    = ('monochrome', 'charcoal sketch', 'chalk-line', 'grayscale', 'black and white')
    _COLOR_KEYWORDS = ('oil-paint realism', 'candlelight glow', 'golden highlights', 'chiaroscuro')
    color_count = bw_count = 0
    for p in prompts:
        text = p.get("image_prompt", "").lower()
        if any(kw in text for kw in _BW_KEYWORDS):
            bw_count += 1
        elif any(kw in text for kw in _COLOR_KEYWORDS):
            color_count += 1
        else:
            color_count += 1   # default to Color when ambiguous
    return color_count, bw_count


def count_noor_prompts(prompts: list[dict]) -> tuple[int, int]:
    """Count Noor (sacred figure) vs normal prompts for History 3 style.

    Returns (noor_count, normal_count).
    """
    _NOOR_KEYWORDS = ('noor light', 'divine luminance', 'blinding golden', 'obscures all physical features')
    noor_count = normal_count = 0
    for p in prompts:
        text = p.get("image_prompt", "").lower()
        if any(kw in text for kw in _NOOR_KEYWORDS):
            noor_count += 1
        else:
            normal_count += 1
    return noor_count, normal_count


def count_fire_accent_prompts(prompts: list[dict]) -> tuple[int, int]:
    """Count how many History 5 prompts include fire/torch warm glow accent.

    Returns (fire_count, no_fire_count).
    """
    _FIRE_KEYWORDS = (
        'campfire', 'torch', 'fire glow', 'ember sparks',
        'firelight', 'fire orange', 'ember red', 'warm glow spill',
    )
    fire_count = no_fire_count = 0
    for p in prompts:
        text = p.get("image_prompt", "").lower()
        if any(kw in text for kw in _FIRE_KEYWORDS):
            fire_count += 1
        else:
            no_fire_count += 1
    return fire_count, no_fire_count


def _detect_prompt_type(prompt_text: str) -> str:
    """Return 'B&W' or 'Color' for a single prompt string (History 2 use)."""
    t = prompt_text.lower()
    if any(kw in t for kw in ('monochrome', 'charcoal sketch', 'chalk-line', 'grayscale', 'black and white')):
        return "B&W"
    return "Color"


def process_prompt_with_style(scene_text: str, style_key: str,
                               subtitle_text: str = "") -> str:
    """Apply visual-style post-processing to an already-extracted scene description.

    For dark_fantasy / custom the LLM wrote the complete prompt — return unchanged.
    For woodcut / victorian_engraving:
      • Apply safety word replacements
      • Trim to word limit
      • Append scene-specific color accent + style line
    """
    try:
        from styles import STYLES, build_final_prompt
    except ImportError:
        return scene_text   # styles.py not present — no-op

    style = STYLES.get(style_key, STYLES["dark_fantasy"])
    if not style.get("append_style", False):
        return scene_text

    return build_final_prompt(scene_text, style_key, subtitle_text or scene_text)


def clean_prompt_text(text: str) -> str:
    """Clean markdown artifacts and bracket formatting from prompt text."""
    # Remove ** bold markers
    text = text.replace("**", "")

    # Remove * italic markers (standalone asterisks around words)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Remove any remaining lone * characters
    text = text.replace("*", "")

    # Remove # headers at start of lines
    text = re.sub(r'(?m)^#+\s*', '', text)

    # Remove bracket tags if they slipped through
    bracket_tags = [
        "[Subject:", "[Action:", "[Location/Context:", "[Location:",
        "[Composition:", "[Camera/Lens:", "[Camera:", "[Lens:",
        "[Color Grading:", "[Color:", "[Style:", "[Style + Lighting + Texture:",
        "[Lighting:", "[Texture:", "[Aspect Ratio:",
    ]
    for tag in bracket_tags:
        text = text.replace(tag, "")

    # Remove closing brackets
    text = text.replace("]", "")

    # Remove + separators between sections (e.g. "...detail] + [Next...")
    text = re.sub(r'\s*\+\s*(?=[A-Z])', ' ', text)

    # Remove [STYLE: ...] shorthand tags
    text = re.sub(r'\[STYLE:[^\]]*\]', '', text)

    # Remove [REFRESH ...] internal tags
    text = re.sub(r'\[REFRESH[^\]]*\]', '', text)

    # Remove character ID tags like [IBLIS-01] [TRAVELER-01]
    text = re.sub(r'\[[A-Z]+-\d+\]', '', text)

    # Clean up multiple spaces
    text = re.sub(r' {2,}', ' ', text)

    # Remove duplicate style blocks
    text = remove_duplicate_style(text)

    # ── Full mojibake fix (em dashes, smart quotes, Turkish/Hungarian) ────────
    mojibake_map = {
        # Em / en dashes (most common artifact)
        'â\x80\x93': '–',      # en dash
        'â\x80\x94': '—',      # em dash
        'â€"': '—',             # em dash variant (double-encoded)
        'â€"': '–',             # en dash variant (double-encoded)
        'â\x96\xa1': '—',      # □ box char → em dash
        'â□□': '—',             # visible box form
        # Smart quotes
        'â\x80\x99': '\u2019', # right single quote  '
        'â\x80\x98': '\u2018', # left single quote   '
        'â€™': '\u2019',       # right single quote variant
        'â€˜': '\u2018',       # left single quote variant
        'â\x80\x9c': '\u201c', # left double quote   "
        'â\x80\x9d': '\u201d', # right double quote  "
        'â€œ': '\u201c',       # left double quote variant
        'â€\x9d': '\u201d',    # right double quote variant
        # Turkish characters
        'Ã¶': 'ö', 'Ãœ': 'Ü', 'Ã¼': 'ü', 'Ã–': 'Ö',
        'Ã§': 'ç', 'Ã‡': 'Ç', 'ÅŸ': 'ş', 'Åž': 'Ş',
        'ÄŸ': 'ğ', 'Äž': 'Ğ', 'Ä±': 'ı', 'Ä°': 'İ',
        # Latin / Hungarian characters
        'Ã¡': 'á', 'Ã': 'Á', 'Ã©': 'é', 'Ã‰': 'É',
        'Ã­': 'í', 'Ã': 'Í', 'Ã³': 'ó', 'Ã"': 'Ó',
        'Ã±': 'ñ', 'Ã¤': 'ä', 'Ã¸': 'ø', 'Ã¥': 'å',
        "Å'": 'ő', 'Å"': 'Ő', 'Å±': 'ű', 'Å°': 'Ű',
        # Common punctuation
        'Â¿': '¿', 'Â¡': '¡', 'Ã ': 'à', 'Â·': '·',
        # Common proper-name mojibake (history content)
        'GÃ¶bekli': 'Göbekli', 'GÃ¶beklitepe': 'Göbeklitepe',
        'MohÃ¡cs': 'Mohács', 'SÃ¼leyman': 'Süleyman',
        'ZÃ¡polya': 'Zápolya', 'BÃ¡thory': 'Báthory',
        'JÃ¡nos': 'János',
    }
    for bad, good in mojibake_map.items():
        text = text.replace(bad, good)
    # Catch-all: â followed by two continuation bytes = broken UTF-8 sequence
    text = re.sub(r'â[\x80-\xbf][\x80-\xbf]', '—', text)
    text = re.sub(r'â□+', '—', text)
    # Bare â with no continuation bytes (e.g. "hyper-detailed" → "hyperâdetailed")
    # This happens when UTF-8 continuation bytes are silently dropped.
    text = text.replace('â', '-')

    # Clean up leading/trailing whitespace
    return text.strip()


def validate_prompt_count(prompts_list: list[dict], total_expected: int) -> dict:
    """Validate generated prompt count against expected total.

    Args:
        prompts_list: list of prompt dicts with 'block' key
        total_expected: total number of SRT subtitle blocks

    Returns:
        dict with keys: expected, generated, missing (list), extra (list), is_perfect (bool)
    """
    expected_set  = set(range(1, total_expected + 1))
    generated_set = set(p["block"] for p in prompts_list)

    missing = sorted(expected_set - generated_set)
    extra   = sorted(generated_set - expected_set)

    return {
        "expected":   total_expected,
        "generated":  len(generated_set),
        "missing":    missing,
        "extra":      extra,
        "is_perfect": len(missing) == 0 and len(extra) == 0,
    }


def export_txt(prompts: list[dict], mode: str) -> str:
    lines = []
    for p in prompts:
        image_prompt = clean_prompt_text(p['image_prompt'])
        lines.append(f"Image Prompt {p['block']}: {image_prompt}")
        if mode == "B" and p.get('video_prompt'):
            video_prompt = clean_prompt_text(p['video_prompt'])
            lines.append(f"Video Prompt {p['block']}: {video_prompt}")
        lines.append("")
    return '\n'.join(lines)


def export_xlsx(prompts: list[dict], mode: str, style_key: str = "") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Image Prompts"

    header_fill  = PatternFill('solid', fgColor='1a1a2e')
    header_font  = Font(name='Arial', bold=True, color='FFFFFF', size=11)
    thin_border  = Border(
        left=Side(style='thin', color='d0d0d0'),
        right=Side(style='thin', color='d0d0d0'),
        top=Side(style='thin', color='d0d0d0'),
        bottom=Side(style='thin', color='d0d0d0')
    )
    # History 2 Color/B&W row fills
    color_fill = PatternFill('solid', fgColor='FFF3E0')   # warm amber for Color rows
    bw_fill    = PatternFill('solid', fgColor='F5F5F5')   # light grey for B&W rows

    is_h2 = style_key == "history_2"
    is_h4 = style_key == "history_4"
    # History 4 word-count fills
    wc_ok_fill  = PatternFill('solid', fgColor='E8F5E9')   # light green — within target range
    wc_bad_fill = PatternFill('solid', fgColor='FFEBEE')   # light red   — outside target range

    if is_h2:
        if mode == "B":
            headers    = ['Block #', 'Type', 'Image Prompt', 'Video Prompt']
            col_widths = [8, 10, 80, 60]
        else:
            headers    = ['Block #', 'Type', 'Image Prompt']
            col_widths = [8, 10, 90]
    elif is_h4:
        if mode == "B":
            headers    = ['Block #', 'Words', 'Image Prompt', 'Video Prompt']
            col_widths = [8, 8, 80, 60]
        else:
            headers    = ['Block #', 'Words', 'Image Prompt']
            col_widths = [8, 8, 90]
    elif mode == "B":
        headers    = ['Block #', 'Image Prompt', 'Video Prompt']
        col_widths = [8, 80, 60]
    else:
        headers    = ['Block #', 'Image Prompt']
        col_widths = [8, 100]

    for i, (h, w) in enumerate(zip(headers, col_widths), 1):
        cell = ws.cell(row=1, column=i, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.column_dimensions[chr(64 + i)].width = w

    for row_idx, p in enumerate(prompts, 2):
        prompt_text = clean_prompt_text(p['image_prompt'])

        # ── Block # ──────────────────────────────────────────────────────────
        cell_num = ws.cell(row=row_idx, column=1, value=p['block'])
        cell_num.font      = Font(name='Arial', size=10, bold=True)
        cell_num.alignment = Alignment(horizontal='center', vertical='top')
        cell_num.border    = thin_border

        if is_h2:
            # ── Type column (Color / B&W) ─────────────────────────────────
            ptype      = _detect_prompt_type(prompt_text)
            row_fill   = bw_fill if ptype == "B&W" else color_fill
            type_label = "⬛ B&W" if ptype == "B&W" else "🎨 Color"

            cell_type            = ws.cell(row=row_idx, column=2, value=type_label)
            cell_type.font       = Font(name='Arial', size=10, bold=True)
            cell_type.alignment  = Alignment(horizontal='center', vertical='top')
            cell_type.border     = thin_border
            cell_type.fill       = row_fill

            cell_img             = ws.cell(row=row_idx, column=3, value=prompt_text)
            cell_img.font        = Font(name='Arial', size=10)
            cell_img.alignment   = Alignment(vertical='top', wrap_text=True)
            cell_img.border      = thin_border
            cell_img.fill        = row_fill

            if mode == "B":
                cell_vid           = ws.cell(row=row_idx, column=4, value=clean_prompt_text(p.get('video_prompt', '')))
                cell_vid.font      = Font(name='Arial', size=10)
                cell_vid.alignment = Alignment(vertical='top', wrap_text=True)
                cell_vid.border    = thin_border
                cell_vid.fill      = row_fill
        elif is_h4:
            # ── Word count column ─────────────────────────────────────────
            actual_wc = len(prompt_text.split())
            in_range  = 25 <= actual_wc <= 47   # ±3 of min/max targets
            wc_fill   = wc_ok_fill if in_range else wc_bad_fill

            cell_wc            = ws.cell(row=row_idx, column=2, value=actual_wc)
            cell_wc.font       = Font(name='Arial', size=10, bold=True)
            cell_wc.alignment  = Alignment(horizontal='center', vertical='top')
            cell_wc.border     = thin_border
            cell_wc.fill       = wc_fill

            cell_img           = ws.cell(row=row_idx, column=3, value=prompt_text)
            cell_img.font      = Font(name='Arial', size=10)
            cell_img.alignment = Alignment(vertical='top', wrap_text=True)
            cell_img.border    = thin_border
            cell_img.fill      = wc_fill

            if mode == "B":
                cell_vid           = ws.cell(row=row_idx, column=4, value=clean_prompt_text(p.get('video_prompt', '')))
                cell_vid.font      = Font(name='Arial', size=10)
                cell_vid.alignment = Alignment(vertical='top', wrap_text=True)
                cell_vid.border    = thin_border
        else:
            cell_img             = ws.cell(row=row_idx, column=2, value=prompt_text)
            cell_img.font        = Font(name='Arial', size=10)
            cell_img.alignment   = Alignment(vertical='top', wrap_text=True)
            cell_img.border      = thin_border

            if mode == "B":
                cell_vid           = ws.cell(row=row_idx, column=3, value=clean_prompt_text(p.get('video_prompt', '')))
                cell_vid.font      = Font(name='Arial', size=10)
                cell_vid.alignment = Alignment(vertical='top', wrap_text=True)
                cell_vid.border    = thin_border

        ws.row_dimensions[row_idx].height = 80

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
