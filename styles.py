"""Visual style definitions for the Mythology Prompt Generator."""

import re


STYLES = {
    "dark_fantasy": {
        "name": "Dark Fantasy Oil Painting",
        "prompt_mode": "full",
        "max_words": 300,
        "style_line": "Hyper-detailed dark fantasy digital painting, dramatic chiaroscuro lighting, rich oil painting textures, cinematic realism with painterly depth, warm amber and deep shadow tones, 16:9 aspect ratio.",
        "system_prompt_file": "system_prompt.txt",
        "append_style": False,
        "safety_replacements": False,
        "expression_rules": False,
        "section_instructions": False,
        "scene_colors": None,
    },

    "history_1": {
        "name": "History 1 — Museum Parchment",
        "prompt_mode": "full",
        "max_words": 250,
        "style_line": "Hand-painted oil illustration on aged rough parchment canvas, visible brush strokes, worn pigment, slight cracking and craquelure texture, matte finish, sepia warmth, smoky shadow edges, mild vignette, faint dust and grain overlay, faint manuscript border like a scanned museum artifact. Color palette: warm ochre #C9A46A, burnt umber #5E3A24, muted reds #8C4B32, faded olive green #7A6B44, golden dust #D8B87B. No text, no modern objects, no CGI, no neon, no futuristic lighting, 16:9 aspect ratio.",
        "system_prompt_file": "system_prompt_history1.txt",
        "append_style": False,
        "safety_replacements": False,
        "expression_rules": False,
        "section_instructions": False,
        "scene_colors": None,
    },

    "history_2": {
        "name": "History 2 — Documentary Dual Tone",
        "prompt_mode": "full",
        "max_words": 200,
        "style_line": "",   # No fixed style — LLM decides Color vs B&W per block
        "system_prompt_file": "system_prompt_history2.txt",
        "append_style": False,
        "safety_replacements": False,
        "expression_rules": False,
        "section_instructions": False,
        "scene_colors": None,
        "special_feature": "auto_color_bw",
    },

    "history_3": {
        "name": "History 3 — Impasto Mystical",
        "prompt_mode": "full",
        "max_words": 300,
        "style_line": "Classic impasto oil painting, thick visible swirling brushstrokes, highly textured canvas feel, painterly style, magical realism, dramatic Chiaroscuro, cinematic lighting, 16:9 aspect ratio.",
        "system_prompt_file": "system_prompt_history3.txt",
        "append_style": False,
        "safety_replacements": False,
        "expression_rules": False,
        "section_instructions": False,
        "scene_colors": None,
        "special_feature": "noor_rule",
    },

    "history_4": {
        "name": "History 4 — Ancient Fresco",
        "prompt_mode": "word_counted",
        "max_words": 44,
        "style_line": "Ancient fresco on aged cracked plaster wall, carved stone relief texture, illuminated manuscript aesthetic, aged pigment and subtle patina, deep midnight blues and muted gold and charcoal and ash-white palette, soft moonlight and torchlight only, calm mysterious reverent mood, 16:9 aspect ratio.",
        "system_prompt_file": "system_prompt_history4.txt",
        "append_style": False,
        "safety_replacements": False,
        "expression_rules": False,
        "section_instructions": False,
        "scene_colors": None,
        "special_feature": "duration_word_count",
        "word_count_map": {
            "0.0-2.9": 28,
            "3.0-4.9": 32,
            "5.0-6.9": 36,
            "7.0-9.9": 40,
            "10.0+":   44,
        },
    },

    "history_5": {
        "name": "History 5 — 2D Animated Storyboard",
        "prompt_mode": "full",
        "max_words": 250,
        "style_line": "Hand-drawn 2D animation-style digital illustration, clean ink outlines on foreground subjects, soft gradient shading, painterly simplified background with atmospheric haze, matte finish, mild vignette, subtle film grain and dust, cinematic storyboard composition, cool slate blue and deep blue-gray and mist gray and muted olive-brown and earth umber palette with warm fire orange and ember red accents, low contrast muted tones, no text no letters no symbols no watermarks, 16:9 aspect ratio.",
        "system_prompt_file": "system_prompt_history5.txt",
        "append_style": False,
        "safety_replacements": False,
        "expression_rules": False,
        "section_instructions": False,
        "scene_colors": None,
        "special_feature": "fire_accent_rule",
    },

    "woodcut": {
        "name": "Woodcut / Linocut",
        "prompt_mode": "short",
        "max_words": 72,
        "style_line": "woodcut linocut relief print illustration, bold thick black ink outlines flat color fills, NOT photorealistic NOT painting NOT crosshatching, chunky expressive line work, limited muted palette, cream sepia background, high contrast black ink and flat color, dramatic comic panel composition, exaggerated facial expressions, 16:9",
        "system_prompt_file": "system_prompt_woodcut.txt",
        "append_style": True,
        "safety_replacements": True,
        "expression_rules": True,
        "section_instructions": True,
        "scene_colors": {
            "battle":  "muted crimson red on banners and command figures",
            "fire":    "burnt sienna orange on flames only",
            "palace":  "flat ochre gold on throne and ornaments",
            "water":   "flat slate blue on water only",
            "army":    "muted crimson red on banners only",
            "forest":  "flat olive green on foliage only",
            "night":   "flat dark indigo on sky",
            "closeup": "monochrome black ink on cream parchment no color",
            "ending":  "warm ochre gold on key symbolic element only",
            "default": "muted crimson on flags burnt orange on fire",
        },
    },

    "victorian_engraving": {
        "name": "Victorian Engraving",
        "prompt_mode": "short",
        "max_words": 72,
        "style_line": "vintage 19th century newspaper engraving illustration, aged yellowed parchment background, heavy black ink crosshatching fine parallel line work, NOT painting NOT photorealistic, pen ink etching Victorian illustrated book aesthetic, dramatic cinematic composition, 16:9",
        "system_prompt_file": "system_prompt_woodcut.txt",   # same shorter prompt
        "append_style": True,
        "safety_replacements": True,
        "expression_rules": True,
        "section_instructions": True,
        "scene_colors": {
            "battle":  "selective deep crimson on battle flags dark gold on armor",
            "fire":    "selective burnt orange on flames and torches only",
            "palace":  "selective dark gold on crown and ornaments deep purple on drapery",
            "water":   "selective royal blue on water only",
            "army":    "selective deep crimson on standards and commander robes",
            "forest":  "selective forest green on foliage only",
            "night":   "selective royal blue on sky deep purple on shadows",
            "closeup": "pure black ink on sepia parchment no color maximum drama",
            "ending":  "selective dark gold on symbolic legacy element only",
            "default": "selective crimson on flags burnt orange on fire",
        },
    },
}


