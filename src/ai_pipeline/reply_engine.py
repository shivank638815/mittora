"""
Reply Engine — generates natural meeting responses using LLM.
Builds multi-turn role-based messages so the LLM remembers past Q&A
and always prioritizes the latest question.
Does NOT send chat — only returns the reply text.
"""
import logging
import re
from typing import Optional

from .llm_router import LLMRouter

logger = logging.getLogger(__name__)

# System prompt — defines persona and rules (sent as "system" role)
# Profile fields are injected dynamically when available.
SYSTEM_PROMPT = """You are "{user_name}", a participant in an online meeting.
{profile_block}
Someone has addressed you or asked you a question. Respond naturally and briefly.

CRITICAL RULES:
- Respond DIRECTLY with your answer. No thinking, no reasoning, no preamble.
- Do NOT use <think> tags or any internal reasoning blocks.
- Keep your response to 1-2 sentences MAXIMUM.
- Be natural, conversational, and helpful.
- Do NOT start with "As {user_name}" or "Sure!" or any filler.
- Do NOT use quotation marks around your response.
- ALWAYS answer the LATEST question. Do NOT repeat previous answers.
- If nothing meaningful requires a response, return exactly: NO_RESPONSE"""

# Extended context preamble — sent as a system-level summary
CONTEXT_PREAMBLE = """MEETING BACKGROUND (last 5 minutes of conversation for reference):
{extended_context}"""

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
    """Generates chat replies using multi-turn role-based LLM messages."""

    def __init__(
        self,
        llm_router: LLMRouter,
        user_name: str = "User",
        user_role: str = "",
        meeting_purpose: str = "",
        subject_domain: str = "",
        response_style: str = "Casual",
    ):
        self.llm_router = llm_router
        self.user_name = user_name

        # Build profile block from non-empty fields
        profile_lines = []
        if user_role:
            profile_lines.append(f"Your role/designation: {user_role}")
        if meeting_purpose:
            profile_lines.append(f"Meeting type: {meeting_purpose}")
        if subject_domain:
            profile_lines.append(f"Your subject expertise: {subject_domain}")
        if response_style:
            profile_lines.append(f"Response style: {response_style}")
        self._profile_block = "\n".join(profile_lines)

        if self._profile_block:
            logger.info("👤 Profile loaded → %s", self._profile_block.replace('\n', ' | '))

    def generate(
        self,
        recent_context: str,
        extended_context: str,
        current_trigger_text: str = "",
        conversation_history: list[dict] | None = None,
    ) -> Optional[str]:
        """
        Generate a reply using multi-turn role-based messages.

        Args:
            recent_context: Plain text transcript of last 60s (fallback context).
            extended_context: Plain text transcript of last 5 min (system summary).
            current_trigger_text: The specific STT chunk that triggered this reply.
            conversation_history: Role-tagged list [{"role":"user"|"assistant", "content":...}]
                                  from TranscriptManager.get_conversation_history().

        Returns clean reply text, or None if no response needed.
        """
        if not recent_context and not current_trigger_text:
            return None

        messages = self._build_messages(
            recent_context, extended_context,
            current_trigger_text, conversation_history or [],
        )

        logger.debug(
            "🧠 LLM messages (%d turns): %s",
            len(messages),
            [(m["role"], m["content"][:60]) for m in messages],
        )

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

    def _build_messages(
        self,
        recent_context: str,
        extended_context: str,
        current_trigger_text: str,
        history: list[dict],
    ) -> list[dict]:
        """
        Build a multi-turn message list with proper roles:
          1. system  → persona + rules
          2. system  → extended context (background summary)
          3. user/assistant pairs → prior Q&A history
          4. user    → CURRENT question (always last = highest priority)
        """
        msgs: list[dict] = []

        # 1. System: persona + rules + profile context
        msgs.append({
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                user_name=self.user_name,
                profile_block=self._profile_block,
            ),
        })

        # 2. System: extended context as background summary
        if extended_context:
            msgs.append({
                "role": "system",
                "content": CONTEXT_PREAMBLE.format(extended_context=extended_context),
            })

        # 3. Prior Q&A history as alternating user/assistant turns
        if history:
            for entry in history:
                role = entry.get("role", "user")
                content = entry.get("content", "")
                if content:
                    msgs.append({"role": role, "content": content})

        # 4. Current question — placed LAST so LLM prioritizes it
        current = current_trigger_text.strip() if current_trigger_text else ""
        if not current and recent_context:
            current = recent_context

        if current:
            msgs.append({
                "role": "user",
                "content": f"Answer this now: {current}",
            })

        return msgs

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
