"""Mythology Prompt Generator — Streamlit Web App (v3)
Threading-based architecture: generation runs in a background thread,
main Streamlit thread polls every 0.5 s for live updates.
"""

import asyncio
import base64
import math
import re
import sys
import threading
import time
from contextlib import nullcontext

import streamlit as st
import streamlit.components.v1 as components

from srt_parser import parse_srt, auto_chunk, smart_chunk_by_breaks, format_chunk_for_api, block_duration, decode_srt_bytes, fix_mojibake
from api_client import send_chunk_sync_streaming, process_chunks_queue, validate_api_keys_sync
from prompt_engine import (
    load_system_prompt,
    load_system_prompt_short,
    load_system_prompt_for_style,
    build_chunk1_message,
    build_chunk1_message_woodcut,
    build_chunk1_message_history4,
    build_continuation_chunk_message,
    build_continuation_chunk_message_woodcut,
    build_continuation_chunk_message_history4,
    extract_character_cards,
    extract_last_prompt,
    extract_all_prompts,
    infer_scene_context,
)
from styles import get_word_count_for_duration
from output_writer import export_txt, export_xlsx, process_prompt_with_style, count_color_bw, count_noor_prompts, count_fire_accent_prompts, validate_prompt_count
from story_analyzer import (
    run_story_analysis,
    run_master_plan_analysis_async,
    compress_srt_blocks_for_analysis,
    get_srt_blocks_hash,
)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Prompt Generator by MegaShoeb",
    page_icon="🎬",
    layout="wide",
)
st.markdown(
    """
    <style>
    .chunk-card { border-radius:10px; padding:12px 10px; text-align:center;
                  min-height:120px; margin-bottom:4px; }
    .section-title { font-size:18px; font-weight:700; margin:20px 0 8px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}m {s % 60:02d}s"


def calc_est(chunks: list, max_par: int) -> float:
    c1 = (len(chunks[0]) * 350) / 38
    if len(chunks) <= 1:
        return c1
    cont = chunks[1:]
    rounds = math.ceil(len(cont) / max_par)
    avg = sum(len(c) for c in cont) / len(cont)
    return c1 + rounds * (avg * 350 / 38)


def check_visual_consistency(prompts_dict: dict, master_plan: str) -> list[str]:
    """Flag prompts that may break visual consistency based on the Master Story Plan.

    Returns a list of warning strings (empty list = no issues found).
    """
    if not master_plan or not prompts_dict:
        return []

    warnings = []
    european_blocks: set[int] = set()
    desert_blocks:   set[int] = set()

    for line in master_plan.split("\n"):
        ll = line.lower()
        m  = re.search(r'blocks?\s*(\d+)\s*[-–to]+\s*(\d+)', ll)
        if not m:
            continue
        start, end = int(m.group(1)), int(m.group(2))
        block_range = set(range(start, end + 1))
        if any(w in ll for w in ("european", "hungarian", "castle", "gothic", "balkan",
                                  "central europe", "eastern europe", "byzantine")):
            european_blocks.update(block_range)
        if any(w in ll for w in ("desert", "arabian", "sahara", "bedouin", "sand dune")):
            desert_blocks.update(block_range)

    for num, prompt in prompts_dict.items():
        pl = prompt.lower()
        if num in european_blocks:
            if any(w in pl for w in ("desert", "sand dune", "arabian desert", "oasis", "camel caravan")):
                warnings.append(
                    f"Block {num}: Master Plan says European setting, "
                    f"but prompt contains desert imagery."
                )
        if num in desert_blocks:
            if any(w in pl for w in ("gothic castle", "stone castle", "european countryside",
                                      "central european plains")):
                warnings.append(
                    f"Block {num}: Master Plan says desert/Arabian setting, "
                    f"but prompt contains European castle imagery."
                )

    return warnings


def copy_btn(text: str, label: str = "📋 Copy All Prompts", height: int = 52):
    b64 = base64.b64encode(text.encode("utf-8")).decode()
    lbl_js = label.replace("'", "\\'")
    components.html(
        f"""<button id="cb" onclick="
            const t=atob('{b64}');
            navigator.clipboard.writeText(t)
              .then(()=>{{document.getElementById('cb').innerText='✅ Copied!';
                          setTimeout(()=>document.getElementById('cb').innerText='{lbl_js}',3000);}})
              .catch(()=>{{const a=document.createElement('textarea');a.value=t;
                           document.body.appendChild(a);a.select();
                           document.execCommand('copy');document.body.removeChild(a);
                           document.getElementById('cb').innerText='✅ Copied!';}});
        " style="padding:10px 20px;font-size:14px;font-weight:700;background:#ff4b4b;
                 color:white;border:none;border-radius:8px;cursor:pointer;width:100%;"
        >{label}</button>""",
        height=height,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHUNK STATUS CARD RENDERER
# ─────────────────────────────────────────────────────────────────────────────

def _card_html(chunk_id: int, s: dict) -> str:
    status = s.get("status", "queued")
    pct = s.get("pct", 0)

    cfg = {
        "queued":     ("#FFC107", "rgba(255,193,7,0.08)",   "🟡", "Queued",     "Waiting for slot…"),
        "processing": ("#2196F3", "rgba(33,150,243,0.10)",  "🔵", "Running",    ""),
        "progress":   ("#2196F3", "rgba(33,150,243,0.10)",  "🔵", "Running",    ""),
        "done":       ("#4CAF50", "rgba(76,175,80,0.15)",   "🟢", "Done",       ""),
        "error":      ("#F44336", "rgba(244,67,54,0.10)",   "🔴", "Error",      ""),
        "stopped":    ("#888",    "rgba(120,120,120,0.10)", "⏹️", "Stopped",    "Cancelled"),
        "retrying":   ("#FF9800", "rgba(255,152,0,0.10)",   "🟠", "Retrying",   ""),
    }
    color, bg, icon, label, default_detail = cfg.get(
        status, ("#888", "#111", "❓", status, "")
    )

    # Build detail line
    key_label = s.get("key_label", "")
    key_sfx   = f" · {key_label}" if key_label else ""

    if status == "processing":
        done = s.get("prompts_done", 0)
        exp  = s.get("expected", "?")
        detail = f"{done}/{exp} prompts{key_sfx}"
    elif status == "done":
        detail = f"{s.get('prompts_done', '?')} prompts · {fmt(s.get('elapsed', 0))}{key_sfx}"
    elif status == "queued":
        detail = f"Waiting…{key_sfx}"
    elif status == "error":
        detail = (s.get("error_msg", "") or "")[:45]
    elif status == "retrying":
        detail = (s.get("retry_msg", "") or "")[:45]
    elif status == "stopped":
        detail = "Cancelled"
    else:
        detail = default_detail

    bar = (
        f'<div style="background:#333;border-radius:4px;height:6px;margin-top:8px;">'
        f'<div style="background:{color};border-radius:4px;height:6px;width:{pct}%;"></div>'
        f'</div>'
    )
    return (
        f'<div class="chunk-card" style="background:{bg};border:1px solid {color};">'
        f"<b>Chunk {chunk_id}</b><br>{icon} {label}<br>"
        f'<span style="font-size:12px;color:#ccc">{detail}</span>'
        f"{bar}</div>"
    )


def render_chunk_grid(chunk_statuses: dict, cols_per_row: int = 4):
    """Render all chunk cards in a responsive grid."""
    ids = sorted(chunk_statuses.keys())
    for row_start in range(0, len(ids), cols_per_row):
        row_ids = ids[row_start : row_start + cols_per_row]
        cols = st.columns(len(row_ids))
        for col, cid in zip(cols, row_ids):
            with col:
                st.markdown(_card_html(cid, chunk_statuses[cid]), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND GENERATION THREAD
# ─────────────────────────────────────────────────────────────────────────────

def _generation_thread(gen_state: dict) -> None:
    """Runs entirely in a background thread. Updates gen_state in-place."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_async_generation(gen_state))
    except Exception as exc:
        gen_state["fatal_error"] = str(exc)
    finally:
        gen_state["end_time"] = time.time()
        gen_state["done"] = True
        loop.close()


async def _async_generation(gen_state: dict) -> None:
    """Main async orchestration — step 0: story analysis, then chunk 1, then parallel chunks."""
    api_keys       = gen_state["api_keys"]
    model          = gen_state["model"]
    chunks         = gen_state["chunks"]
    mode_code      = gen_state["mode_code"]
    max_parallel   = gen_state["max_parallel"]
    visual_style   = gen_state.get("visual_style", "dark_fantasy")
    custom_style   = gen_state.get("custom_style_text", "")

    # _is_short_style: Woodcut / Victorian (and history_1/2/3) use their own system
    # prompt files loaded via load_system_prompt_for_style.
    # _is_history4: History 4 — word-counted prompts, uses its own message builders.
    _is_history4    = visual_style == "history_4"
    _is_short_style = visual_style not in ("dark_fantasy", "custom") and not _is_history4

    if visual_style in ("dark_fantasy", "custom"):
        sys_full  = load_system_prompt()
        sys_short = load_system_prompt_short()
    else:
        sys_full  = load_system_prompt_for_style(visual_style)
        sys_short = sys_full   # same file for all chunks

    # ── STEP 0: MASTER STORY PLAN ANALYSIS ───────────────────────────────────
    # Run once before any chunks. Produces a plan that every chunk receives.
    all_blocks_flat = [b for chunk in chunks for b in chunk]
    master_plan = gen_state.get("master_story_plan", "")   # pre-filled if cached

    if not master_plan:
        gen_state["analysis_status"]  = "running"
        gen_state["analysis_message"] = (
            f"Analyzing {len(all_blocks_flat)} subtitle blocks for story structure..."
        )
        try:
            compressed = compress_srt_blocks_for_analysis(all_blocks_flat)
            master_plan = await run_master_plan_analysis_async(
                api_keys[0], model, compressed, len(all_blocks_flat)
            )
            if master_plan:
                gen_state["master_story_plan"]  = master_plan
                gen_state["analysis_status"]    = "done"
                gen_state["analysis_message"]   = (
                    f"Master Story Plan created ({len(master_plan)} chars) — "
                    f"all chunks will follow it."
                )
                gen_state["save_master_plan"]   = True  # main thread will cache this
            else:
                gen_state["analysis_status"]  = "failed"
                gen_state["analysis_message"] = (
                    "Story analysis failed — generating without Master Plan (fallback mode)."
                )
        except Exception as _ae:
            gen_state["analysis_status"]  = "failed"
            gen_state["analysis_message"] = f"Analysis error: {_ae} — continuing without plan."
            master_plan = ""
    else:
        gen_state["analysis_status"]  = "cached"
        gen_state["analysis_message"] = "Using cached Master Story Plan from previous run."

    if gen_state.get("stop_requested"):
        return

    # ── CHUNK 1 ──────────────────────────────────────────────────────────────
    chunk1 = chunks[0]
    exp1   = chunk1[-1].index - chunk1[0].index + 1
    gen_state["chunk_statuses"][1] = {
        "status": "processing", "start_time": time.time(),
        "prompts_done": 0, "pct": 0, "expected": exp1,
        "key_label": "Key 1",
    }

    if _is_history4:
        chunk1_msg = build_chunk1_message_history4(
            chunk              = chunk1,
            total_blocks       = gen_state["total_blocks"],
            mode               = mode_code,
            master_story_plan  = master_plan,
        )
    elif _is_short_style:
        chunk1_msg = build_chunk1_message_woodcut(
            srt_text          = format_chunk_for_api(chunk1),
            block_start       = chunk1[0].index,
            block_end         = chunk1[-1].index,
            total_blocks      = gen_state["total_blocks"],
            mode              = mode_code,
            master_story_plan = master_plan,
        )
    else:
        chunk1_msg = build_chunk1_message(
            srt_text          = format_chunk_for_api(chunk1),
            block_start       = chunk1[0].index,
            block_end         = chunk1[-1].index,
            total_blocks      = gen_state["total_blocks"],
            mode              = mode_code,
            master_story_plan = master_plan,
        )
        if visual_style == "custom" and custom_style:
            chunk1_msg += (
                f"\n\nSTYLE OVERRIDE: For every Image Prompt, end with this "
                f"style line instead of the default dark fantasy style: "
                f"{custom_style}"
            )

    _chars   = [0]
    _last_ui = [0.0]

    _lock = gen_state.get("_lock")

    def on_token(delta: str, full_text: str) -> None:
        _chars[0] += len(delta)
        now = time.time()
        if now - _last_ui[0] < 0.3:
            return
        _last_ui[0] = now
        count = len(re.findall(r"Image Prompt\s+\d+\s*:", full_text, re.IGNORECASE))
        pct   = min(100, int(count / exp1 * 100)) if exp1 > 0 else 0
        with (_lock if _lock else nullcontext()):
            gen_state["chunk1_live"]       = full_text
            gen_state["chunk_statuses"][1] = {
                **gen_state["chunk_statuses"][1],
                "prompts_done": count, "pct": pct,
            }

    try:
        # NOTE: send_chunk_sync_streaming uses requests (blocking).
        # Since we're already in a dedicated background thread, this is fine.
        chunk1_response = send_chunk_sync_streaming(
            api_keys[0], model, sys_full, chunk1_msg, on_token
        )
    except Exception as exc:
        gen_state["chunk_statuses"][1] = {
            "status": "error", "error_msg": str(exc)[:200],
            "prompts_done": 0, "pct": 0, "key_label": "Key 1",
        }
        gen_state["fatal_error"] = f"Chunk 1 failed: {exc}"
        return

    chunk1_prompts = extract_all_prompts(chunk1_response)
    if _is_short_style:
        for _p in chunk1_prompts:
            _p["image_prompt"] = process_prompt_with_style(
                _p["image_prompt"], visual_style, _p["image_prompt"]
            )
    gen_state["all_prompts"].extend(chunk1_prompts)
    gen_state["chunk1_response"]  = chunk1_response
    gen_state["character_cards"]  = extract_character_cards(chunk1_response)
    gen_state["last_prompt"]      = extract_last_prompt(chunk1_response)
    elapsed1 = time.time() - gen_state["chunk_statuses"][1]["start_time"]
    gen_state["chunk_statuses"][1] = {
        "status": "done", "elapsed": elapsed1,
        "prompts_done": len(chunk1_prompts), "pct": 100,
    }
    gen_state["chunk1_live"] = ""   # clear live display

    if len(chunks) <= 1 or gen_state.get("stop_requested"):
        return

    # ── CHUNKS 2+ ────────────────────────────────────────────────────────────
    n_keys = len(api_keys)
    chunk_messages = []
    for i, chunk in enumerate(chunks[1:], 2):
        chunk_idx    = i - 2                             # 0-based for round-robin
        assigned_key = api_keys[chunk_idx % n_keys]
        key_label    = f"Key {api_keys.index(assigned_key) + 1}"
        expected     = chunk[-1].index - chunk[0].index + 1
        gen_state["chunk_statuses"][i] = {
            "status": "queued", "prompts_done": 0, "pct": 0,
            "expected": expected, "key_label": key_label,
        }
        if _is_history4:
            msg = build_continuation_chunk_message_history4(
                chunk              = chunk,
                chunk_number       = i,
                total_chunks       = len(chunks),
                character_cards    = gen_state["character_cards"],
                last_prompt        = gen_state["last_prompt"],
                total_blocks       = gen_state["total_blocks"],
                mode               = mode_code,
                master_story_plan  = master_plan,
            )
        elif _is_short_style:
            msg = build_continuation_chunk_message_woodcut(
                srt_text          = format_chunk_for_api(chunk),
                chunk_number      = i,
                total_chunks      = len(chunks),
                block_start       = chunk[0].index,
                block_end         = chunk[-1].index,
                character_cards   = gen_state["character_cards"],
                last_prompt       = gen_state["last_prompt"],
                total_blocks      = gen_state["total_blocks"],
                mode              = mode_code,
                master_story_plan = master_plan,
            )
        else:
            msg = build_continuation_chunk_message(
                srt_text          = format_chunk_for_api(chunk),
                chunk_number      = i,
                total_chunks      = len(chunks),
                block_start       = chunk[0].index,
                block_end         = chunk[-1].index,
                character_cards   = gen_state["character_cards"],
                last_prompt       = gen_state["last_prompt"],
                scene_context     = infer_scene_context(format_chunk_for_api(chunk)),
                mode              = mode_code,
                master_story_plan = master_plan,
            )
            if visual_style == "custom" and custom_style:
                msg += (
                    f"\n\nSTYLE OVERRIDE: For every Image Prompt, end with this "
                    f"style line instead of the default dark fantasy style: "
                    f"{custom_style}"
                )
        chunk_messages.append({
            "chunk_id": i, "message": msg, "expected_prompts": expected,
            "api_key": assigned_key, "key_label": key_label,
        })

    def on_chunk_update(chunk_id: int, event: str, prompts_done: int, pct: int, msg: str) -> None:
        with (_lock if _lock else nullcontext()):
            s = dict(gen_state["chunk_statuses"].get(chunk_id, {}))
            if event == "processing":
                gen_state["chunk_statuses"][chunk_id] = {
                    **s, "status": "processing",
                    "start_time": time.time(), "prompts_done": 0, "pct": 0,
                    # msg carries the key_label string sent by process_one
                    "key_label": msg or s.get("key_label", ""),
                }
            elif event == "progress":
                gen_state["chunk_statuses"][chunk_id] = {
                    **s, "prompts_done": prompts_done, "pct": pct,
                }
            elif event == "retrying":
                gen_state["chunk_statuses"][chunk_id] = {
                    **s, "status": "retrying", "retry_msg": msg,
                }
            elif event in ("done", "error", "stopped"):
                elapsed = (
                    time.time() - s.get("start_time", time.time())
                    if s.get("start_time") else 0
                )
                gen_state["chunk_statuses"][chunk_id] = {
                    **s,
                    "status": event,
                    "elapsed": elapsed,
                    "pct": 100 if event == "done" else s.get("pct", 0),
                    "error_msg": msg if event == "error" else "",
                }

    results = await process_chunks_queue(
        api_keys      = api_keys,
        model         = model,
        system_prompt = sys_short,
        chunk_messages= chunk_messages,
        max_parallel  = max_parallel,
        on_chunk_update = on_chunk_update,
        gen_state     = gen_state,
    )

    for r in results:
        if r.get("status") == "success" and r.get("content"):
            _cont_prompts = extract_all_prompts(r["content"])
            if _is_short_style:
                for _p in _cont_prompts:
                    _p["image_prompt"] = process_prompt_with_style(
                        _p["image_prompt"], visual_style, _p["image_prompt"]
                    )
            gen_state["all_prompts"].extend(_cont_prompts)
        elif r.get("status") in ("error",):
            gen_state["errors"].append(
                f"Chunk {r['chunk_id']}: {r.get('error', 'Unknown')[:200]}"
            )

    gen_state["all_prompts"].sort(key=lambda x: x["block"])

    # ── Post-generation: dedup + validate ─────────────────────────────────────
    # Remove duplicates (keep last occurrence so retried blocks win)
    _by_block: dict[int, dict] = {}
    for _p in gen_state["all_prompts"]:
        _by_block[_p["block"]] = _p
    gen_state["all_prompts"] = sorted(_by_block.values(), key=lambda x: x["block"])

    # Remove extra prompts (block numbers beyond expected range)
    _total = gen_state.get("total_blocks", 0)
    _expected_nums = gen_state.get("expected_block_numbers", set())
    if _expected_nums:
        _before_extra = len(gen_state["all_prompts"])
        gen_state["all_prompts"] = [
            _p for _p in gen_state["all_prompts"]
            if _p["block"] in _expected_nums
        ]
        _removed = _before_extra - len(gen_state["all_prompts"])
        if _removed > 0:
            gen_state.setdefault("auto_fix_log", []).append(
                f"Auto-removed {_removed} extra prompt(s) outside expected block range."
            )

    # Store validation result in gen_state for the results UI
    gen_state["prompt_validation"] = validate_prompt_count(
        gen_state["all_prompts"], _total
    )


# ─────────────────────────────────────────────────────────────────────────────
# GENERATION UI (shown while is_generating == True)
# ─────────────────────────────────────────────────────────────────────────────

def render_generation_ui() -> None:
    """Placeholder-based polling — ALL chunk cards refresh simultaneously.

    How it works:
    • Pre-create one st.empty() placeholder per chunk card (done once per full
      script rerun).  Placeholders are written to via placeholder.markdown()
      which pushes the update to the browser immediately over the websocket,
      WITHOUT requiring a full script rerun.
    • An inner loop refreshes all placeholders every 0.5 s.  After 4 iterations
      (≈ 2 s) a full st.rerun() is called so Streamlit can process button clicks
      (Stop button) and flush its internal state.
    • Because we write ALL chunk cards in one pass per tick, every parallel
      chunk's progress bar moves on every refresh — not just one at a time.
    """
    gen_state  = st.session_state.gen_state
    gen_thread = st.session_state.gen_thread
    lock       = gen_state.get("_lock")
    _ctx       = lock if lock else nullcontext()

    # ── Stop button ──────────────────────────────────────────────────────────
    stop_col, _ = st.columns([1, 4])
    with stop_col:
        if st.button("⏹️ Stop Generation", type="secondary", use_container_width=True):
            gen_state["stop_requested"] = True

    # ── Overall progress bar placeholder ──────────────────────────────────────
    overall_ph = st.empty()

    # ── Step 0: Story Analysis status placeholder ──────────────────────────────
    st.markdown(
        '<div class="section-title">Step 0 — Master Story Plan Analysis</div>',
        unsafe_allow_html=True,
    )
    analysis_ph = st.empty()

    # ── Chunk 1 live display placeholder ──────────────────────────────────────
    st.markdown(
        '<div class="section-title">Chunk 1 — Pre-Analysis + Prompts</div>',
        unsafe_allow_html=True,
    )
    chunk1_ph = st.empty()

    # ── Pre-create one placeholder per parallel chunk ─────────────────────────
    # We derive IDs from gen_state["chunks"] (always correct) rather than from
    # chunk_statuses (which may not yet include all chunks at first render).
    n_chunks     = len(gen_state.get("chunks", []))
    parallel_ids = list(range(2, n_chunks + 1))
    chunk_phs: dict = {}

    if parallel_ids:
        st.markdown(
            f'<div class="section-title">'
            f'Chunks 2–{n_chunks} — Parallel '
            f'(max {gen_state["max_parallel"]} concurrent)</div>',
            unsafe_allow_html=True,
        )
        cols_per_row = 4
        for row_start in range(0, len(parallel_ids), cols_per_row):
            row_ids = parallel_ids[row_start : row_start + cols_per_row]
            cols    = st.columns(len(row_ids))
            for col, cid in zip(cols, row_ids):
                with col:
                    chunk_phs[cid] = st.empty()

    # ── Refresh function — one snapshot → all placeholders updated at once ─────
    def _refresh() -> None:
        total_blocks = gen_state.get("total_blocks", 1)
        elapsed      = time.time() - gen_state["start_time"]

        with _ctx:
            done_prompts    = len(gen_state.get("all_prompts", []))
            analysis_status = gen_state.get("analysis_status", "pending")
            analysis_msg    = gen_state.get("analysis_message", "")
            # Shallow-copy each status dict so we release the lock quickly
            statuses = {k: dict(v) for k, v in gen_state["chunk_statuses"].items()}

        # Overall progress
        pct = min(done_prompts / total_blocks, 1.0) if total_blocks > 0 else 0
        overall_ph.progress(
            pct,
            text=f"📊 {done_prompts}/{total_blocks} prompts · ⏱️ {fmt(elapsed)}",
        )

        # Analysis step status
        if analysis_status == "running":
            analysis_ph.info(f"🧠 {analysis_msg or 'Analyzing full story arc...'}")
        elif analysis_status in ("done", "cached"):
            icon = "📋" if analysis_status == "cached" else "✅"
            analysis_ph.success(f"{icon} {analysis_msg}")
        elif analysis_status == "failed":
            analysis_ph.warning(f"⚠️ {analysis_msg}")
        else:
            analysis_ph.info("⏳ Story analysis queued...")

        # Chunk 1
        s1  = statuses.get(1, {})
        st1 = s1.get("status", "queued")
        if st1 == "processing":
            live = gen_state.get("chunk1_live", "")
            if live:
                chunk1_ph.code("\n".join(live.split("\n")[-16:]), language=None)
            else:
                chunk1_ph.info("⏳ Waiting for first tokens…")
        elif st1 == "done":
            chunk1_ph.success(
                f"✅ Chunk 1 complete — {s1.get('prompts_done', 0)} prompts "
                f"in {fmt(s1.get('elapsed', 0))}"
            )
        elif st1 == "error":
            chunk1_ph.error(f"❌ Chunk 1 failed: {s1.get('error_msg', 'Unknown error')}")
        else:
            chunk1_ph.info("⏳ Chunk 1 queued…")

        # All parallel chunk cards — pushed to browser simultaneously
        n_keys_ui = max(1, len(gen_state.get("api_keys", [""])))
        for cid, ph in chunk_phs.items():
            s = statuses.get(
                cid,
                {
                    "status":       "queued",
                    "prompts_done": 0,
                    "pct":          0,
                    "expected":     "?",
                    "key_label":    f"Key {((cid - 2) % n_keys_ui) + 1}",
                },
            )
            ph.markdown(_card_html(cid, s), unsafe_allow_html=True)

    # ── Inner polling loop ─────────────────────────────────────────────────────
    # 4 × 0.5 s = 2 s of in-place updates, then st.rerun() for button handling.
    POLL_INTERVAL = 0.5
    INNER_LOOPS   = 4

    _refresh()  # immediate first paint

    for _ in range(INNER_LOOPS - 1):
        if gen_state.get("done") or (gen_thread and not gen_thread.is_alive()):
            st.session_state.is_generating = False
            st.rerun()
            return
        time.sleep(POLL_INTERVAL)
        _refresh()

    # Hand control back to Streamlit (processes Stop clicks, flushes state)
    if gen_state.get("done") or (gen_thread and not gen_thread.is_alive()):
        st.session_state.is_generating = False
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# RETRY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_retry_message(
    missing_blocks: list[int],
    all_srt_blocks: list,
    character_cards: str,
    all_prompts: list,
    mode_code: str,
    master_plan: str = "",
) -> str:
    """Build a targeted user message to regenerate only the specified blocks."""
    missing_set = set(missing_blocks)
    missing_srt = [b for b in all_srt_blocks if b.index in missing_set]
    srt_text    = format_chunk_for_api(missing_srt)
    first_m     = min(missing_blocks)
    last_m      = max(missing_blocks)

    # Best continuity reference: last generated prompt just before first missing block
    by_block = {p["block"]: p for p in all_prompts}
    cont_ref = ""
    for prev in range(first_m - 1, 0, -1):
        if prev in by_block:
            img_text = by_block[prev].get("image_prompt", "")[:400]
            cont_ref = f"Image Prompt {prev}: {img_text}"
            break

    scene_ctx  = infer_scene_context(srt_text)
    mode_label = (
        "Option A: Image Prompts Only"
        if mode_code == "A"
        else "Option B: Image + Video Prompts"
    )

    plan_section = ""
    if master_plan:
        plan_section = (
            f"MASTER STORY PLAN — use to match visual mood for blocks {missing_blocks}:\n"
            f"{master_plan[:3000]}{'...' if len(master_plan) > 3000 else ''}\n\n"
        )

    return (
        f"The user selected: {mode_label}\n\n"
        f"RETRY TASK — These subtitle blocks were missed in the original generation.\n"
        f"Generate prompts ONLY for: {missing_blocks}\n\n"
        f"STRICT RULES:\n"
        f"- Generate EXACTLY {len(missing_blocks)} prompts, one per listed block.\n"
        f"- First output must be \"Image Prompt {first_m}:\"\n"
        f"- ONLY output prompts for blocks in {missing_blocks}. Skip all others.\n\n"
        f"CHARACTER CARDS (use FULL descriptions as written):\n{character_cards}\n\n"
        f"SCENE CONTEXT:\n{scene_ctx}\n\n"
        f"{plan_section}"
        f"CONTINUITY REFERENCE (last generated prompt before first missing block):\n"
        f"{cont_ref or 'Beginning of content — no prior prompt available.'}\n\n"
        f"SRT BLOCKS TO REGENERATE:\n\n{srt_text}\n\n"
        f"Generate Image Prompt {first_m} through Image Prompt {last_m}. "
        f"Use full Character Card descriptions every time a character appears. "
        f"Follow all style, formatting, and subtitle-fidelity rules.\n\n"
        f"FINAL REMINDER: Output EXACTLY {len(missing_blocks)} prompts for blocks {missing_blocks}. "
        f"No extra prompts. No skipped blocks."
    )


