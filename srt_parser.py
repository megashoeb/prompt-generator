"""SRT Parser with smart auto-chunking based on timestamp gaps."""

import re
from dataclasses import dataclass


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
