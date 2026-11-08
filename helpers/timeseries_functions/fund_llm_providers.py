import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from typesafe_sdk import Score, TypeSafeClient

from helpers.timeseries_functions.fund_llm_dossier import (
    SYSTEM_PROMPT,
    build_user_prompt,
    dossier_json,
    parse_generative_response,
)

DEFAULT_GENERATIVE_MODELS: dict[str, str] = {
    "openai": "gpt-5.4",
    "anthropic": "claude-sonnet-5-5",
    "google": "gemini-3.8-flash",
    "deepseek": "deepseek-v4-pro",
    "groq": "openai/gpt-oss-120b",
}

TYPESAFE_MODEL = "jev-latest"

_SCORE_LEVELS = [
    "Clear failure on this dimension; the dossier strongly supports the lowest rating.",
    "Mostly weak; several serious issues or contradictions appear in the dossier.",
    "Mixed or ambiguous; some supporting evidence but material weaknesses remain.",
    "Mostly strong; only minor issues and the dossier supports a high rating.",
    "Fully supported; unambiguous evidence in the dossier for the highest rating.",
]

TYPESAFE_SCORE_QUESTIONS: dict[str, Score] = {
    "price_timeseries_reliable": Score(
        instructions=(
            "How reliable is the fund's monthly total-return price series, "
            "including cross-source agreement and internal consistency checks?"
        ),
        criteria=_SCORE_LEVELS,
    ),
    "tracks_sp500_tr": Score(
        instructions=(
            "Does the evidence show the fund is tracking the S&P 500 total-return index "
            "(beta near 1, very low tracking error), not merely correlated with it?"
        ),
        criteria=_SCORE_LEVELS,
    ),
    "active_management": Score(
        instructions=(
            "From return behaviour versus the index alone, how much does the fund look "
            "actively managed (1) versus passive index-like (0)?"
        ),
        criteria=_SCORE_LEVELS,
    ),
    "regression_quality": Score(
        instructions=(
            "Are the OLS regression parameters statistically solid and consistent with "
            "Lipper Funds sheet figures on 3-, 5-, and 10-year horizons?"
        ),
        criteria=_SCORE_LEVELS,
    ),
}


@dataclass
class ProviderResult:
    provider: str
    model: str
    ok: bool
    scores: dict[str, float | None]
    confidences: dict[str, float | None]
    timeseries_interpretation: str | None
    regression_interpretation: str | None
    score_basis: dict[str, str] | None
    error: str | None
    raw: Any = None


def _http_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    *,
    timeout: float = 120.0,
) -> tuple[int, dict | str]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        status = error.code
        text = error.read().decode("utf-8", errors="replace")
        return status, text
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, text


def _clip_score(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


def _generative_result(
    provider: str,
    model: str,
    parsed: dict,
) -> ProviderResult:
    basis = parsed.get("score_basis")
    if basis is not None and not isinstance(basis, dict):
        basis = None
    return ProviderResult(
        provider=provider,
        model=model,
        ok=True,
        scores={
            "price_timeseries_reliable": _clip_score(parsed.get("price_timeseries_reliable")),
            "tracks_sp500_tr": _clip_score(parsed.get("tracks_sp500_tr")),
            "active_management": _clip_score(parsed.get("active_management")),
            "regression_quality": _clip_score(parsed.get("regression_quality")),
        },
        confidences={key: None for key in TYPESAFE_SCORE_QUESTIONS},
        timeseries_interpretation=str(parsed.get("timeseries_interpretation") or ""),
        regression_interpretation=str(parsed.get("regression_interpretation") or ""),
        score_basis={str(k): str(v) for k, v in basis.items()} if basis else None,
        error=None,
        raw=parsed,
    )


def _failed(provider: str, model: str, message: str) -> ProviderResult:
    return ProviderResult(
        provider=provider,
        model=model,
        ok=False,
        scores={key: None for key in TYPESAFE_SCORE_QUESTIONS},
        confidences={key: None for key in TYPESAFE_SCORE_QUESTIONS},
        timeseries_interpretation=None,
        regression_interpretation=None,
        score_basis=None,
        error=message,
    )


def call_openai(dossier: dict, *, api_key: str, model: str) -> ProviderResult:
    user = build_user_prompt(dossier)
    status, data = _http_json(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_completion_tokens": 4096,
        },
        {"Authorization": f"Bearer {api_key}"},
    )
    if status != 200 or not isinstance(data, dict):
        return _failed("openai", model, f"HTTP {status}: {data!s}"[:500])
    try:
        text = data["choices"][0]["message"]["content"]
        return _generative_result("openai", model, parse_generative_response(text))
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as error:
        return _failed("openai", model, str(error))


def call_anthropic(dossier: dict, *, api_key: str, model: str) -> ProviderResult:
    user = build_user_prompt(dossier)
    status, data = _http_json(
        "https://api.anthropic.com/v1/messages",
        {
            "model": model,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user}],
        },
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    if status != 200 or not isinstance(data, dict):
        return _failed("anthropic", model, f"HTTP {status}: {data!s}"[:500])
    try:
        blocks = data["content"]
        text = "".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        )
        return _generative_result("anthropic", model, parse_generative_response(text))
    except (KeyError, json.JSONDecodeError, ValueError) as error:
        return _failed("anthropic", model, str(error))


