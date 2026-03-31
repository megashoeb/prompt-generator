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
    (r'\bfallen figures?\b',      'fallen warriors'),
    (r'\bfallen bodies\b',        'fallen soldiers'),
    (r'\bblood[\w\s-]*stained\b', 'battle-worn'),
    (r'\bcrimson blood\b',        'crimson stain'),
    (r'\bblood drops?\b',         'crimson drops'),
    (r'\bbloodied\b',             'battle-worn'),
    (r'\bbloody\b',               'crimson-stained'),
    (r'\bbloodied\b',             'battle-worn'),
    (r'\bbloodsh\w+\b',           'devastation'),
    (r'\bbloodbath\b',            'carnage'),
    (r'\bblood\b',                'crimson stain'),
    (r'\bbleeding\b',             'wounded'),
    (r'\bgore\b',                 'aftermath'),
    (r'\bslaughter\b',            'routing'),
    (r'\bkilling\b',              'defeating'),
    (r'\bmassacre\b',             'overwhelming defeat'),
    (r'\bdecapitat\w+',           'overpowering'),
    (r'\bsevered\b',              'dropped'),
    (r'\bmutilat\w+',             'battle-worn'),
    (r'\bwound\w*\b',             'battle-worn'),
    (r'\binjur\w+',               'battered'),
    (r'\bdying\b',                'defeated'),
    (r'\bdeath\b',                'defeat'),
    (r'\bdead bodies\b',          'fallen soldiers'),
    (r'\bcorpses?\b',             'fallen soldiers'),
    (r'\bbodies\b',               'scattered figures'),
    (r'\bimpaled?\b',             'struck'),
    (r'\bstabb\w+',               'striking'),
    (r'\bbeheading\b',            'overwhelming force'),
    (r'\bexecut\w+',              'sentencing'),
    (r'\bexecuted\b',             'slain'),
    (r'\btortur\w+',              'intense'),
    (r'\bbrutally\b',             'dramatically'),
    (r'\bbrutal\b',               'dramatic'),
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


# ─────────────────────────────────────────────────────────────────────────────
# VIDEO PROMPT TEMPLATES — style-specific motion language for Mode B
# ─────────────────────────────────────────────────────────────────────────────

