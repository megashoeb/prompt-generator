"""OpenRouter API client — streaming, per-key semaphore queue, retry, cancel support."""

import asyncio
import json
import re
import sys
import time

import aiohttp
import requests
from openai import OpenAI

API_URL = "https://openrouter.ai/api/v1/chat/completions"


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY / COMPAT
# ─────────────────────────────────────────────────────────────────────────────

def create_client(api_key: str) -> OpenAI:
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)


def send_chunk_sync(client: OpenAI, model: str, system_prompt: str, user_message: str) -> str:
    """Non-streaming sync call via OpenAI SDK (kept for compatibility)."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        max_tokens=65000,
        temperature=0.7,
    )
    return response.choices[0].message.content


# ─────────────────────────────────────────────────────────────────────────────
# CHUNK 1 — SYNC STREAMING (runs in background thread)
# ─────────────────────────────────────────────────────────────────────────────

def send_chunk_sync_streaming(
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    on_token=None,
) -> str:
    """Streaming HTTP call via requests.
    Calls on_token(delta: str, full_text: str) for every received token.
    Returns the complete assembled text.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 65000,
        "temperature": 0.7,
        "stream": True,
    }

    full_text = ""
    with requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            decoded = raw_line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue
            data_str = decoded[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                delta = data["choices"][0]["delta"].get("content", "")
                if delta:
                    full_text += delta
                    if on_token:
                        on_token(delta, full_text)
            except (json.JSONDecodeError, KeyError, IndexError):
                pass

    return full_text


# ─────────────────────────────────────────────────────────────────────────────
# CHUNKS 2+ — ASYNC STREAMING WITH RETRY + CANCEL
# ─────────────────────────────────────────────────────────────────────────────

async def send_chunk_async_streaming(
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    on_progress=None,
    expected_prompts: int = 1,
    stop_check=None,
    max_retries: int = 3,
) -> dict:
    """Async streaming chunk call with per-prompt progress reporting and retry.

    on_progress(event, prompts_done, pct, msg):
        event = "progress"  | "retrying"

    stop_check() → bool: return True to abort.

    Returns {"content": str}  OR  {"error": str, "cancelled": bool}
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 65000,
        "temperature": 0.7,
        "stream": True,
    }

    for attempt in range(max_retries):
        if stop_check and stop_check():
            return {"error": "Stopped by user.", "cancelled": True}

        full_text          = ""
        prompts_found      = 0
        chars_rx           = 0   # total chars received this attempt
        chars_at_last_ping = 0   # chars when we last fired an estimated-progress ping

        try:
            # Each attempt creates its own session — avoids connection-pool issues
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=600),
                ) as resp:

                    # ── Rate-limit: retry with backoff ───────────────────────
                    if resp.status == 429:
                        if attempt < max_retries - 1:
                            wait = 30 * (attempt + 1)
                            if on_progress:
                                on_progress(
                                    "retrying", prompts_found, 0,
                                    f"Rate limited — retrying in {wait}s… "
                                    f"(attempt {attempt + 2}/{max_retries})",
                                )
                            await asyncio.sleep(wait)
                            continue
                        err = await resp.text()
                        return {"error": f"Rate limited (429) after {max_retries} attempts: {err[:200]}"}

                    if resp.status != 200:
                        err = await resp.text()
                        return {"error": f"API Error {resp.status}: {err[:300]}"}

                    # ── Stream tokens ────────────────────────────────────────
                    async for raw_line in resp.content:
                        if stop_check and stop_check():
                            return {"error": "Stopped by user.", "cancelled": True}

                        decoded = raw_line.decode("utf-8").strip()
                        if not decoded.startswith("data: "):
                            continue
                        data_str = decoded[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0]["delta"].get("content", "")
                            if delta:
                                full_text  += delta
                                chars_rx   += len(delta)
                                new_count   = len(
                                    re.findall(
                                        r"Image Prompt\s+\d+\s*:",
                                        full_text,
                                        re.IGNORECASE,
                                    )
                                )
                                if new_count > prompts_found:
                                    # ── Exact update: a new Image Prompt was found ──
                                    prompts_found = new_count
                                    if on_progress and expected_prompts > 0:
                                        pct = min(
                                            100,
                                            int(prompts_found / expected_prompts * 100),
                                        )
                                        on_progress("progress", prompts_found, pct, "")
                                    chars_at_last_ping = chars_rx
                                elif (
                                    on_progress
                                    and expected_prompts > 0
                                    and (chars_rx - chars_at_last_ping) >= 300
                                ):
                                    # ── Estimated update between prompts ───────────
                                    # Fires every ~300 chars so the progress bar moves
                                    # even before the first complete prompt is found.
                                    # Rough assumption: ~400 chars per prompt.
                                    chars_at_last_ping = chars_rx
                                    char_pct = min(
                                        99,
                                        int(chars_rx / (expected_prompts * 400) * 100),
                                    )
                                    prompt_pct = int(
                                        prompts_found / expected_prompts * 100
                                    )
                                    if char_pct > prompt_pct:
                                        on_progress(
                                            "progress", prompts_found, char_pct, ""
                                        )
                        except (json.JSONDecodeError, KeyError, IndexError):
                            pass

                    return {"content": full_text}

        except asyncio.CancelledError:
            return {"error": "Cancelled.", "cancelled": True}
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(10)
                continue
            return {"error": "Request timed out after 10 minutes."}
        except aiohttp.ClientError as exc:
            if attempt < max_retries - 1:
                await asyncio.sleep(5 * (attempt + 1))
                continue
            return {"error": f"Connection error: {exc}"}
        except Exception as exc:
            return {"error": f"Unexpected error: {exc}"}

    return {"error": f"Failed after {max_retries} attempts."}


# ─────────────────────────────────────────────────────────────────────────────
# API KEY VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

async def _validate_key_async(api_key: str, model: str) -> tuple[bool, str]:
    """Validate one API key with a minimal 1-token test call."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL, headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status == 401:
                    return False, "Invalid or expired key (401 Unauthorized)"
                if resp.status == 429:
                    # Rate-limited but the key itself is valid
                    return True, "Rate limited but key is valid (429)"
                if resp.status in (200, 400):
                    # 400 can mean model/param issue — the key is fine
                    return True, "OK"
                body = await resp.text()
                return False, f"HTTP {resp.status}: {body[:100]}"
    except asyncio.TimeoutError:
        return False, "Validation timed out (20 s)"
    except Exception as exc:
        return False, f"Connection error: {exc}"


def validate_api_keys_sync(
    api_keys: list[str], model: str
) -> tuple[list[str], list[str]]:
    """Synchronously validate a list of API keys.

    Returns:
        valid_keys  — keys that passed validation
        error_msgs  — human-readable failure message for each invalid key
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    async def _run_all():
        return await asyncio.gather(
            *[_validate_key_async(k, model) for k in api_keys]
        )

    loop = asyncio.new_event_loop()
    try:
        results = loop.run_until_complete(_run_all())
    finally:
        loop.close()

    valid_keys, error_msgs = [], []
    for key, (ok, msg) in zip(api_keys, results):
        label = f"…{key[-8:]}" if len(key) >= 8 else key
        if ok:
            valid_keys.append(key)
        else:
            error_msgs.append(f"Key {label}: {msg}")
    return valid_keys, error_msgs


# ─────────────────────────────────────────────────────────────────────────────
# SEMAPHORE QUEUE — per-key concurrency control with 429-pause + rerouting
# ─────────────────────────────────────────────────────────────────────────────

async def process_chunks_queue(
    api_keys: "list[str] | str",
    model: str,
    system_prompt: str,
    chunk_messages: list[dict],
    max_parallel: int = 3,
    on_chunk_update=None,
    gen_state: dict = None,
) -> list[dict]:
    """Process continuation chunks with per-key semaphore queues.

    api_keys: a single key string OR a list of key strings.

    Chunks are assigned to keys round-robin upfront (stored as
    ``cm["api_key"]`` / ``cm["key_label"]`` in each chunk-message dict).

    Each key gets its own asyncio.Semaphore with:
        max_per_key = max(1, max_parallel // len(api_keys))

    When a key hits 429, ``progress_cb`` marks it paused for 30 s.
    Chunks that haven't started yet will be rerouted to the least-loaded
    available key.

    chunk_messages items:
        {"chunk_id": int, "message": str, "expected_prompts": int}
        Optional: "api_key": str, "key_label": str  (set by caller for UI)

    on_chunk_update(chunk_id, event, prompts_done, pct, msg):
        event: "processing" | "progress" | "done" | "error" | "stopped" | "retrying"
        When event == "processing", msg carries the key_label string.
    """
    # ── Normalise to a list ───────────────────────────────────────────────────
    if isinstance(api_keys, str):
        api_keys = [api_keys]
    if not api_keys:
        raise ValueError("No API keys provided.")

    n_keys      = len(api_keys)
    max_per_key = max(1, max_parallel // n_keys)

    # Per-key semaphores
    key_semaphores: dict[str, asyncio.Semaphore] = {
        k: asyncio.Semaphore(max_per_key) for k in api_keys
    }

    # Pause state — key → time.time() when pause expires
    # (single asyncio event-loop, no lock needed)
    key_paused_until: dict[str, float] = {}

    def _is_paused(key: str) -> bool:
        return time.time() < key_paused_until.get(key, 0)

    def _pause_key(key: str, seconds: float = 30.0) -> None:
        key_paused_until[key] = time.time() + seconds

    def _best_key(preferred: str) -> str:
        """Preferred key if not paused, else first non-paused key,
        else the key whose pause expires soonest."""
        if not _is_paused(preferred):
            return preferred
        for k in api_keys:
            if not _is_paused(k):
                return k
        # All keys paused — return the one that unpauses soonest
        return min(api_keys, key=lambda k: key_paused_until.get(k, 0))

    # ── Pre-assign keys round-robin ───────────────────────────────────────────
    for i, cm in enumerate(chunk_messages):
        if "api_key" not in cm:
            cm["api_key"] = api_keys[i % n_keys]
        if "key_label" not in cm:
            try:
                kidx = api_keys.index(cm["api_key"])
            except ValueError:
                kidx = i % n_keys
            cm["key_label"] = f"Key {kidx + 1}"

    results: list[dict | None] = [None] * len(chunk_messages)

    async def process_one(idx: int, cm: dict) -> None:
        chunk_id     = cm["chunk_id"]
        assigned_key = cm["api_key"]
        key_label    = cm.get("key_label", "Key 1")

        # ── Check stop before queuing ─────────────────────────────────────────
        if gen_state and gen_state.get("stop_requested"):
            results[idx] = {"chunk_id": chunk_id, "status": "cancelled", "content": ""}
            if on_chunk_update:
                on_chunk_update(chunk_id, "stopped", 0, 0, "Cancelled before queuing")
            return

        # ── Reroute if assigned key is currently paused ───────────────────────
        active_key = _best_key(assigned_key)
        if _is_paused(active_key):
            # All keys are paused — wait for the soonest to become available
            wait_sec = max(0.5, key_paused_until.get(active_key, 0) - time.time())
            await asyncio.sleep(min(wait_sec + 1.0, 35.0))
            active_key = _best_key(assigned_key)

        # Update label if we switched keys
        if active_key != assigned_key:
            try:
                kidx = api_keys.index(active_key)
            except ValueError:
                kidx = 0
            key_label = f"Key {kidx + 1} (rerouted)"

        # ── Acquire the key's semaphore slot ──────────────────────────────────
        async with key_semaphores[active_key]:

            # Re-check stop after waiting in queue
            if gen_state and gen_state.get("stop_requested"):
                results[idx] = {"chunk_id": chunk_id, "status": "cancelled", "content": ""}
                if on_chunk_update:
                    on_chunk_update(chunk_id, "stopped", 0, 0, "Cancelled while queued")
                return

            # Signal slot acquired; pass key_label via the msg parameter
            if on_chunk_update:
                on_chunk_update(chunk_id, "processing", 0, 0, key_label)

            expected   = cm.get("expected_prompts", 1)
            _akey      = active_key  # capture for the closures below

            def progress_cb(event: str, prompts_done: int, pct: int, msg: str) -> None:
                # Detect 429 → pause this key so future chunks avoid it
                if event == "retrying" and "Rate limited" in msg:
                    _pause_key(_akey, 30.0)
                if on_chunk_update:
                    on_chunk_update(chunk_id, event, prompts_done, pct, msg)

            def stop_check() -> bool:
                return gen_state.get("stop_requested", False) if gen_state else False

            result = await send_chunk_async_streaming(
                _akey,
                model,
                system_prompt,
                cm["message"],
                on_progress=progress_cb,
                expected_prompts=expected,
                stop_check=stop_check,
            )

        # ── Semaphore released — record outcome ───────────────────────────────
        is_cancelled = result.get("cancelled", False)
        is_error     = "error" in result and not is_cancelled

        result["chunk_id"]  = chunk_id
        result["status"]    = (
            "cancelled" if is_cancelled else ("error" if is_error else "success")
        )
        result["key_label"] = key_label
        results[idx] = result

        final_event = "stopped" if is_cancelled else ("error" if is_error else "done")
        if on_chunk_update:
            on_chunk_update(
                chunk_id,
                final_event,
                0,
                0 if is_error else 100,
                result.get("error", ""),
            )

    tasks = [
        asyncio.create_task(process_one(i, cm))
        for i, cm in enumerate(chunk_messages)
    ]
    await asyncio.gather(*tasks, return_exceptions=True)

    return [r for r in results if r is not None]