def call_google(dossier: dict, *, api_key: str, model: str) -> ProviderResult:
    user = build_user_prompt(dossier)
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    status, data = _http_json(
        url,
        {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        {},
    )
    if status != 200 or not isinstance(data, dict):
        return _failed("google", model, f"HTTP {status}: {data!s}"[:500])
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _generative_result("google", model, parse_generative_response(text))
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as error:
        return _failed("google", model, str(error))


def call_openai_compatible(
    dossier: dict,
    *,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
) -> ProviderResult:
    user = build_user_prompt(dossier)
    status, data = _http_json(
        f"{base_url.rstrip('/')}/chat/completions",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
        },
        {"Authorization": f"Bearer {api_key}"},
    )
    if status != 200 or not isinstance(data, dict):
        return _failed(provider, model, f"HTTP {status}: {data!s}"[:500])
    try:
        text = data["choices"][0]["message"]["content"]
        return _generative_result(provider, model, parse_generative_response(text))
    except (KeyError, IndexError, json.JSONDecodeError, ValueError) as error:
        return _failed(provider, model, str(error))


def call_deepseek(dossier: dict, *, api_key: str, model: str) -> ProviderResult:
    return call_openai_compatible(
        dossier,
        provider="deepseek",
        base_url="https://api.deepseek.com",
        api_key=api_key,
        model=model,
    )


def call_groq(dossier: dict, *, api_key: str, model: str) -> ProviderResult:
    return call_openai_compatible(
        dossier,
        provider="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key,
        model=model,
    )


def call_typesafe(dossier: dict, *, api_key: str, model: str = TYPESAFE_MODEL) -> ProviderResult:
    state = dossier_json(dossier)
    try:
        with TypeSafeClient(api_key=api_key) as client:
            response = client.system_one(
                state=state,
                questions=TYPESAFE_SCORE_QUESTIONS,
                model=model,
                timeout=120.0,
            )
    except Exception as error:  # noqa: BLE001 — surface provider errors in notebook
        return _failed("typesafe", model, str(error))

    top_level = len(_SCORE_LEVELS) - 1
    scores: dict[str, float | None] = {}
    confidences: dict[str, float | None] = {}
    for name in TYPESAFE_SCORE_QUESTIONS:
        answer = response.scores.get(name)
        if answer is None:
            scores[name] = None
            confidences[name] = None
            continue
        scores[name] = _clip_score(answer.score / top_level)
        confidences[name] = float(answer.confidence)

    return ProviderResult(
        provider="typesafe",
        model=response.model,
        ok=True,
        scores=scores,
        confidences=confidences,
        timeseries_interpretation=None,
        regression_interpretation=None,
        score_basis=None,
        error=None,
        raw={
            name: {
                "score_0_to_1": scores[name],
                "confidence": confidences[name],
                "probabilities": dict(response.scores[name].probabilities),
            }
            for name in TYPESAFE_SCORE_QUESTIONS
            if name in response.scores
        },
    )


def provider_result_as_json(result: ProviderResult) -> dict[str, Any]:
    """Serializable payload for ``outputs/llm-evaluation-openai.json``."""
    return {
        "provider": result.provider,
        "model": result.model,
        "ok": result.ok,
        "error": result.error,
        "scores": result.scores,
        "score_basis": result.score_basis,
        "timeseries_interpretation": result.timeseries_interpretation,
        "regression_interpretation": result.regression_interpretation,
    }


def env_api_keys() -> dict[str, str | None]:
    return {
        "openai": os.environ.get("OPENAI_API_KEY"),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
        "google": os.environ.get("GOOGLE_API_KEY"),
        "deepseek": os.environ.get("DEEPSEEK_API_KEY"),
        "groq": os.environ.get("GROQ_API_KEY"),
        "typesafe": os.environ.get("TYPESAFE_API_KEY"),
    }


def run_all_providers(
    dossier: dict,
    *,
    models: dict[str, str] | None = None,
    keys: dict[str, str | None] | None = None,
) -> list[ProviderResult]:
    models = models or DEFAULT_GENERATIVE_MODELS
    keys = keys or env_api_keys()
    results: list[ProviderResult] = []

    dispatch: list[tuple[str, str | None, str, Any]] = [
        ("openai", keys.get("openai"), models["openai"], call_openai),
        ("anthropic", keys.get("anthropic"), models["anthropic"], call_anthropic),
        ("google", keys.get("google"), models["google"], call_google),
        ("deepseek", keys.get("deepseek"), models["deepseek"], call_deepseek),
        ("groq", keys.get("groq"), models["groq"], call_groq),
        ("typesafe", keys.get("typesafe"), TYPESAFE_MODEL, call_typesafe),
    ]

    for provider, api_key, model, caller in dispatch:
        if not api_key:
            results.append(_failed(provider, model, "Missing API key in environment"))
            continue
        if provider == "typesafe":
            results.append(caller(dossier, api_key=api_key, model=model))
        else:
            results.append(caller(dossier, api_key=api_key, model=model))

    return results


def scores_comparison_table(results: list[ProviderResult]):
    import pandas as pd

    rows = [
        ("price_timeseries_reliable", "Price series reliable"),
        ("tracks_sp500_tr", "Tracks S&P 500 TR"),
        ("active_management", "Active management (1=active)"),
        ("regression_quality", "Regression quality"),
    ]
    table = pd.DataFrame(index=[label for _, label in rows])
    for result in results:
        column = f"{result.provider}\n({result.model})"
        values = []
        for key, _ in rows:
            score = result.scores.get(key)
            if score is None:
                values.append("—" if not result.ok else "")
                continue
            conf = result.confidences.get(key)
            if conf is not None:
                values.append(f"{score:.2f} (conf {conf:.2f})")
            else:
                values.append(f"{score:.2f}")
        table[column] = values
    return table
