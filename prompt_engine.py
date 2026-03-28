"""Prompt engine — builds user messages for each chunk."""

import os
import re
from output_writer import clean_prompt_text
from srt_parser import time_to_seconds

SYSTEM_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
SYSTEM_PROMPT_SHORT_FILE = os.path.join(os.path.dirname(__file__), "system_prompt_short.txt")


def load_system_prompt() -> str:
    with open(SYSTEM_PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read()


def load_system_prompt_short() -> str:
    """Load the shorter continuation system prompt (for chunks 2+).
    Falls back to the full system prompt if the short version does not exist."""
    if os.path.exists(SYSTEM_PROMPT_SHORT_FILE):
        with open(SYSTEM_PROMPT_SHORT_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    return load_system_prompt()


def build_chunk1_message(srt_text: str, block_start: int, block_end: int, total_blocks: int, mode: str) -> str:
    mode_text = "Option A: Image Prompts Only" if mode == "A" else "Option B: Image + Video Prompts"
    n_prompts = block_end - block_start + 1
    return f"""Selected mode: {mode_text}

This is Chunk 1. The full SRT contains {total_blocks} subtitle blocks.
Generate Image Prompt {block_start} through Image Prompt {block_end}.
You MUST generate EXACTLY {n_prompts} prompts for this chunk.
First prompt: Image Prompt {block_start}
Last prompt: Image Prompt {block_end}
Total prompts for this chunk: EXACTLY {n_prompts}

Do NOT merge blocks. Do NOT skip blocks. Do NOT add extra prompts.
Every subtitle block gets exactly ONE prompt — even single-word blocks.
If a block is very short, use surrounding context to infer a transitional visual.

IMPORTANT: You MUST output the full pre-analysis (Story Summary, Story Outline, Character Registry with Character Cards, Sacred Figure Protocol Tags, Scene Location Map, Color Grading Map) BEFORE generating any prompts. Do NOT skip the pre-analysis. If you skip the pre-analysis and jump directly to Image Prompt 1, your entire output is invalid.

IMPORTANT: Write every Image Prompt as ONE continuous flowing narrative paragraph. Do NOT use bracket tags like [Subject:], [Action:], [Location:], [Composition:], [Camera/Lens:], [Color Grading:], [Style:] or + signs between sections. All prompts must be plain text with no markdown (no **, no *, no #).

SRT blocks for this chunk:
{srt_text}"""


def build_continuation_chunk_message(
    srt_text: str,
    chunk_number: int,
    total_chunks: int,
    block_start: int,
    block_end: int,
    character_cards: str,
    last_prompt: str,
    scene_context: str,
    mode: str
) -> str:
    mode_text = "Option A: Image Prompts Only" if mode == "A" else "Option B: Image + Video Prompts"
    n_prompts = block_end - block_start + 1
    return f"""Selected mode: {mode_text}

This is Chunk {chunk_number} of {total_chunks}.
Generate Image Prompt {block_start} through Image Prompt {block_end}.
You MUST generate EXACTLY {n_prompts} prompts for this chunk.
First prompt: Image Prompt {block_start}
Last prompt: Image Prompt {block_end}
Total prompts for this chunk: EXACTLY {n_prompts}

Do NOT merge blocks. Do NOT skip blocks. Do NOT add extra prompts.
Every subtitle block gets exactly ONE prompt — even single-word blocks.
If a block is very short, use surrounding context to infer a transitional visual.

Active Character Cards for this section:
{character_cards}

Scene context for this section:
{scene_context}

Continuity reference — last prompt from previous chunk:
{last_prompt}

SRT blocks for this chunk:
{srt_text}"""


def extract_character_cards(chunk1_response: str) -> str:
    patterns = [
        r'(CHARACTER REGISTRY.*?)(?=SACRED FIGURE|SCENE LOCATION|COLOR GRADING|\n\n[A-Z]{3,})',
        r'(CHARACTER CARD.*?)(?=SACRED FIGURE|SCENE LOCATION|COLOR GRADING|\n\n[A-Z]{3,})',
    ]
    for pattern in patterns:
        match = re.search(pattern, chunk1_response, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

    lines = chunk1_response.split('\n')
    card_lines = []
    capturing = False
    for line in lines:
        if 'CHARACTER CARD' in line.upper() or 'CHARACTER REGISTRY' in line.upper():
            capturing = True
        if capturing:
            card_lines.append(line)
            if len(card_lines) > 5 and line.strip() == '' and card_lines[-2].strip() == '':
                break
    if card_lines:
        return '\n'.join(card_lines).strip()

    return "No character cards found — use full Pre-Analysis from Chunk 1."


def extract_last_prompt(response: str) -> str:
    pattern = r'(Image Prompt\s*\d+\s*:.*?)(?=Image Prompt\s*\d+\s*:|Video Prompt|$)'
    matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
    if matches:
        return matches[-1].strip()

    lines = response.strip().split('\n')
    last_lines = '\n'.join(lines[-20:])
    return last_lines


def extract_all_prompts(response: str) -> list[dict]:
    """Extract all prompts from LLM response using dict-keyed deduplication.

    Supports multiple prompt header formats:
      'Image Prompt 1: ...'
      'Prompt 1: ...'
      'Prompt 1 – ...'   (em-dash variant)
      'prompt 1 – ...'   (lowercase variant)
    """
    # ── Image prompts ─────────────────────────────────────────────────────────
    img_patterns = [
        r'Image\s+Prompt\s+(\d+)\s*[:–-]\s*(.*?)(?=(?:Video\s+Prompt\s*\d+|Image\s+Prompt\s*\d+|$))',
        r'(?<!\w)Prompt\s+(\d+)\s*[:–-]\s*(.*?)(?=(?:Video\s+Prompt\s*\d+|(?<!\w)Prompt\s+\d+\s*[:–-]|$))',
    ]
    img_dict: dict[int, str] = {}
    for pattern in img_patterns:
        matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
        if matches:
            for num_str, text in matches:
                num = int(num_str)
                cleaned = clean_prompt_text(text.strip())
                if cleaned and len(cleaned) > 15:   # skip empty/noise extractions
                    if num not in img_dict:           # first occurrence wins
                        img_dict[num] = cleaned
            break  # stop at first pattern that yields results

    # ── Video prompts ─────────────────────────────────────────────────────────
    vid_pattern = r'Video\s+Prompt\s*(\d+)\s*[:–-]\s*(.*?)(?=(?:Image\s+Prompt\s*\d+|Video\s+Prompt\s*\d+|$))'
    vid_matches = re.findall(vid_pattern, response, re.DOTALL | re.IGNORECASE)
    vid_dict: dict[int, str] = {}
    for num_str, text in vid_matches:
        num = int(num_str)
        cleaned = clean_prompt_text(text.strip())
        if cleaned and num not in vid_dict:
            vid_dict[num] = cleaned

    # ── Build sorted list ─────────────────────────────────────────────────────
    prompts = []
    for num in sorted(img_dict.keys()):
        prompts.append({
            "block": num,
            "image_prompt": img_dict[num],
            "video_prompt": vid_dict.get(num, ""),
        })

    return prompts


def infer_scene_context(srt_text: str) -> str:
    text_lower = srt_text.lower()
    contexts = []

    if any(w in text_lower for w in ['desert', 'sand', 'dune', 'çöl', 'sahra']):
        contexts.append("Arabian/Middle Eastern desert landscape")
    if any(w in text_lower for w in ['temple', 'palace', 'throne', 'saray', 'tapınak']):
        contexts.append("Ancient palace or temple interior")
    if any(w in text_lower for w in ['battle', 'army', 'soldier', 'war', 'savaş', 'asker', 'ordu']):
        contexts.append("Battlefield or military scene")
    if any(w in text_lower for w in ['night', 'moon', 'dark', 'gece', 'karanlık']):
        contexts.append("Night scene, moonlit")
    if any(w in text_lower for w in ['fire', 'flame', 'burn', 'ateş', 'alev']):
        contexts.append("Fire/flame elements present")
    if any(w in text_lower for w in ['god', 'divine', 'heaven', 'paradise', 'cennet', 'tanrı']):
        contexts.append("Divine/celestial setting")
    if any(w in text_lower for w in ['sea', 'ocean', 'water', 'deniz', 'okyanus']):
        contexts.append("Maritime/oceanic setting")

    if not contexts:
        contexts.append("General mythological/historical setting")

    return "Location: " + ", ".join(contexts) + "\nColor palette: Match to scene mood — warm amber for desert, cold blue for night, golden for divine, red-amber for battle"


def load_system_prompt_for_style(style_key: str) -> str:
    """Load the appropriate system prompt file for the given visual style."""
    try:
        from styles import STYLES
        style = STYLES.get(style_key, STYLES["dark_fantasy"])
        prompt_file = style["system_prompt_file"]
    except (ImportError, KeyError):
        prompt_file = "system_prompt.txt"

    prompt_path = os.path.join(os.path.dirname(__file__), prompt_file)
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return load_system_prompt()   # fallback


def build_chunk1_message_woodcut(
    srt_text: str,
    block_start: int,
    block_end: int,
    total_blocks: int,
    mode: str,
) -> str:
    """Build Chunk 1 user message for Woodcut / Victorian styles.

    Unlike the dark-fantasy variant, this does NOT request a pre-analysis section —
    the LLM starts outputting Image Prompts immediately.
    """
    n_prompts   = block_end - block_start + 1
    ending_start = max(total_blocks - 4, block_start)

    section_note = (
        f"\nSECTION INFO for this story (total {total_blocks} blocks):\n"
        f"  Blocks 1-7      → HOOK section: epic dramatic opening, fill the entire frame.\n"
        f"  Blocks 8-{ending_start - 1} → STORY section: match narration, vary closeup/medium/wide.\n"
        f"  Blocks {ending_start}-{total_blocks} → ENDING section: symbolic legacy closing, wide shot.\n"
    )

    return (
        f"Generate Image Prompt {block_start} through Image Prompt {block_end}.\n"
        f"You MUST generate EXACTLY {n_prompts} prompts for this chunk.\n"
        f"First prompt: Image Prompt {block_start}\n"
        f"Last prompt: Image Prompt {block_end}\n"
        f"Do NOT merge blocks. Do NOT skip blocks. Do NOT add extra prompts.\n"
        f"Every subtitle block gets exactly ONE prompt — even single-word blocks.\n"
        f"\nSTYLE: Short description only — 60-72 words per prompt. "
        f"No style keywords. No pre-analysis. No headers.\n"
        f"Start your response directly with: Image Prompt {block_start}:\n"
        f"{section_note}"
        f"\nSRT blocks:\n{srt_text}"
    )


def build_continuation_chunk_message_woodcut(
    srt_text: str,
    chunk_number: int,
    total_chunks: int,
    block_start: int,
    block_end: int,
    character_cards: str,
    last_prompt: str,
    total_blocks: int,
    mode: str,
) -> str:
    """Build a continuation chunk message for Woodcut / Victorian styles."""
    n_prompts    = block_end - block_start + 1
    ending_start = max(total_blocks - 4, 1)

    section_note = (
        f"\nSECTION INFO (total story = {total_blocks} blocks):\n"
        f"  Blocks 1-7      → HOOK\n"
        f"  Blocks 8-{ending_start - 1} → STORY (match narration, vary shot types)\n"
        f"  Blocks {ending_start}-{total_blocks} → ENDING (symbolic, legacy, wide shot)\n"
    )

    cards_section = ""
    if character_cards and "No character cards" not in character_cards:
        cards_section = (
            f"\nKnown character descriptions (maintain visual consistency):\n"
            f"{character_cards}\n"
        )

    continuity = ""
    if last_prompt:
        continuity = (
            f"\nContinuity reference — last prompt from previous chunk:\n"
            f"{last_prompt}\n"
        )

    return (
        f"This is Chunk {chunk_number} of {total_chunks}.\n"
        f"Generate Image Prompt {block_start} through Image Prompt {block_end}.\n"
        f"You MUST generate EXACTLY {n_prompts} prompts for this chunk.\n"
        f"First prompt: Image Prompt {block_start}\n"
        f"Last prompt: Image Prompt {block_end}\n"
        f"Do NOT merge blocks. Do NOT skip blocks. Do NOT add extra prompts.\n"
        f"Every subtitle block gets exactly ONE prompt — even single-word blocks.\n"
        f"\nSTYLE: Short description only — 60-72 words per prompt. "
        f"No style keywords. Include a facial expression for every visible character.\n"
        f"{section_note}"
        f"{cards_section}"
        f"{continuity}"
        f"\nSRT blocks:\n{srt_text}"
    )


def build_chunk1_message_history4(chunk: list, total_blocks: int, mode: str) -> str:
    """Build Chunk 1 user message for History 4 — Ancient Fresco style.

    Includes per-block duration and EXACT word count target.
    Requests mandatory pre-analysis before prompts.
    chunk: list[SubtitleBlock]
    """
    from styles import get_word_count_for_duration

    n_prompts = chunk[-1].index - chunk[0].index + 1
    lines = [
        f"Generate Image Prompt {chunk[0].index} through Image Prompt {chunk[-1].index}.",
        f"Exactly {n_prompts} prompts.",
        "",
        "IMPORTANT — Chunk 1: You MUST output the full pre-analysis "
        "(Story Summary, Fresco Aesthetic Choice, Character Cards, Scene Location Map) "
        "BEFORE generating any prompts. Do NOT skip the pre-analysis.",
        "",
        "STRICT WORD COUNT RULE: Each prompt must be EXACTLY the word count shown "
        "for that block (based on its duration). Count your words before finalizing each prompt.",
        "",
        "SRT blocks with target word counts:",
        "",
    ]
    for block in chunk:
        dur = max(0.0, time_to_seconds(block.end_time) - time_to_seconds(block.start_time))
        wc  = get_word_count_for_duration(dur)
        lines.append(f"Block {block.index} ({dur:.1f}s → EXACTLY {wc} words):")
        lines.append(f"  {block.start_time} --> {block.end_time}")
        lines.append(f"  \"{block.text}\"")
        lines.append("")
    return "\n".join(lines)


def build_continuation_chunk_message_history4(
    chunk: list,
    chunk_number: int,
    total_chunks: int,
    character_cards: str,
    last_prompt: str,
    total_blocks: int,
    mode: str,
) -> str:
    """Build a continuation chunk message for History 4 — Ancient Fresco style.

    chunk: list[SubtitleBlock]
    """
    from styles import get_word_count_for_duration

    n_prompts = chunk[-1].index - chunk[0].index + 1
    lines = [
        f"This is Chunk {chunk_number} of {total_chunks}.",
        f"Generate Image Prompt {chunk[0].index} through Image Prompt {chunk[-1].index}.",
        f"Exactly {n_prompts} prompts.",
        "",
        "STRICT WORD COUNT RULE: Each prompt must be EXACTLY the word count shown. "
        "Count your words before finalizing each prompt.",
        "",
    ]
    if character_cards and "No character cards" not in character_cards:
        lines += [
            "Character descriptions (maintain consistency across all prompts):",
            character_cards,
            "",
        ]
    if last_prompt:
        lines += [
            "Continuity reference — last prompt from previous chunk:",
            last_prompt,
            "",
        ]
    lines.append("SRT blocks with target word counts:")
    lines.append("")
    for block in chunk:
        dur = max(0.0, time_to_seconds(block.end_time) - time_to_seconds(block.start_time))
        wc  = get_word_count_for_duration(dur)
        lines.append(f"Block {block.index} ({dur:.1f}s → EXACTLY {wc} words):")
        lines.append(f"  {block.start_time} --> {block.end_time}")
        lines.append(f"  \"{block.text}\"")
        lines.append("")
    return "\n".join(lines)
