"""LLM-based story structure analyzer.

Two public entry points:
  run_story_analysis()          — smart chunking: identifies natural scene breaks (sync)
  run_master_plan_analysis_async() — full-story Master Plan analysis (async, called
                                     from inside _async_generation background thread)

run_story_analysis() returns a 3-tuple: (break_points | None, error_msg, method)
  method = "api"   — result came from the LLM
  method = "local" — LLM failed, result came from local heuristic
  method = None    — complete failure
"""

import asyncio
import hashlib
import json
import re
import sys

import aiohttp

API_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = (
    "You are a story structure analyzer. "
    "Your only job is to identify scene breaks in SRT subtitle files. "
    "Output ONLY a valid JSON array of integers. No explanation. No other text."
)


# ─────────────────────────────────────────────────────────────────────────────
# SRT COMPRESSION  (25 KB → ~3 KB)
# ─────────────────────────────────────────────────────────────────────────────

def _compress_srt(srt_text: str) -> str:
    """Convert full SRT to compact 'block_num: first 10 words' lines."""
    lines = []
    for raw in re.split(r'\n\s*\n', srt_text.strip()):
        parts = raw.strip().split('\n')
        if len(parts) < 3:
            continue
        try:
            block_num = int(parts[0].strip())
        except ValueError:
            continue
        words = ' '.join(parts[2:]).split()
        lines.append(f"{block_num}: {' '.join(words[:10])}")
    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# ROBUST JSON ARRAY EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json_array(text: str | None) -> list[int] | None:
    """Find the first [integer, …] array in any response format."""
    if not text:
        return None
    try:
        match = re.search(r'\[[\d,\s]+\]', str(text), re.DOTALL)
        if not match:
            return None
        arr = json.loads(match.group())
        result = sorted({int(x) for x in arr if isinstance(x, (int, float))})
        return result if result else None
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# LOCAL HEURISTIC FALLBACK  (no API needed)
# ─────────────────────────────────────────────────────────────────────────────

