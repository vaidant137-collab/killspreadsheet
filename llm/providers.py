"""
Both providers, behind one interface. Whichever key is present wins.

Neither is imported at module load, so the repo runs end to end with no key at
all — which is what lets the deterministic half of the pipeline be built and
proven before any model is involved.
"""

from __future__ import annotations

import base64
import json
import os
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


# A model call with no timeout can hang a build forever, and one did: a deploy
# printed "recording a real model run" and then sat silent for thirteen minutes
# with no error and no output, because the SDK default is ten minutes per
# attempt and it retries. Extraction is five documents, each of which may make a
# second repair call — so the worst case was over an hour of nothing.
#
# Ninety seconds is generous for one document and short enough that a stuck call
# surfaces as a per-document fallback, which the pipeline already handles and
# reports honestly, instead of as a hung deploy.
CALL_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "90"))

# The analyst gets a tighter one, for a different reason. Extraction runs in a
# build nobody is watching, so ninety seconds costs patience nobody is spending.
# The analyst runs while a buyer stares at the word "thinking" — and eight steps
# at ninety seconds each is twelve minutes of that. Forty-five seconds a call,
# with a wall-clock budget across the whole turn in analyst/loop.py, means the
# screen always says something within about two minutes, even when it has to say
# that the model gave up.
ANALYST_TIMEOUT_S = float(os.getenv("LLM_ANALYST_TIMEOUT_S", "45"))


class AnthropicClient:
    name = "anthropic"
    supports_vision = True

    def __init__(self, model: str = "claude-sonnet-5",
                 timeout: float = CALL_TIMEOUT_S):
        import anthropic
        self._c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"],
                                      timeout=timeout, max_retries=1)
        self.model = model

    def structured(self, *, system, user, schema: type[T], images=None,
                   max_tokens: int = 8000) -> T:
        content: list[dict] = []
        for img in images or []:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.b64encode(img).decode()}})
        content.append({"type": "text", "text": user})

        tool = {
            "name": "record",
            "description": f"Record the extracted data as {schema.__name__}.",
            "input_schema": schema.model_json_schema(),
        }
        r = self._c.messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            tools=[tool], tool_choice={"type": "tool", "name": "record"},
            messages=[{"role": "user", "content": content}],
        )
        for block in r.content:
            if block.type == "tool_use":
                return schema.model_validate(block.input)
        raise RuntimeError("model returned no structured output")


