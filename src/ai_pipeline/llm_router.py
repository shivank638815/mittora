"""
LLM Router — routes tasks to appropriate LLM models via the unified Groq client.
No business logic — only routing, model selection, and fallback handling.
"""
import logging
import os
from typing import Optional

from .groq_client import GroqClient

logger = logging.getLogger(__name__)

# Default model assignments
DEFAULT_MODELS = {
    "trigger_check": "llama-3.1-8b-instant",
    "generate_reply": "qwen/qwen3-32b",
    "qa": "openai/gpt-oss-120b",
}

# Fallback chains — if primary model fails, try these in order
FALLBACK_CHAINS = {
    "trigger_check": ["llama-3.1-8b-instant", "qwen/qwen3-32b"],
    "generate_reply": ["qwen/qwen3-32b", "llama-3.1-8b-instant"],
    "qa": ["openai/gpt-oss-120b", "qwen/qwen3-32b"],
}

# Temperature settings per task type
TASK_TEMPERATURES = {
    "trigger_check": 0.1,   # Deterministic yes/no
    "generate_reply": 0.6,  # Natural variation
    "qa": 0.3,              # Accurate but not rigid
}

# Max token limits per task type
TASK_MAX_TOKENS = {
    "trigger_check": 16,    # Just "YES" or "NO"
    "generate_reply": 512,  # Room for reply even if thinking leaks
    "qa": 1024,             # Detailed answers
}


class LLMRouter:
    """Routes tasks to the appropriate LLM model with fallback handling."""

    def __init__(self, groq_client: GroqClient):
        self.groq_client = groq_client

        # Load model assignments from environment or use defaults
        self.models = {
            "trigger_check": os.getenv("LLM_TRIGGER_MODEL", DEFAULT_MODELS["trigger_check"]),
            "generate_reply": os.getenv("LLM_REPLY_MODEL", DEFAULT_MODELS["generate_reply"]),
            "qa": os.getenv("LLM_QA_MODEL", DEFAULT_MODELS["qa"]),
        }

        logger.info(
            "🧠 LLM Router initialized — trigger: %s, reply: %s, qa: %s",
            self.models["trigger_check"],
            self.models["generate_reply"],
            self.models["qa"],
        )

    def route(self, task_type: str, messages: list[dict]) -> Optional[str]:
        """
        Route a task to the appropriate LLM model.

        Args:
            task_type: One of 'trigger_check', 'generate_reply', 'qa'
            messages: Chat messages in OpenAI format [{"role": ..., "content": ...}]

        Returns:
            LLM response text, or None if all models fail.
        """
        if task_type not in self.models:
            logger.error("Unknown task type: %s", task_type)
            return None

        temperature = TASK_TEMPERATURES.get(task_type, 0.3)
        max_tokens = TASK_MAX_TOKENS.get(task_type, 256)

        # Build fallback chain with configured primary model first
        primary = self.models[task_type]
        fallbacks = FALLBACK_CHAINS.get(task_type, [primary])

        # Ensure primary is first in the chain
        chain = [primary] + [m for m in fallbacks if m != primary]

        for model in chain:
            logger.debug("Routing '%s' to model: %s", task_type, model)

            result = self.groq_client.chat_completion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if result is not None:
                logger.debug("'%s' completed by %s: %s", task_type, model, result[:80])
                return result

            logger.warning("Model %s failed for '%s', trying fallback...", model, task_type)

        logger.error("All models failed for task '%s'", task_type)
        return None