def _local_heuristic_breaks(srt_text: str, target_chunk: int) -> list[int]:
    """Two-signal offline break detector:

    Signal 1 — Large timestamp gaps (top 20 % of all inter-block gaps).
    Signal 2 — Blocks that mention years / dates (1000–2099), which in
               historical content usually mark new events or eras.

    Both signals are combined; the result is then filtered so every segment
    is at least 10 blocks long.  Mandatory break every target_chunk blocks
    ensures no segment grows too large either.
    """
    _TIME_RE = re.compile(
        r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*'
        r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})'
    )
    _DATE_RE = re.compile(r'\b(1[0-9]{3}|20[0-9]{2})\b')

    blocks_data = []
    for raw in re.split(r'\n\s*\n', srt_text.strip()):
        parts = raw.strip().split('\n')
        if len(parts) < 3:
            continue
        try:
            block_num = int(parts[0].strip())
        except ValueError:
            continue
        m = _TIME_RE.match(parts[1].strip())
        if not m:
            continue
        def _ms(h, mi, s, ms):
            return (int(h) * 3600 + int(mi) * 60 + int(s)) * 1000 + int(ms)
        start_ms = _ms(*m.group(1, 2, 3, 4))
        end_ms   = _ms(*m.group(5, 6, 7, 8))
        text = ' '.join(parts[2:])
        blocks_data.append({
            'num': block_num, 'start': start_ms, 'end': end_ms,
            'has_date': bool(_DATE_RE.search(text)),
        })

    if not blocks_data:
        return [1]

    n = len(blocks_data)

    # Signal 1: top-20 % gaps
    gaps = [
        (blocks_data[i]['start'] - blocks_data[i - 1]['end'], i)
        for i in range(1, n)
    ]
    gaps.sort(reverse=True)
    top_gap_positions = {pos for _, pos in gaps[:max(1, n // 5)]}

    # Signal 2: date/year positions
    date_positions = {i for i, b in enumerate(blocks_data) if b['has_date']}

    # Mandatory grid every target_chunk blocks
    grid_positions = set(range(0, n, target_chunk))

    candidates = sorted(top_gap_positions | date_positions | grid_positions)

    # Always start at 0
    if not candidates or candidates[0] != 0:
        candidates = [0] + candidates

    # Convert positions → block numbers
    raw_break_nums = [blocks_data[i]['num'] for i in candidates if i < n]

    # Filter: minimum 10 blocks between breaks
    MIN_SEG = 10
    filtered = [raw_break_nums[0]]
    for bn in raw_break_nums[1:]:
        pos_new  = next((i for i, b in enumerate(blocks_data) if b['num'] == bn), None)
        pos_prev = next((i for i, b in enumerate(blocks_data) if b['num'] == filtered[-1]), None)
        if pos_new is not None and pos_prev is not None and (pos_new - pos_prev) >= MIN_SEG:
            filtered.append(bn)

    return filtered


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE API ATTEMPT
# ─────────────────────────────────────────────────────────────────────────────

async def _single_api_call(
    api_key: str, model: str, compressed: str, target_chunk: int
) -> tuple[list[int] | None, str, bool]:
    """One HTTP attempt.  Returns (points | None, error_msg, is_rate_limit)."""
    user_msg = (
        f"Below is a compressed SRT — each line: BLOCK_NUMBER: first 10 words of subtitle.\n\n"
        f"Identify every block number where a new SCENE, TOPIC, LOCATION, or NARRATIVE PHASE begins.\n\n"
        f"Rules:\n"
        f"- Each segment should be roughly {target_chunk} blocks (±10 is fine).\n"
        f"- Break only at NATURAL transitions — never mid-sentence.\n"
        f"- The first number must always be 1.\n"
        f"- Output ONLY a JSON array, e.g.: [1, 18, 35, 52, 70]\n\n"
        f"Compressed SRT:\n{compressed}"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 400,
        "temperature": 0.1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:

                if resp.status == 429:
                    return None, "Rate limited (429).", True
                if resp.status == 401:
                    return None, "Invalid API key (401).", False
                if resp.status != 200:
                    body = await resp.text()
                    return None, f"API error {resp.status}: {body[:200]}", False

                try:
                    data = await resp.json()
                except Exception as e:
                    return None, f"Failed to parse API response: {e}", False

                try:
                    raw = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    return None, f"Unexpected response structure: {e} | {str(data)[:150]}", False

                if raw is None:
                    return None, "API returned null content.", False

                raw = str(raw).strip()
                if not raw:
                    return None, "API returned empty content.", False

                points = _extract_json_array(raw)
                if points is None:
                    return None, f"No JSON array found. Got: {raw[:150]}", False

                return points, "", False

    except asyncio.TimeoutError:
        return None, "Request timed out (120 s).", False
    except Exception as e:
        return None, f"Unexpected error: {e}", False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ASYNC ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

async def _analyze_async(
    api_key: str,
    model: str,
    srt_text: str,
    target_chunk: int,
    status_cb=None,
    max_retries: int = 3,
) -> tuple[list[int] | None, str, str | None]:
    """Returns (points | None, error_msg, method).
    method = "api" | "local" | None
    """
    compressed = _compress_srt(srt_text)

    # ── 5 s cooldown before hitting the API ──────────────────────────────────
    if status_cb:
        status_cb("⏳ Waiting 5s to avoid rate limits…")
    await asyncio.sleep(5)

    # ── API call with retry on 429 ────────────────────────────────────────────
    last_error = "Unknown error."
    for attempt in range(max_retries):
        if status_cb:
            label = (
                f"🧠 Analyzing… (attempt {attempt + 1}/{max_retries})"
                if attempt == 0
                else f"🔄 Retrying… (attempt {attempt + 1}/{max_retries})"
            )
            status_cb(label)

        points, err, is_rate_limit = await _single_api_call(
            api_key, model, compressed, target_chunk
        )

        if points is not None:
            return points, "", "api"

        last_error = err

        if is_rate_limit and attempt < max_retries - 1:
            wait = 30 * (attempt + 1)
            if status_cb:
                status_cb(
                    f"⚠️ Rate limited — retrying in {wait}s… "
                    f"(attempt {attempt + 2}/{max_retries})"
                )
            await asyncio.sleep(wait)
            continue

        # Non-rate-limit error or last attempt — stop retrying
        break

    # ── Local heuristic fallback ──────────────────────────────────────────────
    if status_cb:
        status_cb("🔧 API failed — using local heuristic as fallback…")

    try:
        local_points = _local_heuristic_breaks(srt_text, target_chunk)
        if local_points:
            return local_points, last_error, "local"
    except Exception as e:
        last_error = f"{last_error} | Local heuristic error: {e}"

    return None, last_error, None


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC SYNC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_story_analysis(
    api_key: str,
    model: str,
    srt_text: str,
    target_chunk: int,
    status_callback=None,
) -> tuple[list[int] | None, str, str | None]:
    """Synchronous entry point.

    Returns (break_points, error_msg, method):
      break_points — list of block numbers where new chunks start, or None
      error_msg    — human-readable failure reason (empty string on full success)
      method       — "api" | "local" | None

    status_callback(msg: str) is called with progress updates if provided.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            _analyze_async(api_key, model, srt_text, target_chunk, status_callback)
        )
    except Exception as e:
        return None, f"Event loop error: {e}", None
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# MASTER STORY PLAN ANALYSIS
# Produces a full narrative plan that every chunk receives for visual consistency
# ─────────────────────────────────────────────────────────────────────────────

_MASTER_PLAN_SYSTEM = """\
You are a cinematic story analyst for a visual documentary production team.
Analyze the provided compressed SRT subtitle blocks and produce a MASTER STORY PLAN.
This plan will be given to every image-prompt writer so all chunks have the same
visual identity, mood, and location logic.

Output ONLY this structured format — no markdown, no extra text:

STORY SUMMARY:
[5-8 sentence summary of the complete narrative arc and emotional journey]

NARRATIVE PHASES:
Phase 1: Blocks X-Y — [phase name] — [visual mood: dark/warm/somber/triumphant/mystical/etc]
Phase 2: Blocks X-Y — [phase name] — [visual mood]
[continue for every phase]

CHARACTER REGISTRY:
[NAME]: [age, build, ethnicity/features, clothing, weapons/props, expression tendencies]
[continue for every named character]

SCENE LOCATION MAP:
Blocks X-Y: [location name] — [geographic region, e.g. Central European castle, Arabian desert, Byzantine Constantinople] — [era-accurate visual details]
[continue for every location change]

VISUAL MOOD PROGRESSION:
Blocks X-Y: [dominant color palette] — [lighting type] — [emotional tone]
[continue showing how visual feel evolves]

CRITICAL TRANSITIONS:
Block X to Block Y: [what changes visually — location/mood/character/lighting]
[only for major visual shifts]
"""


def compress_srt_blocks_for_analysis(blocks: list) -> str:
    """Compress SubtitleBlock list to 'N: first 15 words...' lines for master plan API call.

    Reduces a 25 KB SRT to ~3-4 KB while preserving the full narrative arc.
    """
    lines = []
    for b in blocks:
        words = b.text.split()
        short_text = " ".join(words[:15])
        if len(words) > 15:
            short_text += "..."
        lines.append(f"{b.index}: {short_text}")
    return "\n".join(lines)


def get_srt_blocks_hash(blocks: list) -> str:
    """Return an MD5 hash of the SRT content for caching master plans."""
    content = "".join(b.text for b in blocks)
    return hashlib.md5(content.encode()).hexdigest()


async def _master_plan_api_call(
    api_key: str, model: str, compressed_srt: str, total_blocks: int
) -> tuple[str | None, str, bool]:
    """Single API call for master plan. Returns (content | None, error_msg, is_rate_limit)."""
    user_msg = (
        f"Analyze this complete story with {total_blocks} subtitle blocks.\n"
        f"Create the Master Story Plan exactly as specified in your instructions.\n\n"
        f"COMPRESSED SRT (block number: first 15 words):\n\n{compressed_srt}"
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _MASTER_PLAN_SYSTEM},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": 3000,
        "temperature": 0.25,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if resp.status == 429:
                    return None, "Rate limited (429).", True
                if resp.status == 401:
                    return None, "Invalid API key (401).", False
                if resp.status != 200:
                    body = await resp.text()
                    return None, f"API error {resp.status}: {body[:200]}", False
                try:
                    data    = await resp.json()
                    content = data["choices"][0]["message"]["content"]
                except Exception as e:
                    return None, f"Response parse error: {e}", False
                if content and len(content.strip()) > 80:
                    return content.strip(), "", False
                return None, "Response too short to be a valid Master Plan.", False
    except asyncio.TimeoutError:
        return None, "Request timed out (180 s).", False
    except Exception as exc:
        return None, f"Connection error: {exc}", False


async def run_master_plan_analysis_async(
    api_key: str,
    model: str,
    compressed_srt: str,
    total_blocks: int,
    max_retries: int = 2,
) -> str | None:
    """Async full-story master plan analysis with retry on 429.

    Called directly with 'await' from inside _async_generation.
    Returns the master plan string, or None if all attempts fail.
    """
    for attempt in range(max_retries + 1):
        content, err, is_rate_limit = await _master_plan_api_call(
            api_key, model, compressed_srt, total_blocks
        )
        if content:
            return content
        if is_rate_limit and attempt < max_retries:
            wait = 20 * (attempt + 1)
            await asyncio.sleep(wait)
            continue
        if not is_rate_limit:
            break   # non-recoverable error — stop retrying
    return None
