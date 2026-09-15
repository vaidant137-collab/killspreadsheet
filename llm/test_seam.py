"""
Every provider must satisfy the LLMClient seam.

This exists because one did not, and nothing caught it. `structured()` lived on
GeminiClient, so OpenAIClient and OpenRouterClient had no implementation at all —
and the architecture's central claim, that a provider swap costs one config line,
was quietly false for two of the four. It surfaced only when a real deploy tried
to record an extraction run and the honest fallback reported the AttributeError.

Run:  python -m llm.test_seam
"""

from __future__ import annotations

import inspect
import sys

from llm.providers import (AnthropicClient, GeminiClient, OpenAIClient,
                           OpenRouterClient)

PROVIDERS = (AnthropicClient, OpenAIClient, GeminiClient, OpenRouterClient)
REQUIRED = ("structured", "raw_turn")
STRUCTURED_PARAMS = ("system", "user", "schema", "images", "max_tokens")


def main() -> int:
    problems: list[str] = []
    print("\n  LLMClient seam — every provider, every method\n")
    for c in PROVIDERS:
        row = []
        for m in REQUIRED:
            ok = callable(getattr(c, m, None))
            row.append(f"{m}={'ok' if ok else 'MISSING'}")
            if not ok:
                problems.append(f"{c.__name__}.{m} is missing")
        fn = getattr(c, "structured", None)
        if callable(fn):
            params = inspect.signature(fn).parameters
            for p in STRUCTURED_PARAMS:
                if p not in params:
                    problems.append(f"{c.__name__}.structured has no '{p}'")
        print(f"    {c.__name__:18s} {'  '.join(row)}")

    if problems:
        print("\n  FAILED:")
        for p in problems:
            print(f"    · {p}")
        print()
        return 1
    print(f"\n  {len(PROVIDERS)} providers satisfy the seam.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