class OpenAIClient:
    name = "openai"
    supports_vision = True
    BASE: str | None = None
    KEY_ENV = "OPENAI_API_KEY"

    def __init__(self, model: str = "gpt-4.1", timeout: float = CALL_TIMEOUT_S):
        from openai import OpenAI
        kw = {"api_key": os.environ[self.KEY_ENV],
              "timeout": timeout, "max_retries": 1}
        if self.BASE:
            kw["base_url"] = self.BASE
        self._c = OpenAI(**kw)
        self.model = model

    def structured(self, *, system, user, schema: type[T], images=None,
                   max_tokens: int = 8000) -> T:
        """One schema-constrained call over the OpenAI wire format.

        This lives HERE, on the base class, rather than on one subclass. It used
        to live on GeminiClient, which meant OpenAIClient and OpenRouterClient
        silently had no `structured` at all — and the seam's whole claim, that a
        new provider costs four lines, was only true because Gemini happened to
        be carrying the implementation for everyone. A deploy found it: real
        extraction had never run on OpenRouter, and the honest fallback said so
        rather than hiding it.

        Not every OpenAI-compatible endpoint supports `json_schema`. Rather than
        require one, try it and fall back to plain JSON mode with the schema in
        the prompt. The output is validated by pydantic either way, so a model
        that ignores the schema fails loudly at the boundary instead of leaking
        a half-shaped object downstream.
        """
        content: list[dict] = [{"type": "text", "text": user}]
        for img in images or []:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": content}]

        try:
            r = self._c.chat.completions.create(
                model=self.model, max_tokens=max_tokens, messages=msgs,
                response_format={"type": "json_schema", "json_schema": {
                    "name": schema.__name__, "strict": False,
                    "schema": schema.model_json_schema()}})
        except Exception:                                    # noqa: BLE001
            msgs[0] = {"role": "system", "content": system +
                       "\n\nReturn ONLY a JSON object matching this schema, with "
                       "no prose and no code fence:\n" +
                       json.dumps(schema.model_json_schema())}
            r = self._c.chat.completions.create(
                model=self.model, max_tokens=max_tokens, messages=msgs,
                response_format={"type": "json_object"})

        return self._validate_or_repair(r, schema, msgs, max_tokens)

    def _validate_or_repair(self, r, schema: type[T], msgs: list,
                            max_tokens: int, _second_try: bool = False) -> T:
        """Validate, and if the shape is wrong, hand the model its own error.

        Three deploys in a row lost five documents each to a different field the
        model had shaped wrongly — a string where a list belonged, a missing
        label, a nested object flattened. Chasing them one at a time costs a ten
        minute build and a live API call per guess, and only ever fixes the
        mismatch you already saw.

        So: show the model exactly what pydantic rejected and let it correct the
        shape. One extra call, once, only on failure. This repairs the CONTAINER
        and never the content — the retry is still validated by the same schema,
        so a model that responds by inventing a plausible number fails here just
        as it would have the first time.
        """
        text = (r.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        try:
            return schema.model_validate(json.loads(text))
        except Exception as e:                                # noqa: BLE001
            if _second_try:
                raise
            repair = msgs + [
                {"role": "assistant", "content": text[:6000]},
                {"role": "user", "content":
                    "That response did not match the required shape. The "
                    f"validator said:\n\n{str(e)[:1500]}\n\nReturn the SAME "
                    "information again, corrected to fit the schema. Do not "
                    "invent, add or change any value — fix only the structure. "
                    "Return JSON only, no prose, no code fence."}]
            r2 = self._c.chat.completions.create(
                model=self.model, max_tokens=max_tokens, messages=repair,
                response_format={"type": "json_object"})
            return self._validate_or_repair(r2, schema, msgs, max_tokens,
                                            _second_try=True)


class GeminiClient(OpenAIClient):
    """Gemini through its OpenAI-compatible endpoint.

    Not a new client -- the same code with a different base URL. Structured
    outputs, function calling and image input all work over this path, which is
    the whole reason the model provider is a seam: adding a third provider cost
    four lines.

    Free tier covers the Flash and Flash-Lite models including image input, so
    the entire pipeline can be developed and rehearsed at zero cost.
    """

    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
    KEY_ENV = "GEMINI_API_KEY"

    def __init__(self, model: str = "gemini-3.5-flash",
                 timeout: float = CALL_TIMEOUT_S):
        super().__init__(model=model, timeout=timeout)


class OpenRouterClient(OpenAIClient):
    """OpenRouter, through its OpenAI-compatible endpoint.

    One key, every provider, pass-through token rates. Worth noting for the
    write-up: this is the fourth provider added to this system and it cost four
    lines, because the model provider was a seam from the first commit rather
    than something retrofitted once a signup went wrong.

    It also decouples the build from any single vendor's onboarding. That is not
    a hypothetical benefit -- it is why this project has a working key tonight.
    """

    name = "openrouter"
    BASE = "https://openrouter.ai/api/v1"
    KEY_ENV = "OPENROUTER_API_KEY"

    def __init__(self, model: str = "z-ai/glm-4.6v",
                 timeout: float = CALL_TIMEOUT_S):
        super().__init__(model=model, timeout=timeout)


def get_client(role: str = "extract"):
    """Pick a provider for this role from whatever key is present.

    Raises only when a model is actually needed — the dataset, normaliser,
    allocator, eval harness and the whole UI run without one.
    """
    from config import LLM_PROVIDER, LLM_PROVIDER_ANALYST
    want = (LLM_PROVIDER_ANALYST or LLM_PROVIDER) if role == "analyst" else LLM_PROVIDER

    have = {"anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "gemini": bool(os.getenv("GEMINI_API_KEY")),
            "openrouter": bool(os.getenv("OPENROUTER_API_KEY"))}
    cls = {"anthropic": AnthropicClient, "openai": OpenAIClient,
           "gemini": GeminiClient, "openrouter": OpenRouterClient}

    if want in cls:
        if not have[want]:
            raise RuntimeError(f"{want} selected for '{role}' but its API key is not set.")
        # Extraction is the expensive half (66% image tokens, ~15k output per
        # pass) and is schema-constrained, so a cheaper model has little room to
        # go wrong. The analyst is what anyone actually watches. Two models, one
        # provider, set independently.
        # Extraction is vision-heavy and schema-constrained; the analyst is what
        # anyone watches. Same provider, two models, set independently.
        prefix = {"anthropic": "ANTHROPIC", "openrouter": "OPENROUTER",
                  "gemini": "GEMINI", "openai": "OPENAI"}[want]
        env = f"{prefix}_ANALYST_MODEL" if role == "analyst" else f"{prefix}_EXTRACT_MODEL"
        m = os.getenv(env)
        t = ANALYST_TIMEOUT_S if role == "analyst" else CALL_TIMEOUT_S
        return cls[want](model=m, timeout=t) if m else cls[want](timeout=t)
    # auto: cheapest capable provider first, so a spare key is never the
    # expensive one by accident
    t = ANALYST_TIMEOUT_S if role == "analyst" else CALL_TIMEOUT_S
    for name in ("openrouter", "gemini", "anthropic", "openai"):
        if have[name]:
            return cls[name](timeout=t)
    raise RuntimeError(
        "No model API key found. Set OPENROUTER_API_KEY, GEMINI_API_KEY, "
        "ANTHROPIC_API_KEY or OPENAI_API_KEY in .env.\n"
        "Everything except extraction and the analyst runs without one:\n"
        "  python -m data.build_ground_truth\n"
        "  python -m tools.render_all\n"
        "  python -m normalize.engine --self-test\n"
        "  python -m allocate.subsets --self-test")


# ---------------------------------------------------------------------------
# Raw multi-turn tool calling, for the analyst loop. Kept separate from
# `structured()` because extraction wants exactly one shape back and nothing
# else, while the analyst needs a conversation.
# ---------------------------------------------------------------------------

def _anthropic_raw(self, *, system, messages, tools, max_tokens=4000):
    msgs = []
    for m in messages:
        if m.get("_tool_results"):
            msgs.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                for r in m["content"]]})
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    r = self._c.messages.create(model=self.model, max_tokens=max_tokens,
                                system=system, tools=tools, messages=msgs)
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    calls = [{"id": b.id, "name": b.name, "input": b.input}
             for b in r.content if b.type == "tool_use"]
    return {"text": text, "tool_calls": calls, "content": r.content}


