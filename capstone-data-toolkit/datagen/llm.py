"""Provider-agnostic LLM client used to synthesise corpus content.

Deliberately dependency-light: plain `requests` rather than an SDK, so the
toolkit installs in seconds and does not fight with whatever client library
your capstone itself pins. Swap in LiteLLM if you prefer -- the call surface
here (`complete`, `complete_json`) is one thin adapter away.
"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Any

import requests

from .config import Provider, settings


class LLMError(RuntimeError):
    """Raised when a provider call fails after all retries."""


class ContentBlocked(LLMError):
    """The provider refused to generate this specific content.

    Distinct from a transport failure: retrying will not help, and the right
    response is to skip this document and tell the user which one, rather than
    aborting a 50-document run.
    """


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> Any:
    """Pull a JSON value out of a model response.

    Models wrap JSON in prose or fences even when told not to. Try the cheap
    parse first, then the fenced block, then the widest brace/bracket span.
    """
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = _JSON_FENCE.search(text)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise LLMError(f"No parseable JSON in response: {text[:400]!r}")


def _call_gemini(
    prompt: str, system: str | None, temperature: float, model: str | None = None
) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model or settings.gemini_model}:generateContent"
    )
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 8192},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}

    resp = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        },
        json=payload,
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    # A blocked prompt returns no candidates at all, only promptFeedback. This
    # is not rare: clinical escalation standards and hazardous-procedure SOPs
    # trip safety classifiers regularly. Retrying is pointless, so raise a
    # ContentBlocked that the caller can report and skip.
    feedback = data.get("promptFeedback") or {}
    if feedback.get("blockReason"):
        raise ContentBlocked(
            f"Gemini blocked the prompt (reason: {feedback['blockReason']})"
        )

    candidates = data.get("candidates") or []
    if not candidates:
        raise ContentBlocked(
            "Gemini returned no candidates. This usually means a safety filter "
            "blocked the request."
        )

    candidate = candidates[0]
    finish = candidate.get("finishReason")
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts)

    if not text.strip() and finish in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT"):
        raise ContentBlocked(f"Gemini stopped generating (finishReason: {finish})")

    return text


def _call_openrouter(prompt: str, system: str | None, temperature: float) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={
            "model": settings.openrouter_model,
            "messages": messages,
            "temperature": temperature,
        },
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ContentBlocked(f"OpenRouter returned no choices: {str(data)[:200]}")
    return (choices[0].get("message") or {}).get("content") or ""


def _call_ollama(prompt: str, system: str | None, temperature: float) -> str:
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    resp = requests.post(
        f"{settings.ollama_host}/api/chat",
        json={
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=settings.request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message") or {}).get("content") or ""


_DISPATCH = {
    "gemini": _call_gemini,
    "openrouter": _call_openrouter,
    "ollama": _call_ollama,
}


# Transient, server-side or quota conditions: always worth waiting out.
_RETRYABLE = {408, 429, 500, 502, 503, 504}

# Run-wide state. Once the primary Gemini model has been abandoned for the
# fallback, every later call goes straight to the fallback instead of paying
# the same failed-retry toll again on each of the ~100 calls in a run.
_state: dict[str, Any] = {"model": None, "last_call": 0.0}


def _error_info(resp: requests.Response | None) -> tuple[float | None, str]:
    """(seconds the provider asked us to wait, quota id that was exceeded).

    Gemini's 429 body carries a RetryInfo detail ("retryDelay": "37s") and a
    QuotaFailure detail naming the limit (e.g. ...PerMinute... vs ...PerDay...).
    Other providers use the standard Retry-After header.
    """
    if resp is None:
        return None, ""
    delay: float | None = None
    quota = ""
    header = resp.headers.get("Retry-After")
    if header:
        try:
            delay = float(header)
        except ValueError:
            pass
    try:
        for detail in (resp.json().get("error") or {}).get("details") or []:
            if detail.get("retryDelay"):
                delay = float(str(detail["retryDelay"]).rstrip("s"))
            for v in detail.get("violations") or []:
                quota = quota or v.get("quotaId") or v.get("quotaMetric") or ""
    except (ValueError, AttributeError):
        pass
    return delay, quota


def _pace() -> None:
    """Keep under the free tier's requests-per-minute limit proactively."""
    gap = settings.min_request_interval - (time.monotonic() - _state["last_call"])
    if gap > 0:
        time.sleep(gap)
    _state["last_call"] = time.monotonic()


