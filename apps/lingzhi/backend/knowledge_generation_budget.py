"""Knowledge extraction shares a model window, not a handout-writing input cap."""
from __future__ import annotations

from dataclasses import dataclass
import math

from ai_base import AIBase
from course_generation_budget import CourseGenerationBudget, _env_int


@dataclass(frozen=True)
class KnowledgeTreeBudget:
    context_window_tokens: int
    context_reserve_tokens: int
    max_input_tokens: int
    max_input_chars: int
    max_output_tokens: int
    request_timeout_seconds: int

    @classmethod
    def from_env(cls) -> KnowledgeTreeBudget:
        shared = CourseGenerationBudget.from_env()
        output = _env_int('COURSE_KNOWLEDGE_TREE_MAX_OUTPUT_TOKENS', 32000, minimum=1024, maximum=32000)
        available = shared.context_window_tokens - output - shared.context_reserve_tokens
        tokens = min(available, _env_int('COURSE_KNOWLEDGE_TREE_MAX_INPUT_TOKENS', available,
            minimum=1, maximum=shared.context_window_tokens))
        char_capacity = max(1, math.ceil(max(0, tokens) * 3.2))
        return cls(shared.context_window_tokens, shared.context_reserve_tokens, tokens,
            _env_int('COURSE_KNOWLEDGE_TREE_MAX_INPUT_CHARS', char_capacity, minimum=1, maximum=char_capacity),
            output, _env_int('COURSE_KNOWLEDGE_TREE_REQUEST_TIMEOUT_SECONDS', 600, minimum=30, maximum=1800))

    def describe(self, prompt: str, system: str) -> dict[str, int | str]:
        return {'schema_version': 'knowledge_tree_request_budget_v1',
            'estimated_input_tokens': AIBase.estimate_request_tokens(prompt, system),
            'input_chars': len(prompt) + len(system), 'max_input_tokens': self.max_input_tokens,
            'max_input_chars': self.max_input_chars, 'max_output_tokens': self.max_output_tokens,
            'context_window_tokens': self.context_window_tokens, 'context_reserve_tokens': self.context_reserve_tokens}

    def validate(self, prompt: str, system: str) -> int:
        # The input estimate includes the final system and user messages. Output
        # and message framing keep their own space even with a generous override.
        return AIBase.validate_request_budget(prompt, system, self.max_input_tokens, self.max_input_chars)

    def call_options(self) -> dict[str, int]:
        return {'max_input_tokens': self.max_input_tokens, 'max_input_chars': self.max_input_chars,
            'max_tokens': self.max_output_tokens, 'request_timeout_seconds': self.request_timeout_seconds}