def _openai_raw(self, *, system, messages, tools, max_tokens=4000):
    msgs = [{"role": "system", "content": system}]
    for m in messages:
        if m.get("_tool_results"):
            for r in m["content"]:
                msgs.append({"role": "tool", "tool_call_id": r["id"],
                             "content": r["content"]})
        elif m["role"] == "assistant" and hasattr(m["content"], "tool_calls"):
            # The loop hands back `reply["content"]` verbatim, which on this
            # path is the provider's own ChatCompletionMessage. Passing it
            # through as `content` buries tool_calls one level down, so the
            # assistant turn goes up with NO tool_calls field and the following
            # role:"tool" message references an id that, as far as the API can
            # see, was never issued. The observed failure is not an error: the
            # model returns an empty completion, the loop sees no text and no
            # tool calls, and the turn ends having said nothing. Re-send the
            # assistant turn in the shape the API documents.
            c = m["content"]
            turn = {"role": "assistant", "content": c.content or ""}
            if c.tool_calls:
                turn["tool_calls"] = [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in c.tool_calls]
            msgs.append(turn)
        else:
            msgs.append({"role": m["role"], "content": m["content"]})
    spec = [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": t["input_schema"]}} for t in tools]
    r = self._c.chat.completions.create(model=self.model, max_tokens=max_tokens,
                                        messages=msgs, tools=spec)
    m = r.choices[0].message
    calls = [{"id": c.id, "name": c.function.name,
              "input": json.loads(c.function.arguments or "{}")}
             for c in (m.tool_calls or [])]
    return {"text": (m.content or "").strip(), "tool_calls": calls, "content": m}


AnthropicClient.raw_turn = _anthropic_raw
OpenAIClient.raw_turn = _openai_raw
# GeminiClient subclasses OpenAIClient, so it inherits raw_turn unchanged.
