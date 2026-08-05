"""The agent loop, running on Groq (free) via its OpenAI-compatible API.

Only this file is provider-specific. The tools, handlers, PostGIS layer, and
frontend are unchanged — we convert the existing tool schemas (Anthropic-style
name/description/input_schema in tools.py) into OpenAI function-calling format
here, and translate the tool-use loop to chat-completions semantics.

To switch backends, change OPENAI_BASE_URL + the API key env var:
  * Groq        : https://api.groq.com/openai/v1            (GROQ_API_KEY)
  * Gemini      : https://generativelanguage.googleapis.com/v1beta/openai/  (GEMINI_API_KEY)
  * Ollama      : http://localhost:11434/v1                 (any key)
  * Anthropic   : revert to the anthropic SDK (see git history)
"""
import json
import os

import asyncio

import asyncpg
from openai import AsyncOpenAI, BadRequestError, RateLimitError

from .tools import HANDLERS, TOOLS

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_STEPS = 8  # guard against runaway tool loops
# A public connection can be held open indefinitely; cap the history it accrues
# so per-call token cost stays bounded.
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "40"))
# Groq's free tier allows 12k tokens/minute and one call costs ~2.3k, so a busy
# moment returns 429. Wait briefly and retry rather than surfacing a raw error.
_RATE_LIMIT_MAX_WAIT = float(os.environ.get("RATE_LIMIT_MAX_WAIT", "8"))

SYSTEM = """You are an analyst's assistant for a map of renewable-energy projects across South West England (Bristol/Avon, Bath, Somerset, North Somerset, Gloucestershire, Wiltshire, Dorset, Devon, Cornwall). The data is the public DESNZ Renewable Energy Planning Database (REPD).

Each project has: a technology (solar_ground, solar_rooftop, wind, bess, hydro, biomass), capacity in MW, a development status (operational / under_construction / awaiting_construction / submitted), an operator, and a county. Coordinates are real REPD site locations (WGS84).

You act on the map by calling tools:
- Data tools (search_projects, projects_within_distance, nearest_projects, area_summary, show_footprint, geocode_place) query PostGIS and render results. On the map: colour = technology, size = capacity (MW).
- View tools (fly_to, set_layer_color, set_layer_visibility, clear_map) move the camera or restyle.

Conventions:
- For "solar" (unspecified), use technology="solar" in ONE call — it covers both ground and rooftop. Only use solar_ground or solar_rooftop when the user is specific.
- "Development stage" / "pipeline" maps to the `status` filter (operational / under_construction / awaiting_construction / submitted). Use it when the user screens by how far along a project is.
- Pass place/county names straight to a tool's `place` or `area` argument in ONE call (e.g. projects_within_distance(technology="solar_ground", place="Bath", radius_meters=15000)). The server geocodes them. Do NOT geocode separately then copy coordinates — that is error-prone. Never invent coordinates.
- To show a ground-mount solar site's area, use show_footprint with its title.
- Data tools already render and fit the map — don't also call fly_to unless the user asks to move the camera.
- Be concise: after acting, give a one-sentence confirmation."""

# Anthropic-style schemas -> OpenAI function-calling format.
OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in TOOLS
]


def make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=BASE_URL,
        api_key=os.environ.get("GROQ_API_KEY", os.environ.get("OPENAI_API_KEY", "")),
        # The SDK's own retry ladder silently sits in backoff for minutes on a
        # 429; _complete() handles retries with a bounded wait instead.
        max_retries=0,
        timeout=30.0,
    )


def _status_text(name: str, args: dict) -> str:
    tech = args.get("technology", "projects")
    return {
        "geocode_place": f"Looking up “{args.get('query', '')}”…",
        "search_projects": f"Searching {tech}…",
        "projects_within_distance": f"Finding {tech} within {args.get('radius_meters', '?')} m…",
        "nearest_projects": f"Finding nearest {tech}…",
        "area_summary": "Aggregating by county…",
        "show_footprint": "Drawing the site footprint…",
        "fly_to": "Moving the map…",
        "set_layer_color": "Recolouring a layer…",
        "set_layer_visibility": "Toggling a layer…",
        "clear_map": "Clearing the map…",
    }.get(name, f"Running {name}…")