# ---------------------------------------------------------------------------
# Safety word replacements (Woodcut / Victorian)
# ---------------------------------------------------------------------------

SAFETY_REPLACEMENTS = [
    (r'\bfallen figures?\b',   'resting warriors'),
    (r'\bfallen bodies\b',     'scattered equipment'),
    (r'\bblood[\w\s-]*stained\b', 'battle-worn'),
    (r'\bcrimson blood\b',     'crimson war marks'),
    (r'\bblood drops?\b',      'red marks'),
    (r'\bblood\b',             'battle marks'),
    (r'\bbleeding\b',          'battle-worn'),
    (r'\bgore\b',              'battle chaos'),
    (r'\bslaughter\b',         'routing'),
    (r'\bkilling\b',           'defeating'),
    (r'\bmassacre\b',          'overwhelming defeat'),
    (r'\bdecapitat\w+',        'overpowering'),
    (r'\bsevered\b',           'dropped'),
    (r'\bmutilat\w+',          'battle-worn'),
    (r'\bwound\w*\b',          'battle-worn'),
    (r'\binjur\w+',            'battered'),
    (r'\bdying\b',             'defeated'),
    (r'\bdeath\b',             'defeat'),
    (r'\bdead bodies\b',       'scattered equipment'),
    (r'\bcorpses?\b',          'scattered soldiers'),
    (r'\bbodies\b',            'scattered figures'),
    (r'\bimpaled?\b',          'struck'),
    (r'\bstabb\w+',            'striking'),
    (r'\bbeheading\b',         'overwhelming force'),
    (r'\bexecut\w+',           'confronting'),
    (r'\btortur\w+',           'intense'),
    (r'\bbrutally\b',          'dramatically'),
    (r'\bbrutal\b',            'dramatic'),
]