def complete(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = None,
    provider: Provider | None = None,
) -> str:
    """Single completion with pacing, backoff, jitter and model fallback.

    Free tiers rate-limit aggressively (429) and Google's Flash models are
    frequently overloaded at peak hours (503). Strategy for Gemini:
      * pace calls `min_request_interval` apart to stay under the RPM limit;
      * on 429 switch to `gemini_fallback_model` at once (separate quota);
      * on repeated 503 switch after half the retry budget;
      * once switched, stay on the fallback for the rest of the run;
      * a *daily* quota cannot be waited out, so fail fast with a clear hint.
    """
    name = provider or settings.provider
    fn = _DISPATCH[name]
    temp = settings.temperature if temperature is None else temperature
    is_gemini = name == "gemini"
    fallback = settings.gemini_fallback_model if is_gemini else ""
    if fallback == settings.gemini_model:
        fallback = ""  # primary already is the fallback; nothing to switch to
    switch_at = max(1, settings.max_retries // 2)
    last: Exception | None = None

    for attempt in range(settings.max_retries):
        model = _state["model"] if is_gemini else None
        label = model or (settings.gemini_model if is_gemini else name)
        server_delay = None
        if is_gemini:
            _pace()
        try:
            out = fn(prompt, system, temp, model) if is_gemini else fn(prompt, system, temp)
            if out and out.strip():
                return out
            last = LLMError("Empty completion")
        except ContentBlocked:
            raise  # retrying a refusal just burns quota
        except requests.HTTPError as exc:
            last = exc
            resp = exc.response
            status = resp.status_code if resp is not None else 0
            if status == 404 and model and model == fallback:
                print(f"    [llm] fallback model {fallback!r} not found; ignoring it")
                _state["model"] = None
                fallback = ""
                continue
            if status not in _RETRYABLE:  # 400/401/403/404 etc: fix config instead
                raise LLMError(f"Provider rejected request ({status}): {exc}") from exc
            server_delay, quota = _error_info(resp)
            last = LLMError(f"HTTP {status} from {label}" + (f" [{quota}]" if quota else ""))

            on_primary = is_gemini and fallback and _state["model"] is None
            if on_primary and (status == 429 or attempt + 1 >= switch_at):
                print(f"    [llm] {label} returned {status}; switching to "
                      f"{fallback} for the rest of this run")
                _state["model"] = fallback
                continue  # different model, different quota: try it now
            if status == 429 and "PerDay" in quota:
                raise LLMError(
                    f"Daily free-tier quota exhausted on {label} ({quota}). "
                    "Waiting will not help: re-run after the quota resets "
                    "(midnight US Pacific), use another API key, or switch with "
                    "--provider openrouter / --provider ollama. Completed "
                    "documents are kept."
                ) from exc
        except requests.RequestException as exc:
            last = exc

        if attempt == settings.max_retries - 1:
            break
        backoff = min(settings.max_backoff, 2 ** (attempt + 1)) + random.uniform(0, 2)
        sleep_for = max(backoff, (server_delay or 0) + random.uniform(0.5, 2))
        print(f"    [llm] attempt {attempt + 1}/{settings.max_retries}: {last}; "
              f"retrying in {sleep_for:.0f}s")
        time.sleep(sleep_for)

    raise LLMError(f"Failed after {settings.max_retries} attempts: {last}")


def complete_json(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = None,
) -> Any:
    """Completion that must parse as JSON, with one corrective re-ask."""
    instruction = (
        "Respond with raw JSON only. No prose, no markdown fences, no preamble."
    )
    sys_prompt = f"{system}\n\n{instruction}" if system else instruction

    raw = complete(prompt, system=sys_prompt, temperature=temperature)
    try:
        return _extract_json(raw)
    except LLMError:
        repair = (
            "The following was supposed to be valid JSON but is not. "
            "Return the corrected JSON and nothing else.\n\n" + raw[:6000]
        )
        return _extract_json(complete(repair, system=instruction, temperature=0.0))