class ModelBusy(Exception):
    """The upstream model is rate-limited and retrying didn't clear it."""


def _retry_after(exc: RateLimitError) -> float:
    """Seconds Groq asks us to wait, clamped so a user isn't left hanging."""
    response = getattr(exc, "response", None)
    value = response.headers.get("retry-after") if response is not None else None
    try:
        return min(float(value), _RATE_LIMIT_MAX_WAIT)
    except (TypeError, ValueError):
        return 3.0


def _is_tool_format_error(exc: BadRequestError) -> bool:
    # Groq returns 400 `tool_use_failed` when Llama emits a malformed tool call
    # (e.g. "<function=search_pois ...>" instead of valid JSON). It's stochastic,
    # so a retry usually succeeds.
    return "tool_use_failed" in str(exc)


async def _complete(client, history):
    """Call the model, retrying malformed-tool-call errors and 429s."""
    last_exc = None
    rate_limited = 0
    for _ in range(4):
        try:
            return await client.chat.completions.create(
                model=MODEL,
                # Groq checks its rate limit against prompt + max_tokens, not
                # against what the model actually returns, so an oversized
                # max_tokens reserves quota we never use and triggers 429s
                # early. Replies here are a one-sentence confirmation plus tool
                # calls — measured at ~33 completion tokens — so 512 is ample
                # and cuts the reserved cost per call by roughly 1.5k tokens.
                max_tokens=512,
                temperature=0.2,  # steadier tool-call formatting
                messages=[{"role": "system", "content": SYSTEM}] + history,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
            )
        except RateLimitError as exc:
            rate_limited += 1
            if rate_limited > 2:
                raise ModelBusy from exc
            await asyncio.sleep(_retry_after(exc))
        except BadRequestError as exc:
            if _is_tool_format_error(exc):
                last_exc = exc
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise ModelBusy


def _trim(history: list[dict]) -> None:
    """Drop the oldest turns once history is too long.

    Trims to a `user` boundary so an assistant message carrying tool_calls is
    never separated from the tool results that answer it — the API rejects that.
    """
    while len(history) > MAX_HISTORY_MESSAGES:
        del history[0]
        while history and history[0].get("role") != "user":
            del history[0]


async def run_turn(client, history, user_text, send, pool: asyncpg.Pool) -> None:
    """Run one user turn to completion, mutating `history` in place.

    `history` holds OpenAI-format messages (user / assistant / tool); the system
    prompt is prepended per request and not stored.
    """
    _trim(history)
    history.append({"role": "user", "content": user_text})

    for _ in range(MAX_STEPS):
        try:
            resp = await _complete(client, history)
        except ModelBusy:
            await send({"type": "error",
                        "text": "The free model tier is busy right now — "
                                "give it a few seconds and ask again."})
            if history and history[-1].get("role") == "user":
                history.pop()
            break
        except BadRequestError as exc:
            if _is_tool_format_error(exc):
                await send({"type": "assistant_text",
                            "text": "Sorry — I garbled that request. Could you rephrase it?"})
                # Drop the dangling user turn so it doesn't poison the next message.
                if history and history[-1].get("role") == "user":
                    history.pop()
                break
            raise
        msg = resp.choices[0].message

        # Record the assistant turn (with any tool calls) so the model keeps context.
        tool_calls = msg.tool_calls or []
        entry: dict = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ]
        history.append(entry)

        if msg.content and msg.content.strip():
            await send({"type": "assistant_text", "text": msg.content})

        if not tool_calls:
            break

        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):  # model may emit "null" for no-arg calls
                args = {}
            await send({"type": "status", "text": _status_text(name, args)})
            handler = HANDLERS.get(name)
            try:
                if handler is None:
                    result = f"Error: unknown tool '{name}'."
                else:
                    result = await handler(args, send, pool)
            except Exception as exc:  # surface to the model so it can recover
                result = f"Error running {name}: {exc}"
            history.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    else:
        await send({"type": "assistant_text",
                    "text": "(Stopped after several steps — ask me to continue if needed.)"})

    await send({"type": "done"})
