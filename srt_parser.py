"""SRT Parser with smart auto-chunking based on timestamp gaps."""

import re
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# ENCODING HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fix_mojibake(text: str) -> str:
    """Fix common UTF-8 double-encoding mojibake patterns (Hungarian/Turkish chars)."""
    replacements = {
        # Turkish
        'Ã¡': 'á', 'Ã©': 'é', 'Ã­': 'í', 'Ã³': 'ó', 'Ã¶': 'ö', 'Ã¼': 'ü',
        'Ã‡': 'Ç', 'Ã§': 'ç', '\u00c5\u009f': 'ş', '\u00c5\u009e': 'Ş',
        '\u00c4\u009f': 'ğ', '\u00c4\u009e': 'Ğ', '\u00c4\u00b1': 'ı', '\u00c4\u00b0': 'İ',
        # Hungarian / Central European
        '\u00c3\u0081': 'Á', '\u00c3\u0089': 'É', '\u00c3\u008d': 'Í',
        '\u00c3\u0093': 'Ó', '\u00c3\u0096': 'Ö', '\u00c3\u009c': 'Ü',
        '\u00c5\u0091': 'ő', '\u00c5\u0090': 'Ő', '\u00c5\u00b1': 'ű', '\u00c5\u00b0': 'Ű',
        'Ã¤': 'ä', 'Ã¸': 'ø', 'Ã¥': 'å', 'Ã±': 'ñ',
        # Literal mojibake strings
        'JÃ¡nos': 'János', 'ZÃ¡polya': 'Zápolya', 'BÃ¡thory': 'Báthory',
        'MohÃ¡cs': 'Mohács', 'SzÃ©kesfehÃ©rvÃ¡r': 'Székesfehérvár',
        # Common punctuation mojibake
        'â€"': '—', 'â€"': '–', 'â€™': '\u2019', 'â€œ': '\u201c',
        'Â·': '·', 'Â ': ' ',
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def decode_srt_bytes(raw_bytes: bytes) -> tuple[str, str]:
    """Decode raw SRT file bytes with smart encoding detection.

    Returns (decoded_text, encoding_used_label).
    Tries chardet first, then common Central-European and Turkish encodings.
    """
    detected_enc = 'utf-8'
    try:
        import chardet
        result = chardet.detect(raw_bytes)
        detected_enc = result.get('encoding') or 'utf-8'
    except ImportError:
        pass   # chardet not installed — fall through to heuristic list

    seen: set[str] = set()
    candidates: list[str] = []
    for enc in [detected_enc, 'utf-8-sig', 'utf-8',
                'windows-1254', 'cp1254',          # Turkish
                'windows-1250', 'iso-8859-2',       # Hungarian / Central European
                'latin-1', 'windows-1252']:
        if enc and enc.lower() not in seen:
            seen.add(enc.lower())
            candidates.append(enc)

    for enc in candidates:
        try:
            text = raw_bytes.decode(enc)
            # Reject if obvious mojibake or null bytes
            if 'Ã' not in text and '\x00' not in text[:200]:
                return text, enc
        except (UnicodeDecodeError, LookupError):
            continue

    # Final fallback — replace undecodeable bytes
    return raw_bytes.decode('utf-8', errors='replace'), 'utf-8 (fallback)'


@dataclass
class SubtitleBlock:
    index: int
    start_time: str
    end_time: str
    text: str


def parse_srt(srt_content: str) -> list[SubtitleBlock]:
    blocks = []
    raw_blocks = re.split(r'\n\s*\n', srt_content.strip())

    for raw in raw_blocks:
        lines = raw.strip().split('\n')
        if len(lines) < 2:
            continue

        try:
            index = int(lines[0].strip())
        except ValueError:
            continue

        time_match = re.match(
            r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})',
            lines[1].strip()
        )
        if not time_match:
            continue

        text = ' '.join(lines[2:]).strip()
        if not text:
            continue

        blocks.append(SubtitleBlock(
            index=index,
            start_time=time_match.group(1),
            end_time=time_match.group(2),
            text=text
        ))

    return blocks


