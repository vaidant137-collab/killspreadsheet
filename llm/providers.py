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

    def __init__(self, model: str = "claude-sonnet-4-6"):
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

    def __init__(self, model: str = "gpt-4.1"):
        from openai import OpenAI
        self._c = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model

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


def get_client():
    """Pick a provider from whatever key is present. Raises only when a model
    is actually needed — the dataset, normaliser, allocator and eval harness all
    run without one."""
    from config import LLM_PROVIDER
    want = LLM_PROVIDER
    has_a = bool(os.getenv("ANTHROPIC_API_KEY"))
    has_o = bool(os.getenv("OPENAI_API_KEY"))
    if want == "anthropic" or (want == "auto" and has_a):
        return AnthropicClient()
    if want == "openai" or (want == "auto" and has_o):
        return OpenAIClient()
    raise RuntimeError(
        "No model API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env.\n"
        "Everything except extraction and the analyst runs without one:\n"
        "  python -m data.build_ground_truth\n"
        "  python -m tools.render_all\n"
        "  python -m normalize.engine --self-test\n"
        "  python -m allocate.subsets --self-test")