def _retry_generation_thread(gen_state: dict) -> None:
    """Background thread: stream a retry call for missing blocks.
    Writes live text and final result into gen_state['retry'].
    """
    retry        = gen_state["retry"]
    visual_style = gen_state.get("visual_style", "dark_fantasy")
    master_plan  = gen_state.get("master_story_plan", "")
    try:
        all_blocks = [b for chunk in gen_state["chunks"] for b in chunk]
        msg        = _build_retry_message(
            missing_blocks  = retry["missing_blocks"],
            all_srt_blocks  = all_blocks,
            character_cards = gen_state.get("character_cards", ""),
            all_prompts     = gen_state.get("all_prompts", []),
            mode_code       = gen_state.get("mode_code", "A"),
            master_plan     = master_plan,
        )

        # Use the style-correct system prompt (not always dark_fantasy short prompt)
        if visual_style in ("dark_fantasy", "custom"):
            sys_short = load_system_prompt_short()
        else:
            sys_short = load_system_prompt_for_style(visual_style)
        api_keys  = gen_state.get("api_keys", [])
        model     = gen_state.get("model", "")

        def on_token(delta: str, full_text: str) -> None:
            retry["live_text"] = full_text

        response = send_chunk_sync_streaming(
            api_keys[0], model, sys_short, msg, on_token
        )
        retry["response"] = response
        retry["status"]   = "done"
    except Exception as exc:
        retry["error"]  = str(exc)[:300]
        retry["status"] = "error"