VIDEO_PROMPT_TEMPLATES = {
    "dark_fantasy": {
        "motion_style": "Cinematic oil painting animation",
        "camera_moves": [
            "Slow cinematic push forward through dark atmospheric haze",
            "Gentle dolly zoom emphasizing the subject against deep shadows",
            "Slow pan across the scene revealing dramatic chiaroscuro details",
            "Static frame with volumetric fog drifting and torch flames flickering",
            "Slow upward crane revealing the full scale of the environment",
            "Subtle parallax drift separating foreground from background layers",
        ],
        "atmosphere_motion": [
            "torch flames flicker casting dancing amber shadows",
            "volumetric fog drifts slowly through the scene",
            "dust particles float in shafts of golden light",
            "fabric and cloaks sway gently in wind",
            "smoke wisps curl upward from embers",
            "storm clouds churn slowly in the dark sky",
        ],
        "style_suffix": "painterly oil texture maintained throughout motion, dramatic lighting shifts, cinematic depth of field, 16:9",
    },

    "history_1": {
        "motion_style": "Animated museum parchment painting",
        "camera_moves": [
            "Gentle pan across the aged parchment surface as if scanning a museum artifact",
            "Slow zoom into the central subject revealing brush texture and craquelure cracks",
            "Subtle drift across the canvas as if the viewer moves closer to examine details",
            "Static frame with faint dust particles floating across the aged surface",
            "Slow pull back revealing the full composition like stepping away from a painting",
            "Gentle downward tilt as if unrolling an ancient scroll",
        ],
        "atmosphere_motion": [
            "faint dust motes drift across the aged parchment surface",
            "subtle candlelight flicker illuminates worn pigment details",
            "a gentle warmth seems to emanate from the golden ochre tones",
            "craquelure cracks seem to deepen slightly as light shifts",
            "torch glow pulses softly on the ancient canvas texture",
            "a faint sepia warmth washes slowly across the scene",
        ],
        "style_suffix": "museum parchment texture preserved, warm ochre and burnt umber tones, aged artifact feel, 16:9",
    },

    "history_2": {
        "motion_style": "Documentary cinematic transition",
        "camera_moves": [
            "Slow cinematic push with shallow depth of field rack focus",
            "Gentle pan across the scene with documentary steadicam feel",
            "Static frame with subtle subject breathing and eye movement",
            "Slow zoom into subject face with soft focus background drift",
            "Wide establishing drift revealing the full environment",
        ],
        "atmosphere_motion_color": [
            "candlelight glow pulses softly on golden skin tones",
            "oil-paint texture seems to shift slightly with warm light",
            "fabric folds catch moving light creating gentle shadow play",
            "warm amber highlights slowly intensify then fade",
            "gentle dust in candlelight drifts through the scholarly space",
        ],
        "atmosphere_motion_bw": [
            "charcoal grain texture subtly shifts like aged film stock",
            "deep monochrome shadows pulse slowly with vintage film flicker",
            "chalk-line edges seem to vibrate with archival film grain",
            "grayscale tones shift between deep black and soft gray",
            "dust and grain overlay drifts across the vintage photograph feel",
        ],
        "style_suffix_color": "oil-paint realism motion, golden candlelight, documentary pace, 16:9",
        "style_suffix_bw": "vintage monochrome film motion, archival grain, haunting stillness, 16:9",
    },

    "history_3": {
        "motion_style": "Mystical impasto painting animation",
        "camera_moves": [
            "Slow zoom into thick swirling brushstrokes as if diving into the painting",
            "Gentle drift across the canvas revealing impasto texture depth",
            "Slow push through atmospheric magical haze toward the subject",
            "Static frame with divine light rays slowly shifting angle",
            "Slow upward pan following rising smoke or light toward lapis lazuli sky",
        ],
        "atmosphere_motion": [
            "thick impasto brushstrokes seem to shimmer as light crosses them",
            "magical atmospheric haze drifts slowly with ethereal particles",
            "divine golden light beams shift slowly across the scene",
            "ember glow pulses deep within the canvas texture",
            "starry lapis lazuli sky twinkles subtly through painted clouds",
        ],
        "atmosphere_motion_noor": [
            "blinding golden Noor light pulses and radiates outward with divine intensity",
            "surrounding figures sway gently, shielding eyes from the growing luminance",
            "ethereal golden particles spiral slowly around the sacred light source",
            "the divine glow intensifies then softens in a breathing rhythm",
        ],
        "style_suffix": "impasto oil texture maintained, thick brushstroke depth visible in motion, magical realism, 16:9",
    },

    "history_4": {
        "motion_style": "Ancient fresco subtle animation",
        "camera_moves": [
            "Very slow static zoom into carved stone relief details",
            "Gentle horizontal pan across the fresco wall surface",
            "Subtle drift as if torchlight moves past the ancient wall painting",
            "Nearly static frame with only ambient particle movement",
            "Slow pull revealing more of the illuminated manuscript page",
        ],
        "atmosphere_motion": [
            "faint dust particles drift across the cracked plaster surface",
            "torchlight flicker causes painted shadows to dance on stone",
            "subtle moonlight shifts across the aged fresco pigments",
            "candlelight glow slowly pulses on muted gold leaf details",
            "ancient plaster surface seems to breathe with age",
        ],
        "style_suffix": "ancient fresco stillness maintained, minimal motion, cracked plaster texture, midnight blue and muted gold, 16:9",
    },

    "history_5": {
        "motion_style": "2D animated storyboard gentle motion",
        "camera_moves": [
            "Gentle parallax drift separating ink-outlined foreground from painterly background",
            "Slow pan across the 2D illustrated landscape with atmospheric haze layers moving",
            "Subtle zoom toward the hand-drawn character with background softening",
            "Static frame with foreground character subtle breathing animation",
            "Gentle upward drift following ember sparks rising from campfire",
        ],
        "atmosphere_motion": [
            "campfire embers drift upward through thin smoke haze in painterly motion",
            "torch glow flickers softly casting animated warm shadows on ink-outlined faces",
            "atmospheric haze layers shift at different speeds creating depth",
            "hair and cloth sway gently with illustrated wind effect",
            "film grain and dust particles float across the matte finish surface",
        ],
        "atmosphere_motion_no_fire": [
            "diffused daylight shifts subtly across the painted background",
            "atmospheric haze in the distance drifts slowly with depth",
            "subtle film grain overlay animates across the matte surface",
            "cloth and fabric details sway in gentle ambient breeze",
        ],
        "style_suffix": "hand-drawn 2D animation motion, clean ink outlines maintained, painterly background layers, matte finish, 16:9",
    },

    "woodcut": {
        "motion_style": "Animated woodcut print reveal",
        "camera_moves": [
            "Slow reveal as if ink is being pressed onto paper from left to right",
            "Gentle zoom into bold black ink outlines revealing flat color underneath",
            "Static frame with subtle paper texture movement beneath the print",
            "Slow horizontal pan across the woodcut scene like scanning a print",
            "Gentle pull back revealing the full woodcut composition on cream paper",
        ],
        "atmosphere_motion": [
            "bold ink outlines seem to settle onto the cream paper surface",
            "flat color fills pulse subtly beneath thick black outlines",
            "paper texture grain shifts as if the print is being examined closely",
            "ink seems to bleed slightly at edges with organic movement",
            "cream sepia background texture breathes with subtle warmth",
        ],
        "style_suffix": "woodcut print animation, bold outlines maintained, flat color fills, cream paper texture, 16:9",
    },

    "victorian_engraving": {
        "motion_style": "Animated Victorian engraving illustration",
        "camera_moves": [
            "Slow reveal as if crosshatch lines are being drawn stroke by stroke",
            "Gentle zoom into fine parallel line work revealing engraving detail",
            "Static frame with subtle aged parchment movement beneath the illustration",
            "Slow pan across the Victorian illustration like reading a newspaper",
            "Gentle pull back from close detail to full engraving composition",
        ],
        "atmosphere_motion": [
            "fine crosshatch lines seem to deepen and lighten with shifting light",
            "aged yellowed parchment texture breathes subtly beneath the ink",
            "selective color accents (crimson, gold) pulse softly within the monochrome",
            "pen ink etching lines appear to sharpen and soften organically",
            "shadows in the engraving deepen and release with atmospheric rhythm",
        ],
        "style_suffix": "Victorian engraving animation, crosshatch texture maintained, aged parchment feel, selective color, 16:9",
    },
}


def get_video_style_suffix(style_key: str, prompt_text: str = "") -> str:
    """Return the video style suffix for a given style.

    For History 2, checks if the prompt is Color or B&W to pick the right suffix.
    """
    tpl = VIDEO_PROMPT_TEMPLATES.get(style_key)
    if not tpl:
        return "cinematic motion, 16:9"
    if style_key == "history_2":
        t = prompt_text.lower()
        is_bw = any(kw in t for kw in ("monochrome", "charcoal sketch", "grayscale", "black and white", "chalk-line"))
        return tpl["style_suffix_bw"] if is_bw else tpl["style_suffix_color"]
    return tpl.get("style_suffix", "cinematic motion, 16:9")
