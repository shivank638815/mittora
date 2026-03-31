"""
Reply Engine — generates natural meeting responses using LLM.
Does NOT send chat — only returns the reply text.
"""
import logging
import re
from typing import Optional

from .llm_router import LLMRouter

logger = logging.getLogger(__name__)

REPLY_PROMPT = """You are "{user_name}", a participant in an online meeting.
Someone has addressed you or asked you a question. Respond naturally and briefly.

CRITICAL RULES:
- Respond DIRECTLY with your answer. No thinking, no reasoning, no preamble.
- Do NOT use <think> tags or any internal reasoning blocks.
- Keep your response to 1-2 sentences MAXIMUM.
- Be natural, conversational, and helpful.
- Do NOT start with "As {user_name}" or "Sure!" or any filler.
- Do NOT use quotation marks around your response.
- If nothing meaningful requires a response, return exactly: NO_RESPONSE

RECENT CONVERSATION (last 60 seconds):
{recent_context}

EXTENDED CONTEXT (last 5 minutes):
{extended_context}

Your response (direct answer only, no thinking):"""

# Prefixes to strip from LLM output
UNWANTED_PREFIXES = [
    "sure!",
    "sure,",
    "of course!",
    "of course,",
    "well,",
    "okay,",
    "ok,",
    "hey,",
    "hi,",
    "hello,",
]

MAX_REPLY_LENGTH = 200


class ReplyEngine:
    """Generates chat replies using LLM based on meeting context."""

    def __init__(self, llm_router: LLMRouter, user_name: str = "User"):
        self.llm_router = llm_router
        self.user_name = user_name

    def generate(self, recent_context: str, extended_context: str) -> Optional[str]:
        """
        Generate a reply based on meeting context.

        Returns clean reply text, or None if no response needed.
        """
        if not recent_context:
            return None

        prompt = REPLY_PROMPT.format(
            user_name=self.user_name,
            recent_context=recent_context,
            extended_context=extended_context,
        )

        messages = [{"role": "user", "content": prompt}]

        raw_reply = self.llm_router.route("generate_reply", messages)
        if raw_reply is None:
            logger.warning("Reply generation failed — LLM returned None")
            return None

        cleaned = self._clean_reply(raw_reply)
        if not cleaned:
            logger.warning("Reply cleaned to nothing — raw was: %s", raw_reply[:100])
            return None

        logger.info("💬 Generated reply: %s", cleaned)
        return cleaned

    def _clean_reply(self, text: str) -> Optional[str]:
        """Clean and validate LLM reply."""
        text = text.strip()

        # Strip <think>...</think> reasoning blocks (Qwen models) — closed tags
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        # Strip UNCLOSED <think> blocks (model ran out of tokens mid-thinking)
        # This catches: "<think>\nblah blah blah" with no closing tag
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL).strip()

        # Also strip any remaining think-related tags
        text = re.sub(r'</think>', '', text).strip()

        # If only thinking was present with no actual reply
        if not text:
            return None

        # Remove surrounding quotes
        if (text.startswith('"') and text.endswith('"')) or \
           (text.startswith("'") and text.endswith("'")):
            text = text[1:-1].strip()

        # Check for NO_RESPONSE
        if "NO_RESPONSE" in text.upper() or not text:
            return None

        # Strip unwanted prefixes
        text_lower = text.lower()
        for prefix in UNWANTED_PREFIXES:
            if text_lower.startswith(prefix):
                text = text[len(prefix):].strip()
                text_lower = text.lower()

        # Strip "As {name}," prefix pattern
        as_pattern = re.compile(
            rf'^as\s+{re.escape(self.user_name)}\s*[,:]?\s*',
            re.IGNORECASE,
        )
        text = as_pattern.sub('', text).strip()

        # Enforce length limit
        if len(text) > MAX_REPLY_LENGTH:
            truncated = text[:MAX_REPLY_LENGTH]
            last_period = truncated.rfind('.')
            last_question = truncated.rfind('?')
            last_excl = truncated.rfind('!')
            cut_point = max(last_period, last_question, last_excl)
            if cut_point > 20:
                text = truncated[:cut_point + 1]
            else:
                text = truncated.rstrip() + "..."

        if not text or len(text) < 2:
            return None

        return text