# ─────────────────────────────────────────────────────────────────────────────
# RESULTS UI
# ─────────────────────────────────────────────────────────────────────────────

def render_results_ui() -> None:
    gen_state = st.session_state.gen_state

    # ── Retry state machine ───────────────────────────────────────────────────

    retry = gen_state.get("retry")

    # A) Retry is running → show live stream and keep polling
    if retry and retry.get("status") == "running":
        n_missing = len(retry.get("missing_blocks", []))
        st.info(f"🔄 Retrying {n_missing} missing prompts… (30–90 s)")
        live = retry.get("live_text", "")
        retry_ph = st.empty()
        if live:
            retry_ph.code("\n".join(live.split("\n")[-10:]), language=None)
        else:
            retry_ph.info("⏳ Waiting for first tokens…")
        time.sleep(0.5)
        st.rerun()
        return

    # B) Retry just finished → merge results, stash banner, clear retry state
    _retry_banner: tuple | None = None
    if retry and retry.get("status") in ("done", "error"):
        if retry.get("status") == "done":
            new_prompts = extract_all_prompts(retry.get("response", ""))
            if new_prompts:
                by_block = {p["block"]: p for p in gen_state["all_prompts"]}
                for p in new_prompts:
                    by_block[p["block"]] = p
                gen_state["all_prompts"] = sorted(
                    by_block.values(), key=lambda x: x["block"]
                )
                recovered     = len(new_prompts)
                total_retried = len(retry.get("missing_blocks", []))
                still_missing = total_retried - recovered
                if still_missing <= 0:
                    _retry_banner = (
                        "success",
                        f"✅ Retry complete! Recovered all {recovered} missing prompts.",
                    )
                else:
                    _retry_banner = (
                        "warning",
                        f"⚠️ Recovered {recovered}/{total_retried} prompts. "
                        f"{still_missing} still missing — you can retry again.",
                    )
            else:
                _retry_banner = (
                    "warning",
                    "⚠️ Retry returned no parseable prompts. Try again.",
                )
        else:
            _retry_banner = ("error", f"❌ Retry failed: {retry.get('error', 'Unknown error')}")
        gen_state["retry"] = None   # clear after handling

    # ── Normal results ────────────────────────────────────────────────────────
    all_prompts  = gen_state.get("all_prompts", [])
    total_blocks = gen_state.get("total_blocks", 0)
    elapsed      = gen_state.get("end_time", time.time()) - gen_state["start_time"]
    mode_code    = gen_state["mode_code"]

    if gen_state.get("fatal_error"):
        st.error(f"❌ Generation failed: {gen_state['fatal_error']}")
        if st.button("🔄 Try Again"):
            st.session_state.gen_state = None
            st.rerun()
        return

    # Show retry recovery banner (appears above the main stats)
    if _retry_banner:
        lvl, msg = _retry_banner
        if lvl == "success":
            st.success(msg)
        elif lvl == "warning":
            st.warning(msg)
        else:
            st.error(msg)

    _used_style = gen_state.get("visual_style", "dark_fantasy")
    _style_name_map = {
        "dark_fantasy":        "🎨 Dark Fantasy Oil Painting",
        "history_1":           "🏛️ History 1 — Museum Parchment",
        "history_2":           "🎬 History 2 — Documentary Dual Tone",
        "history_3":           "🌙 History 3 — Impasto Mystical",
        "history_4":           "🏺 History 4 — Ancient Fresco",
        "history_5":           "✏️ History 5 — 2D Animated Storyboard",
        "woodcut":             "🪵 Woodcut / Linocut",
        "victorian_engraving": "📰 Victorian Engraving",
        "custom":              "✏️ Custom Style",
    }
    _style_label = _style_name_map.get(_used_style, _used_style)
    _custom_note = ""
    if _used_style == "custom":
        _ct = gen_state.get("custom_style_text", "")
        if _ct:
            _custom_note = f" — `{_ct[:60]}{'…' if len(_ct) > 60 else ''}`"

    st.success(
        f"✅ Generation complete! · ⏱️ {fmt(elapsed)} · "
        f"📊 {len(all_prompts)}/{total_blocks} prompts · "
        f"Style: {_style_label}{_custom_note}"
    )

    # History 2 — Color / B&W breakdown
    if _used_style == "history_2" and all_prompts:
        _color_c, _bw_c = count_color_bw(all_prompts)
        _total_cb = _color_c + _bw_c
        _cb1, _cb2, _cb3 = st.columns(3)
        with _cb1: st.metric("🎨 Color Prompts", _color_c)
        with _cb2: st.metric("⬛ B&W Prompts",   _bw_c)
        with _cb3:
            _ratio = int(_color_c / _total_cb * 100) if _total_cb > 0 else 0
            st.metric("📊 Color Ratio", f"{_ratio}%")

    # History 3 — Noor (sacred figure) breakdown
    if _used_style == "history_3" and all_prompts:
        _noor_c, _norm_c = count_noor_prompts(all_prompts)
        if _noor_c > 0:
            _n1, _n2 = st.columns(2)
            with _n1: st.metric("✨ Noor (Sacred) Prompts", _noor_c)
            with _n2: st.metric("👤 Normal Figure Prompts", _norm_c)

    # History 5 — fire accent breakdown
    if _used_style == "history_5" and all_prompts:
        _fire_c, _nofire_c = count_fire_accent_prompts(all_prompts)
        _total_f = _fire_c + _nofire_c
        _f1, _f2, _f3 = st.columns(3)
        with _f1: st.metric("🔥 Fire Accent Scenes", _fire_c)
        with _f2: st.metric("☀️ Daylight Scenes",    _nofire_c)
        with _f3:
            _fratio = int(_fire_c / _total_f * 100) if _total_f > 0 else 0
            st.metric("🔥 Fire Ratio", f"{_fratio}%")

    # History 4 — word count accuracy breakdown
    if _used_style == "history_4" and all_prompts:
        _word_counts = [len(p["image_prompt"].split()) for p in all_prompts]
        _avg_wc  = sum(_word_counts) / len(_word_counts)
        _min_wc  = min(_word_counts)
        _max_wc  = max(_word_counts)
        _in_rng  = sum(1 for wc in _word_counts if 25 <= wc <= 47)
        _acc     = int(_in_rng / len(_word_counts) * 100)
        _wc1, _wc2, _wc3, _wc4 = st.columns(4)
        with _wc1: st.metric("📏 Avg Words/Prompt", f"{_avg_wc:.0f}")
        with _wc2: st.metric("📉 Min Words", _min_wc)
        with _wc3: st.metric("📈 Max Words", _max_wc)
        with _wc4: st.metric("🎯 In Range (±3)", f"{_acc}%")

    # ── Mode B — Video Prompt stats (all styles) ──────────────────────────────
    if mode_code == "B":
        _video_prompts = [p for p in all_prompts if p.get("video_prompt", "").strip()]
        _img_count     = len(all_prompts)
        _vid_count     = len(_video_prompts)
        _vid_match     = _vid_count == _img_count
        _vc1, _vc2, _vc3 = st.columns(3)
        with _vc1: st.metric("🖼️ Image Prompts",  _img_count)
        with _vc2: st.metric("🎬 Video Prompts",  _vid_count)
        with _vc3:
            if _vid_match:
                st.metric("🔗 Paired", "✅ Perfect")
            else:
                _diff = abs(_img_count - _vid_count)
                st.metric("🔗 Paired", f"⚠️ {_diff} missing")
        if not _vid_match:
            _missing_vids = [p["block"] for p in all_prompts if not p.get("video_prompt", "").strip()]
            st.warning(
                f"⚠️ {len(_missing_vids)} blocks have no Video Prompt: "
                f"{_missing_vids[:20]}{'...' if len(_missing_vids) > 20 else ''}"
            )

    # ── Count validation stats ────────────────────────────────────────────────
    _validation = gen_state.get("prompt_validation") or validate_prompt_count(all_prompts, total_blocks)
    _missing_list = _validation["missing"]
    _extra_list   = _validation["extra"]

    # Show auto-fix log if any extra prompts were removed automatically
    for _log_msg in gen_state.get("auto_fix_log", []):
        st.info(f"🔧 {_log_msg}")

    r1, r2, r3, r4 = st.columns(4)
    with r1: st.metric("✅ Generated",  _validation["generated"])
    with r2: st.metric("📦 Expected",   _validation["expected"])
    with r3: st.metric("⚠️ Missing",    len(_missing_list), delta=f"{'✅ Perfect' if not _missing_list else f'{len(_missing_list)} blocks'}", delta_color="off")
    with r4: st.metric("➕ Extra",      len(_extra_list),   delta=f"{'✅ None' if not _extra_list else f'{len(_extra_list)} removed'}", delta_color="off")

    if _validation["is_perfect"]:
        st.success("✅ Perfect count — every subtitle block has exactly one prompt!")
    else:
        if _missing_list:
            _miss_preview = str(_missing_list[:20]) + ("..." if len(_missing_list) > 20 else "")
            st.warning(f"⚠️ {len(_missing_list)} missing prompt(s): blocks {_miss_preview}")

        if _extra_list:
            st.info(f"🔧 {len(_extra_list)} extra prompt(s) were auto-removed (blocks {_extra_list[:10]})")

        if _missing_list:
            rc1, rc2 = st.columns([1, 1])
            with rc1:
                if st.button(
                    f"🔄 Retry {len(_missing_list)} Missing Prompts",
                    type="primary",
                    use_container_width=True,
                    key="retry_btn",
                ):
                    gen_state["retry"] = {
                        "status":         "running",
                        "missing_blocks": _missing_list,
                        "live_text":      "",
                        "response":       "",
                        "error":          "",
                    }
                    t = threading.Thread(
                        target=_retry_generation_thread,
                        args=(gen_state,),
                        daemon=True,
                    )
                    t.start()
                    st.rerun()
            with rc2:
                if st.button(
                    "🔄 Retry ALL (full regeneration)",
                    use_container_width=True,
                    key="retry_all_btn",
                ):
                    gen_state["retry"] = None
                    st.session_state.gen_state = None
                    st.rerun()

    # Errors
    if gen_state.get("errors"):
        with st.expander(f"❌ Errors ({len(gen_state['errors'])} chunks)", expanded=True):
            for e in gen_state["errors"]:
                st.error(e)

    if gen_state.get("stop_requested"):
        st.info("⏹️ Generation was stopped early. Partial results shown above.")

    # Copy + Download
    txt_data = export_txt(all_prompts, mode_code)
    copy_btn(txt_data, "📋 Copy All Prompts to Clipboard")

    st.subheader("⬇️ Download")
    d1, d2 = st.columns(2)
    with d1:
        st.download_button("⬇️ .txt", data=txt_data, file_name="prompts.txt",
                           mime="text/plain", use_container_width=True)
    with d2:
        st.download_button("⬇️ .xlsx",
                           data=export_xlsx(all_prompts, mode_code, _used_style),
                           file_name="prompts.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

    # Preview
    with st.expander("👀 Preview (first 5 prompts)", expanded=True):
        for p in all_prompts[:5]:
            tc, bc = st.columns([0.87, 0.13])
            with tc:
                st.markdown(f"**Image Prompt {p['block']}:**")
                preview = p["image_prompt"]
                st.text(preview[:500] + "…" if len(preview) > 500 else preview)
            with bc:
                copy_btn(p["image_prompt"], "📋", height=42)
            if mode_code == "B" and p.get("video_prompt"):
                st.markdown(f"**Video Prompt {p['block']}:**")
                st.text(p["video_prompt"][:300])
            st.divider()
        if len(all_prompts) > 5:
            st.caption(f"…and {len(all_prompts) - 5} more prompts in the downloaded files.")

    # ── Master Story Plan caching (main thread → session_state) ──────────────
    if gen_state.get("save_master_plan"):
        _plan_to_save = gen_state.get("master_story_plan", "")
        _hash_key     = gen_state.get("srt_hash", "")
        if _hash_key and _plan_to_save:
            st.session_state[f"master_plan_{_hash_key}"] = _plan_to_save
        gen_state["save_master_plan"] = False

    # ── Master Story Plan expander ────────────────────────────────────────────
    _master_plan = gen_state.get("master_story_plan", "")
    if _master_plan:
        with st.expander("📋 Master Story Plan (Full Story Analysis)", expanded=False):
            _analysis_status = gen_state.get("analysis_status", "")
            if _analysis_status == "cached":
                st.caption("📋 Cached from previous run with this SRT file.")
            st.text(_master_plan)

    # ── Visual consistency check ──────────────────────────────────────────────
    if _master_plan and all_prompts:
        _prompts_dict = {p["block"]: p["image_prompt"] for p in all_prompts}
        _consistency_warnings = check_visual_consistency(_prompts_dict, _master_plan)
        if _consistency_warnings:
            with st.expander(
                f"⚠️ {len(_consistency_warnings)} Visual Consistency Warning(s)",
                expanded=False,
            ):
                for _w in _consistency_warnings[:20]:
                    st.warning(_w)
                if len(_consistency_warnings) > 20:
                    st.caption(f"…and {len(_consistency_warnings) - 20} more warnings.")

    # Pre-analysis
    chunk1_resp = gen_state.get("chunk1_response", "")
    with st.expander("🧠 Character Cards & Story Analysis", expanded=False):
        pre_end = chunk1_resp.find("Image Prompt 1")
        st.text(chunk1_resp[:pre_end] if pre_end > 0 else chunk1_resp[:4000])

    with st.expander("🔍 Debug: Raw Chunk 1 Response", expanded=False):
        st.text(chunk1_resp[:6000])

    if st.button("🔄 Generate Again (new SRT or settings)"):
        gen_state["retry"] = None
        st.session_state.gen_state = None
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# HOW TO USE PAGE
# ─────────────────────────────────────────────────────────────────────────────

def render_how_to_use() -> None:
    st.markdown("## 📖 How to Use — Prompt Generator by MegaShoeb")
    st.caption("Complete guide to getting started and generating AI image prompts from SRT subtitles.")
    st.divider()

    # ── Step 1: Get API Key ───────────────────────────────────────────────────
    st.markdown("### 🔑 Step 1 — Get Your Free API Key")
    st.info(
        "This tool uses **OpenRouter** to access the AI model. "
        "OpenRouter gives you a **free API key** that includes free model access."
    )
    with st.expander("📋 How to get a free OpenRouter API key (click to expand)", expanded=True):
        st.markdown("""
**Follow these steps:**

1. 🌐 Open **[https://openrouter.ai](https://openrouter.ai)** in your browser

2. 👤 Click **"Sign In"** → Sign up with Google, GitHub, or email (free — no credit card needed)

3. 🔑 After logging in, go to **[https://openrouter.ai/keys](https://openrouter.ai/keys)**

4. ➕ Click **"Create Key"** → give it any name → click **"Create"**

5. 📋 **Copy the key** — it starts with `sk-or-v1-...`

6. 🔒 Paste it into the **"OpenRouter API Key"** field in the left sidebar

> ✅ The free tier includes access to **Step 3.5 Flash** (the default model used by this tool).
> No payment required for basic usage.
""")

    st.divider()

    # ── Step 2: Prepare SRT ──────────────────────────────────────────────────
    st.markdown("### 📄 Step 2 — Prepare Your SRT File")
    with st.expander("What is an SRT file?", expanded=False):
        st.markdown("""
An **SRT file** (.srt) is a subtitle file format. It contains numbered blocks of text with timestamps:

```
1
00:00:01,000 --> 00:00:04,000
In the year 1453, Constantinople fell.

2
00:00:05,000 --> 00:00:09,500
The Ottoman sultan Mehmed II led the final siege.

3
00:00:10,000 --> 00:00:14,000
After 53 days, the great city was taken.
```

Each block has:
- **A number** (block index)
- **Timestamps** (start → end)
- **Subtitle text** (the narration)

You can upload `.srt` or `.txt` files — or paste the SRT text directly.
""")

    with st.expander("How to export SRT from your video editor / YouTube", expanded=False):
        st.markdown("""
**From YouTube Studio:**
- Go to your video → **Subtitles** → Download SRT

**From Premiere Pro / DaVinci Resolve:**
- Export → choose **SubRip (.srt)** format

**From a script/text document:**
- Each paragraph of narration = one subtitle block
- Use a free tool like **[Subtitle Edit](https://www.nikse.dk/subtitleedit)** to create SRT from text
""")

    st.divider()

    # ── Step 3: Configure & Generate ─────────────────────────────────────────
    st.markdown("### ⚙️ Step 3 — Configure Settings")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
**📥 Input**
- **Upload SRT** — drag & drop your `.srt` file into the upload box
- **Paste SRT** — switch to the Paste tab and paste text directly

**🎨 Visual Style**
- Pick from 9 styles in the sidebar (see Style Guide below)
- Each style produces a different artistic look for the prompts

**📤 Output Mode**
- **Mode A** — Image prompts only (for AI image generators like Midjourney, Flux)
- **Mode B** — Image + Video prompts (for video generators like Kling, Runway)
""")
    with col2:
        st.markdown("""
**🔧 Advanced Settings**
- **Chunk Size** — how many subtitle blocks per API call (default: 30)
- **Parallel Tasks** — how many chunks run at the same time (default: 3)
  - Higher = faster but may cause 429 rate-limit errors on free tier
  - Recommended: **2–3** with one free key

**🔑 Multiple API Keys**
- Open **"Advanced: Multiple API Keys"** in the sidebar
- Paste one key per line — each key gets its own rate-limit quota
- More keys = more parallel capacity = much faster generation
""")

    st.divider()

    # ── Multiple API Keys + Parallel Tasks deep dive ──────────────────────────
    st.markdown("### ⚡ Speed Up — Multiple API Keys & Parallel Tasks")
    st.info("Using multiple free OpenRouter keys is the **fastest** way to generate prompts for long SRTs (200–500+ blocks).")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
**🔑 How to add multiple API keys:**

1. Go to **[openrouter.ai/keys](https://openrouter.ai/keys)**
2. Click **"Create Key"** — create 3–5 keys (all free)
3. Name them: `Key 1`, `Key 2`, `Key 3` etc.
4. In the sidebar → open **"🔑 Advanced: Multiple API Keys"**
5. Paste all keys — **one per line:**
```
sk-or-v1-abc123...
sk-or-v1-def456...
sk-or-v1-ghi789...
```
6. Click **"🔍 Validate Keys"** to confirm all keys work
7. Now generation uses all keys in parallel — 3x faster!
""")

    with col_b:
        st.markdown("""
**⚡ How Parallel Tasks work:**

Each chunk of subtitle blocks is sent to the AI as a separate task. Parallel Tasks = how many chunks run **at the same time**.

| Keys | Parallel Tasks | Speed |
|------|---------------|-------|
| 1 key | 2–3 | Normal |
| 2 keys | 4–6 | 2× faster |
| 3 keys | 6–9 | 3× faster |
| 5 keys | 10–15 | 5× faster |

**Rule of thumb:**
- Set **Parallel Tasks = (number of keys) × 2–3**
- Example: 3 keys → set Parallel Tasks to 6–9
- Each key handles ~2–3 parallel tasks safely on free tier

⚠️ Setting too high causes **429 rate-limit errors** — the tool will auto-retry, but it slows things down.
""")

    with st.expander("📊 Example: 300-block SRT generation time estimate", expanded=False):
        st.markdown("""
| Setup | Chunks | Parallel | Est. Time |
|-------|--------|----------|-----------|
| 1 key, 2 parallel | 10 chunks | 2 at a time | ~8–12 min |
| 2 keys, 4 parallel | 10 chunks | 4 at a time | ~4–6 min |
| 3 keys, 6 parallel | 10 chunks | 6 at a time | ~2–4 min |
| 5 keys, 10 parallel | 10 chunks | all at once | ~1–2 min |

*Estimates based on 30-block chunk size. Actual time varies with model load.*
""")

    st.divider()

    # ── Step 4: Generate ─────────────────────────────────────────────────────
    st.markdown("### 🎬 Step 4 — Generate & Download")
    st.markdown("""
1. ✅ API key entered → SRT uploaded → style selected → click **"🎬 Generate Prompts"**

2. 🧠 **Story Analysis** runs first (~15–30 sec) — reads the full SRT and creates a Master Story Plan so all chunks stay visually consistent

3. 📦 **Chunk 1** generates first (includes character cards + scene analysis)

4. ⚡ **Remaining chunks** generate in parallel

5. ✅ When complete, you can:
   - **📋 Copy All** — copy to clipboard
   - **⬇️ .txt** — plain text download
   - **⬇️ .xlsx** — Excel spreadsheet with formatting
   - **🔄 Retry Missing** — if any blocks were skipped, retry them automatically
""")

    st.divider()

    # ── Style Guide ──────────────────────────────────────────────────────────
    st.markdown("### 🎨 Visual Style Guide")
    styles_data = [
        ("🎨", "Dark Fantasy Oil Painting", "Hyper-detailed digital painting, dramatic chiaroscuro, rich oil paint textures.", "Mythology, epic battles, dark stories, fantasy worlds"),
        ("🏛️", "History 1 — Museum Parchment", "Hand-painted oil on aged parchment, museum artifact look, craquelure texture, warm ochre palette.", "Ancient history, empires, civilizations, documentary channels"),
        ("🎬", "History 2 — Documentary Dual Tone", "Auto Color/B&W per scene — oil-paint realism for biography, charcoal monochrome for war/tragedy.", "Biography channels, history documentaries, dual-tone storytelling"),
        ("🌙", "History 3 — Impasto Mystical", "Thick impasto oil painting, magical realism, lapis lazuli skies. Special Noor rule for Islamic sacred figures.", "Ancient mysteries, lost civilizations, Islamic history, mythology"),
        ("🏺", "History 4 — Ancient Fresco", "Ancient fresco / carved relief / illuminated manuscript. Midnight blues + muted gold. Duration-based word count.", "Sleep/ambient videos, ancient mysteries, reverent tone, calm storytelling"),
        ("✏️", "History 5 — 2D Animated Storyboard", "Hand-drawn 2D animation, clean ink outlines, painterly backgrounds. Mandatory fire glow for night scenes.", "Story-driven documentaries, animated history, campfire narrative tone"),
        ("🪵", "Woodcut / Linocut", "Bold thick ink outlines, flat color fills, dramatic closeups, relief print aesthetic.", "Historical documentaries, war, ancient civilizations, stark drama"),
        ("📰", "Victorian Engraving", "Fine crosshatching on aged parchment, newspaper illustration style, 19th century look.", "Victorian era, colonial history, 19th century, exploration narratives"),
        ("✏️", "Custom Style", "Define your own style — anime, comic book, watercolor, Studio Ghibli, etc.", "Any style not covered above"),
    ]
    for icon, name, desc, best_for in styles_data:
        with st.expander(f"{icon} {name}", expanded=False):
            st.markdown(f"**Description:** {desc}")
            st.markdown(f"**Best for:** {best_for}")

    st.divider()

    # ── FAQ ───────────────────────────────────────────────────────────────────
    st.markdown("### ❓ Frequently Asked Questions")

    with st.expander("Why am I getting 429 errors / rate limit errors?", expanded=False):
        st.markdown("""
The free OpenRouter tier has rate limits. Solutions:
- **Lower Parallel Tasks** to 1–2 in the sidebar
- **Add more API keys** in "Advanced: Multiple API Keys" (you can create multiple free keys)
- **Wait 60 seconds** and click "Retry Missing" to recover any skipped blocks
""")

    with st.expander("The prompt count doesn't match my SRT block count — what do I do?", expanded=False):
        st.markdown("""
After generation, if counts don't match:
1. The tool shows **⚠️ Missing X prompts** with the exact block numbers
2. Click **"🔄 Retry Missing Prompts"** — it will regenerate only the missing blocks
3. If still missing, click **"Retry ALL (full regeneration)"** to start fresh
""")

    with st.expander("What AI models are supported?", expanded=False):
        st.markdown("""
Currently the tool uses **Step 3.5 Flash** (by Stepfun) via OpenRouter — it's free, fast, and produces high-quality prompts.

Other models can be added — the model selector in the sidebar will be expanded in future updates.
""")

    with st.expander("Can I use this for non-mythology content?", expanded=False):
        st.markdown("""
Yes! Despite the name, this tool works for **any** narrated documentary content:
- History documentaries
- Educational videos
- Travel/nature documentaries
- Biography channels
- Any SRT-based video project

The "style" setting determines the visual look — choose the one that fits your content.
""")

    with st.expander("What's the Master Story Plan?", expanded=False):
        st.markdown("""
Before generating prompts, the tool analyzes your **entire SRT** to create a **Master Story Plan** — a structured document with:
- **Narrative phases** (introduction, backstory, battle, aftermath, etc.)
- **Character registry** (consistent visual descriptions for every named character)
- **Scene location map** (which blocks are set where)
- **Visual mood progression** (how lighting and color should evolve)

This plan is given to **every chunk** so they all produce visually consistent prompts — even when processing in parallel.

The plan is **cached** — if you re-generate with the same SRT, the analysis step is skipped.
""")

    with st.expander("Is my API key stored or sent anywhere?", expanded=False):
        st.markdown("""
Your API key is used **only** to make direct API calls to OpenRouter. It is:
- ✅ Never stored on any server
- ✅ Never logged or saved
- ✅ Sent only to OpenRouter's API endpoint (api.openrouter.ai)
- ✅ Lives only in your browser session (cleared when you close the tab)
""")

    st.divider()
    st.markdown("""
    <div style="text-align:center; color:#888; font-size:13px; padding:10px 0;">
    🎬 Prompt Generator by MegaShoeb · Built with Streamlit · Powered by OpenRouter<br>
    <a href="https://openrouter.ai/keys" style="color:#ff4b4b;">Get your free API key →</a>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────
for _k, _v in {
    "is_generating": False,
    "gen_state":     None,
    "gen_thread":    None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    # ── Page navigation ───────────────────────────────────────────────────────
    st.markdown("### 📌 Navigation")
    _nav_page = st.radio(
        "",
        ["🎬 Generator", "📖 How to Use"],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="nav_page",
    )
    st.divider()

    st.header("⚙️ Settings")

    api_key  = st.text_input("OpenRouter API Key", type="password", placeholder="sk-or-…")
    api_keys = [api_key] if api_key and api_key.strip() else []  # overridden below if multi-key

    model   = st.selectbox("Model", ["stepfun/step-3.5-flash:free"], index=0)

    # ── Visual Style selector ─────────────────────────────────────────────────
    st.markdown("### 🎨 Visual Style")
    visual_style = st.selectbox(
        "Choose image generation style",
        options=["dark_fantasy", "history_1", "history_2", "history_3", "history_4", "history_5", "woodcut", "victorian_engraving", "custom"],
        format_func=lambda x: {
            "dark_fantasy":        "🎨 Dark Fantasy Oil Painting",
            "history_1":           "🏛️ History 1 — Museum Parchment",
            "history_2":           "🎬 History 2 — Documentary Dual Tone",
            "history_3":           "🌙 History 3 — Impasto Mystical",
            "history_4":           "🏺 History 4 — Ancient Fresco",
            "history_5":           "✏️ History 5 — 2D Animated Storyboard",
            "woodcut":             "🪵 Woodcut / Linocut",
            "victorian_engraving": "📰 Victorian Engraving",
            "custom":              "✏️ Custom Style",
        }[x],
        index=0,
        help="Dark Fantasy = detailed cinematic. History 1 = museum parchment. History 2 = auto Color/B&W. History 3 = impasto + Noor. History 4 = fresco + duration word count. History 5 = 2D animation + fire accent. Woodcut = bold outlines. Victorian = crosshatching.",
        key="visual_style_select",
    )
    _style_descs = {
        "dark_fantasy":        "Hyper-detailed digital painting, dramatic chiaroscuro, rich oil textures. Best for: mythology, epic battles, dark stories.",
        "history_1":           "Hand-painted oil on aged parchment, museum artifact look, craquelure texture, warm ochre palette. Best for: ancient history, empires, civilizations, documentary channels.",
        "history_2":           "Auto Color/B&W per scene — oil-paint realism for biography, charcoal monochrome for war/tragedy. Best for: biography channels, history documentaries, dual-tone storytelling.",
        "history_3":           "Thick impasto oil painting, magical realism, lapis lazuli skies, cinematic chiaroscuro. Special Noor rule for Islamic sacred figures. Best for: ancient mysteries, lost civilizations, Islamic history, mythology.",
        "history_4":           "Ancient fresco, carved relief, illuminated manuscript look. Midnight blues + muted gold. Duration-based word count per prompt. Best for: sleep/ambient videos, ancient mysteries, reverent tone, calm storytelling.",
        "history_5":           "Hand-drawn 2D animation, clean ink outlines, painterly backgrounds, cinematic storyboard feel. Mandatory fire glow for night scenes. Best for: story-driven documentaries, animated history, campfire narrative tone.",
        "woodcut":             "Bold thick ink outlines, flat color fills, dramatic closeups. Best for: historical documentaries, war, ancient civilizations.",
        "victorian_engraving": "Fine crosshatching on aged parchment, newspaper illustration. Best for: Victorian era, colonial history, 19th century.",
        "custom":              "Define your own style — anime, comic book, watercolor, etc.",
    }
    st.caption(_style_descs[visual_style])

    custom_style_text = ""
    if visual_style == "custom":
        custom_style_text = st.text_area(
            "Describe your style",
            placeholder="e.g: anime illustration, clean line art, vibrant colors, Studio Ghibli, 16:9",
            height=80,
            key="custom_style_input",
        )

    mode    = st.radio("Output Mode",
                       ["A — Image Prompts Only", "B — Image + Video Prompts"], index=0)
    mode_code = "A" if mode.startswith("A") else "B"

    chunk_size     = st.slider("Chunk Size (blocks)", 15, 50, 30)
    gap_threshold  = st.slider("Scene Break Gap (s)", 1.0, 10.0, 3.0, 0.5)

    # ── Parallel tasks: slider OR custom number ───────────────────────────────
    st.markdown("**Parallel Tasks**")
    par_mode = st.radio("", ["Slider (1–8)", "Custom (1–20)"],
                        horizontal=True, label_visibility="collapsed")
    if par_mode == "Slider (1–8)":
        max_parallel = st.slider("", 1, 8, 3, label_visibility="collapsed")
    else:
        max_parallel = int(st.number_input("", min_value=1, max_value=20,
                                           value=3, step=1, label_visibility="collapsed"))
    if max_parallel > 3:
        st.warning("⚠️ Free tier: >3 parallel tasks may trigger 429 rate limits. Recommended: 2–3.")

    # ── Multi-key section ─────────────────────────────────────────────────────
    with st.expander("🔑 Advanced: Multiple API Keys"):
        api_keys_text = st.text_area(
            "Paste API keys (one per line)",
            height=100,
            placeholder="sk-or-key-1...\nsk-or-key-2...\nsk-or-key-3...",
            help="Add multiple OpenRouter API keys for faster generation. Each key gets its own rate limit quota.",
            key="multi_api_keys_text",
        )
        raw_keys = [k.strip() for k in api_keys_text.split("\n") if k.strip()]
        if raw_keys:
            api_keys = raw_keys  # override single-key with multi-key list
            _val_cache = f"key_val_{hash(tuple(raw_keys))}"
            _vc, _ = st.columns([1, 1])
            with _vc:
                if st.button("🔍 Validate Keys", key="validate_keys_btn"):
                    with st.spinner("Validating keys…"):
                        _vk, _ve = validate_api_keys_sync(raw_keys, model)
                    st.session_state[_val_cache] = (_vk, _ve)
            if _val_cache in st.session_state:
                _vk, _ve = st.session_state[_val_cache]
                for _e in _ve:
                    st.warning(f"⚠️ {_e}")
                if _vk:
                    st.success(f"✅ {len(_vk)}/{len(raw_keys)} keys passed validation")
                    api_keys = _vk  # drop invalid keys

    if len(api_keys) > 1:
        _eff = max(1, max_parallel // len(api_keys)) * len(api_keys)
        st.info(
            f"🔑 Active keys: {len(api_keys)} | "
            f"Effective parallel capacity: {_eff} "
            f"({max(1, max_parallel // len(api_keys))} per key)"
        )

    # ── Chunking mode ─────────────────────────────────────────────────────────
    st.markdown("**Chunking Method**")
    chunking_mode = st.radio(
        "",
        ["Auto (timestamp gaps)", "Smart (AI story analysis)"],
        index=0,
        label_visibility="collapsed",
        help="Smart mode makes a quick AI call to find natural scene breaks. ~15 s extra.",
    )

    st.divider()
    st.caption("🔑 [Get free API key → openrouter.ai](https://openrouter.ai)")

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("<h1>🎬 Prompt Generator <span style='color:#ff4b4b;'>by MegaShoeb</span></h1>", unsafe_allow_html=True)
st.caption("SRT → AI Image Prompts  |  Powered by Step 3.5 Flash")
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# PAGE ROUTING — How to Use
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.get("nav_page") == "📖 How to Use":
    render_how_to_use()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# GENERATING STATE — hijack entire page
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.is_generating:
    render_generation_ui()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# COMPLETED STATE — show results
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.gen_state and st.session_state.gen_state.get("done"):
    render_results_ui()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# IDLE STATE — upload + configure + generate
# ─────────────────────────────────────────────────────────────────────────────
tab_upload, tab_paste = st.tabs(["📁 Upload SRT File", "📋 Paste SRT Text"])

with tab_upload:
    uploaded_file = st.file_uploader("Upload your SRT file", type=["srt", "txt"], label_visibility="collapsed")

with tab_paste:
    pasted_text = st.text_area(
        "Paste your SRT content here",
        height=250,
        placeholder="1\n00:00:01,000 --> 00:00:04,000\nYour subtitle text here\n\n2\n00:00:05,000 --> 00:00:08,000\nNext subtitle block...",
        label_visibility="collapsed",
    )

# Determine srt_content from whichever input was used
srt_content = None
_detected_encoding = None
if uploaded_file:
    _raw_bytes = uploaded_file.read()
    srt_content, _detected_encoding = decode_srt_bytes(_raw_bytes)
    # Apply mojibake fix in case encoding detection wasn't perfect
    srt_content = fix_mojibake(srt_content)
elif pasted_text and pasted_text.strip():
    srt_content = pasted_text.strip()

if not srt_content:
    st.info("📁 Upload an SRT file — or paste SRT text directly using the Paste tab.")
    st.stop()

if not api_keys:
    st.warning("🔑 Enter your OpenRouter API key in the sidebar.")
    st.stop()
if _detected_encoding:
    st.caption(f"📄 Encoding detected: `{_detected_encoding}`")
blocks = parse_srt(srt_content)
if not blocks:
    st.error("❌ No valid subtitle blocks found. Check your SRT format.")
    st.stop()

# ── Chunking ──────────────────────────────────────────────────────────────────
chunks = None
smart_info = None

if chunking_mode == "Smart (AI story analysis)":
    # Cache key — only re-analyze if the SRT content or chunk_size changes
    _cache_key = f"smart_bp_{hash(srt_content)}_{chunk_size}"

    if _cache_key not in st.session_state:
        # First time (or settings changed) — call the API
        if not api_keys:
            st.session_state[_cache_key] = (None, "No API key provided.", None)
        else:
            _status_box = st.empty()
            def _status_cb(msg: str) -> None:
                _status_box.info(f"🧠 {msg}")

            # Smart analysis always uses the first key — it's one lightweight call
            with st.spinner("🧠 Analyzing story structure (this takes ~15–30 s)…"):
                _bp, _err, _method = run_story_analysis(
                    api_keys[0], model, srt_content, chunk_size,
                    status_callback=_status_cb,
                )
            _status_box.empty()
            st.session_state[_cache_key] = (_bp, _err, _method)
    else:
        _bp, _err, _method = st.session_state[_cache_key]

    if _bp:
        chunks = smart_chunk_by_breaks(blocks, _bp)
        _method_badge = "🤖 AI analysis" if _method == "api" else "🔧 Local heuristic"
        smart_info = (
            f"✅ Smart chunking ({_method_badge}): {len(chunks)} narrative segments "
            f"(break points: {_bp})"
        )
    else:
        st.warning(
            f"⚠️ Smart chunking failed — using timestamp gaps instead.\n\n"
            f"**Reason:** {_err or 'Unknown error'}"
        )
        # Clear cache so user can retry after fixing the issue (e.g. rate limit)
        if st.button("🔄 Retry Smart Analysis"):
            del st.session_state[_cache_key]
            st.rerun()

if chunks is None:
    chunks = auto_chunk(blocks, target_chunk_size=chunk_size, gap_threshold=gap_threshold)

if smart_info:
    st.success(smart_info)

# ── Stats row ─────────────────────────────────────────────────────────────────
est_sec = calc_est(chunks, max_parallel)
c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.metric("📦 Total Blocks", len(blocks))
with c2: st.metric("🔢 Chunks",        len(chunks))
with c3: st.metric("📏 Avg Chunk",     len(blocks) // max(len(chunks), 1))
with c4: st.metric("⏱️ Est. Time",    f"~{fmt(est_sec)}")
with c5: st.metric("🚀 Parallel",      max_parallel)

# ── Chunk preview ─────────────────────────────────────────────────────────────
with st.expander("📋 Chunk Preview", expanded=False):
    for i, chunk in enumerate(chunks):
        st.write(
            f"**Chunk {i+1}:** "
            f"Blocks {chunk[0].index}–{chunk[-1].index} "
            f"({len(chunk)} blocks)"
        )

# ── History 4 — block duration preview ───────────────────────────────────────
if visual_style == "history_4":
    with st.expander("⏱️ Block Durations & Word Count Targets (History 4)", expanded=False):
        _preview_blocks = blocks[:25]
        for _b in _preview_blocks:
            _dur = block_duration(_b)
            _twc = get_word_count_for_duration(_dur)
            _txt_preview = _b.text[:55] + ("…" if len(_b.text) > 55 else "")
            st.text(f"Block {_b.index:>4}: {_dur:4.1f}s → {_twc} words  |  \"{_txt_preview}\"")
        if len(blocks) > 25:
            st.caption(f"…and {len(blocks) - 25} more blocks not shown.")

# ── Generate button ───────────────────────────────────────────────────────────
if not st.button("🎬 Generate Prompts", type="primary", use_container_width=True):
    st.stop()

# ── Start generation ──────────────────────────────────────────────────────────
# Pre-populate ALL chunk statuses so render_generation_ui can create placeholders
# immediately on the first rerun, before the background thread has run at all.
_n_keys = len(api_keys)
_init_statuses: dict = {
    1: {
        "status": "queued", "prompts_done": 0, "pct": 0,
        "expected": chunks[0][-1].index - chunks[0][0].index + 1,
        "key_label": "Key 1",
    },
}
for _ci, _ck in enumerate(chunks[1:], 2):
    _aidx  = (_ci - 2) % _n_keys
    _akey  = api_keys[_aidx]
    _klbl  = f"Key {api_keys.index(_akey) + 1}"
    _init_statuses[_ci] = {
        "status": "queued", "prompts_done": 0, "pct": 0,
        "expected": _ck[-1].index - _ck[0].index + 1,
        "key_label": _klbl,
    }

# ── Master Story Plan caching — check session_state before starting thread ────
_srt_hash     = get_srt_blocks_hash(blocks)
_cached_plan  = st.session_state.get(f"master_plan_{_srt_hash}", "")

gen_state: dict = {
    # config
    "api_keys":         api_keys,
    "model":            model,
    "chunks":           chunks,
    "mode_code":        mode_code,
    "visual_style":     visual_style,
    "custom_style_text": custom_style_text,
    "max_parallel":     max_parallel,
    "total_blocks":     len(blocks),
    "expected_block_numbers": {b.index for b in blocks},
    # control
    "stop_requested": False,
    "done":           False,
    "fatal_error":    None,
    "start_time":     time.time(),
    "end_time":       None,
    # threading — protects chunk_statuses from read/write races
    "_lock":          threading.Lock(),
    # live data
    "chunk_statuses":  _init_statuses,
    "chunk1_live":     "",
    "chunk1_response": "",
    "character_cards": "",
    "last_prompt":     "",
    "all_prompts":     [],
    "errors":          [],
    # master story plan
    "srt_hash":           _srt_hash,
    "master_story_plan":  _cached_plan,
    "analysis_status":    "cached" if _cached_plan else "pending",
    "analysis_message":   "Using cached Master Story Plan." if _cached_plan else "",
    "save_master_plan":   False,
}

thread = threading.Thread(target=_generation_thread, args=(gen_state,), daemon=True)

st.session_state.gen_state    = gen_state
st.session_state.gen_thread   = thread
st.session_state.is_generating = True

thread.start()
st.rerun()