def time_to_seconds(time_str: str) -> float:
    time_str = time_str.replace(',', '.')
    parts = time_str.split(':')
    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])


def block_duration(block: SubtitleBlock) -> float:
    """Return the duration in seconds for a SubtitleBlock."""
    return max(0.0, time_to_seconds(block.end_time) - time_to_seconds(block.start_time))


def auto_chunk(blocks: list[SubtitleBlock], target_chunk_size: int = 30, gap_threshold: float = 3.0) -> list[list[SubtitleBlock]]:
    if len(blocks) <= target_chunk_size:
        return [blocks]

    scene_breaks = []
    for i in range(1, len(blocks)):
        prev_end = time_to_seconds(blocks[i - 1].end_time)
        curr_start = time_to_seconds(blocks[i].start_time)
        gap = curr_start - prev_end
        if gap >= gap_threshold:
            scene_breaks.append(i)

    if not scene_breaks:
        chunks = []
        for i in range(0, len(blocks), target_chunk_size):
            chunks.append(blocks[i:i + target_chunk_size])
        return chunks

    chunks = []
    current_chunk_start = 0

    for break_idx in scene_breaks:
        chunk_size = break_idx - current_chunk_start
        if chunk_size >= target_chunk_size * 0.6:
            chunks.append(blocks[current_chunk_start:break_idx])
            current_chunk_start = break_idx

    if current_chunk_start < len(blocks):
        remaining = blocks[current_chunk_start:]
        if chunks and len(remaining) < target_chunk_size * 0.4:
            chunks[-1].extend(remaining)
        else:
            chunks.append(remaining)

    if len(chunks) == 1 and len(chunks[0]) > target_chunk_size * 1.5:
        big_chunk = chunks[0]
        chunks = []
        for i in range(0, len(big_chunk), target_chunk_size):
            chunks.append(big_chunk[i:i + target_chunk_size])

    # ── Integrity validation — every input block must appear exactly once ─────
    seen_indices: set[int] = set()
    duplicates:   list[int] = []
    for chunk in chunks:
        for block in chunk:
            if block.index in seen_indices:
                duplicates.append(block.index)
            seen_indices.add(block.index)

    expected_indices = {b.index for b in blocks}
    missing_from_chunks = expected_indices - seen_indices

    if missing_from_chunks:
        # Safety: append missing blocks to the last chunk so nothing is lost
        missing_blocks = [b for b in blocks if b.index in missing_from_chunks]
        if chunks:
            chunks[-1].extend(missing_blocks)
            chunks[-1].sort(key=lambda b: b.index)
        else:
            chunks = [missing_blocks]

    return chunks


def smart_chunk_by_breaks(
    blocks: list[SubtitleBlock], break_points: list[int]
) -> list[list[SubtitleBlock]]:
    """Divide blocks at LLM-identified scene-break block numbers.

    break_points is a list of subtitle block *index values* (as in SubtitleBlock.index)
    where new chunks should START. The first value should be 1 (or the first block's index).
    """
    if not break_points:
        return [blocks]

    # Map block index values → position in the blocks list
    index_to_pos: dict[int, int] = {b.index: i for i, b in enumerate(blocks)}

    start_positions: set[int] = {0}  # always start at position 0
    for bp in break_points:
        # Find the first block whose index is >= the break-point value
        for i, b in enumerate(blocks):
            if b.index >= bp:
                start_positions.add(i)
                break

    sorted_starts = sorted(start_positions)
    chunks: list[list[SubtitleBlock]] = []
    for j, start in enumerate(sorted_starts):
        end = sorted_starts[j + 1] if j + 1 < len(sorted_starts) else len(blocks)
        if end > start:
            chunks.append(blocks[start:end])

    return chunks if chunks else [blocks]


def format_chunk_for_api(chunk: list[SubtitleBlock]) -> str:
    lines = []
    for block in chunk:
        lines.append(f"{block.index}")
        lines.append(f"{block.start_time} --> {block.end_time}")
        lines.append(block.text)
        lines.append("")
    return '\n'.join(lines)