# ---------------------------------------------------------------------------
# Expression rules (injected into continuation messages for short styles)
# ---------------------------------------------------------------------------

EXPRESSION_RULES = (
    "EXPRESSION RULE — always include one facial expression per character shown:\n"
    "Hero: jaw clenched determined / authoritative pointing calm eyes / proud slight smile chest forward\n"
    "Villain: cold sneer menacing head tilted / calculating barely-visible smile / furious teeth showing\n"
    "Enemy advance: fierce battle cry open mouth wild eyes\n"
    "Enemy retreat: wide fearful eyes hunched posture\n"
    "Army: confident arrogant chins raised / cold blank synchronized expressions\n"
)


# ---------------------------------------------------------------------------
# Section-specific instructions
# ---------------------------------------------------------------------------

SECTION_INSTRUCTIONS = {
    "hook":   "Epic opening: massive army aerial OR extreme face closeup fierce expression OR charging force. Show raw emotion. Fill entire frame.",
    "story":  "Match narration. Include character expression. Vary between: face closeup / medium action / wide establishing shots.",
    "ending": "Symbolic closing. Legacy moment. Hero: proud contemplative slight smile. Wide meaningful shot.",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def detect_scene_type(text: str) -> str:
    """Auto-detect scene type from text for color selection."""
    t = text.lower()
    if any(w in t for w in ['fire', 'burn', 'flame', 'torch', 'blaze', 'yangın', 'ateş']):
        return 'fire'
    if any(w in t for w in ['river', 'water', 'sea', 'ocean', 'lake', 'flood', 'nehir', 'su', 'deniz']):
        return 'water'
    if any(w in t for w in ['palace', 'throne', 'court', 'chamber', 'hall', 'saray', 'taht', 'divan']):
        return 'palace'
    if any(w in t for w in ['forest', 'tree', 'jungle', 'wood', 'orman', 'ağaç']):
        return 'forest'
    if any(w in t for w in ['night', 'dark', 'moon', 'star', 'midnight', 'gece', 'ay', 'karanlık']):
        return 'night'
    if any(w in t for w in ['end', 'final', 'legacy', 'last', 'triumph', 'fall', 'son', 'zafer']):
        return 'ending'
    if any(w in t for w in ['army', 'march', 'soldier', 'troop', 'formation', 'ordu', 'asker']):
        return 'army'
    if any(w in t for w in ['face', 'eye', 'look', 'gaze', 'express', 'yüz', 'göz', 'bak']):
        return 'closeup'
    return 'battle'


def get_scene_color(style_key: str, text: str) -> str:
    """Get the scene-specific color instruction for the given style."""
    style = STYLES.get(style_key, {})
    colors = style.get("scene_colors")
    if not colors:
        return ""
    scene_type = detect_scene_type(text)
    return colors.get(scene_type, colors.get("default", ""))


def apply_safety_replacements(text: str) -> str:
    """Replace unsafe words with safe alternatives."""
    for pattern, replacement in SAFETY_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def build_final_prompt(scene_description: str, style_key: str, subtitle_text: str = "") -> str:
    """Build the final prompt by appending style line + scene color if needed.

    For dark_fantasy / custom the LLM already wrote the full prompt — return as-is.
    For woodcut / victorian_engraving: apply safety replacements, trim to word
    limit, then append color + style line.
    """
    style = STYLES.get(style_key, STYLES["dark_fantasy"])

    if not style["append_style"]:
        return scene_description

    scene = scene_description.strip().rstrip(',').rstrip('.')

    # Apply safety replacements
    if style["safety_replacements"]:
        scene = apply_safety_replacements(scene)

    # Trim to max words, cutting at a natural break
    words = scene.split()
    max_w = style.get("max_words", 72)
    if len(words) > max_w:
        scene = ' '.join(words[:max_w])
        last_period = scene.rfind('.')
        last_comma  = scene.rfind(',')
        cut = max(last_period, last_comma)
        if cut > max_w * 3:
            scene = scene[:cut]

    # Scene-specific color accent
    color_str  = get_scene_color(style_key, subtitle_text or scene)
    style_line = style["style_line"]

    if color_str:
        return f"{scene}, {color_str}, {style_line}"
    return f"{scene}, {style_line}"


def get_section_type(block_index: int, total_blocks: int,
                     hook_count: int = 7, ending_count: int = 5) -> str:
    """Return 'hook', 'story', or 'ending' for a given block index (1-based)."""
    if block_index <= hook_count:
        return "hook"
    if block_index > total_blocks - ending_count:
        return "ending"
    return "story"


def get_section_instruction(section_type: str) -> str:
    """Return the section-specific prompt instruction string."""
    return SECTION_INSTRUCTIONS.get(section_type, SECTION_INSTRUCTIONS["story"])


# ---------------------------------------------------------------------------
# History 4 — duration-based word count helpers
# ---------------------------------------------------------------------------

def get_word_count_for_duration(duration_seconds: float) -> int:
    """Return the target word count for a History 4 prompt based on block duration."""
    if duration_seconds < 3.0:
        return 28
    elif duration_seconds < 5.0:
        return 32
    elif duration_seconds < 7.0:
        return 36
    elif duration_seconds < 10.0:
        return 40
    else:
        return 44


def detect_fire_accent_needed(subtitle_text: str, block_index: int, total_blocks: int) -> bool:
    """Detect if a scene needs mandatory fire/torch warm glow accent (History 5).

    Returns True if the scene is dusk, night, cold, outdoor, or emotionally somber.
    """
    text = subtitle_text.lower()

    fire_triggers = [
        'night', 'gece', 'dark', 'karanlık', 'dusk', 'dawn', 'evening', 'akşam',
        'moon', 'ay', 'star', 'yıldız', 'cold', 'soğuk', 'winter', 'kış',
        'camp', 'kamp', 'tent', 'çadır', 'fire', 'ateş', 'torch', 'meşale',
        'battle', 'savaş', 'war', 'siege', 'kuşatma', 'death', 'ölüm',
        'defeat', 'yenilgi', 'mourn', 'yas', 'grave', 'mezar', 'ruin', 'harabe',
        'storm', 'fırtına', 'rain', 'yağmur', 'shadow', 'gölge',
        'prison', 'hapishane', 'dungeon', 'zindan', 'cave', 'mağara',
        'march', 'yürüyüş', 'retreat', 'geri çekilme',
    ]

    if any(trigger in text for trigger in fire_triggers):
        return True

    # Ending blocks often benefit from fire accent
    if block_index >= total_blocks - 5:
        return True

    return False


def calculate_block_duration(start_time: str, end_time: str) -> float:
    """Calculate the duration (seconds) of an SRT block from its time strings.

    Accepts both comma-separated and dot-separated milliseconds:
        "00:01:23,456"  or  "00:01:23.456"
    """
    def _parse(t: str) -> float:
        t = t.replace(',', '.').strip()
        parts = t.split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])

    return max(0.0, _parse(end_time) - _parse(start_time))
