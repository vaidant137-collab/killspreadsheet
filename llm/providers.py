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


class AnthropicClient:
    name = "anthropic"
    supports_vision = True

    def __init__(self, model: str = "claude-sonnet-5"):
        import anthropic
        self._c = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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

    def __init__(self, model: str = "gpt-4.1"):
        from openai import OpenAI
        kw = {"api_key": os.environ[self.KEY_ENV]}
        if self.BASE:
            kw["base_url"] = self.BASE
        self._c = OpenAI(**kw)
        self.model = model


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

    def __init__(self, model: str = "gemini-3.5-flash"):
        super().__init__(model=model)

    def structured(self, *, system, user, schema: type[T], images=None,
                   max_tokens: int = 8000) -> T:
        content: list[dict] = [{"type": "text", "text": user}]
        for img in images or []:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        r = self._c.chat.completions.create(
            model=self.model, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {
                "name": schema.__name__, "strict": False,
                "schema": schema.model_json_schema()}},
        )
        return schema.model_validate(json.loads(r.choices[0].message.content))


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

    def __init__(self, model: str = "z-ai/glm-4.6v"):
        super().__init__(model=model)


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
        return cls[want](model=m) if m else cls[want]()
    # auto: cheapest capable provider first, so a spare key is never the
    # expensive one by accident
    for name in ("openrouter", "gemini", "anthropic", "openai"):
        if have[name]:
            return cls[name]()
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
