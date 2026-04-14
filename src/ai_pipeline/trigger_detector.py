"""
Trigger Detector — decides WHEN the AI should generate a reply.
Two-step detection: fuzzy local name check → LLM confirmation.
"""
import logging
import os
import re
from difflib import SequenceMatcher
from typing import Optional

from .llm_router import LLMRouter
from .transcript_manager import TranscriptManager

logger = logging.getLogger(__name__)

# Similarity threshold for fuzzy name matching (0.0 to 1.0)
# Whisper often misspells names: Shivank → Sivank, Siwank, Shiwank, etc.
NAME_SIMILARITY_THRESHOLD = 0.65

TRIGGER_CHECK_PROMPT = """You are analyzing a meeting transcript to determine if someone is directly asking or expecting a response from "{user_name}".

RECENT CONVERSATION (last 60 seconds — high priority):
{recent_context}

EXTENDED CONTEXT (last 5 minutes):
{extended_context}

Question: Is someone directly addressing "{user_name}" or asking them a question that requires a response?

Rules:
- Answer YES only if someone is clearly expecting "{user_name}" to respond.
- General group questions do NOT count unless "{user_name}" is specifically mentioned.
- If "{user_name}" was just mentioned casually (e.g., greeting, acknowledgment), answer NO.
- Answer with ONLY "YES" or "NO". Nothing else."""


class TriggerDetector:
    """Detects when the AI should generate a reply on behalf of the user."""

    def __init__(
        self,
        llm_router: LLMRouter,
        transcript_manager: TranscriptManager,
        user_name: Optional[str] = None,
    ):
        self.llm_router = llm_router
        self.transcript_manager = transcript_manager
        self.user_name = user_name or os.getenv("USER_DISPLAY_NAME", "User")

        # Build name variations for matching
        # Users can add aliases via env: USER_NAME_ALIASES=Sivank,Siwank,Shiwank
        self._name_variants = {self.user_name.lower()}
        aliases_raw = os.getenv("USER_NAME_ALIASES", "")
        if aliases_raw:
            for alias in aliases_raw.split(","):
                alias = alias.strip().lower()
                if alias:
                    self._name_variants.add(alias)

        logger.info(
            "🎯 Trigger Detector initialized — monitoring for: '%s' (+ fuzzy matching, threshold=%.0f%%)",
            self.user_name,
            NAME_SIMILARITY_THRESHOLD * 100,
        )

    def check(self, latest_text: str) -> bool:
        """
        Two-step trigger detection.
        Step 1: Fuzzy local name check in latest transcript chunk.
        Step 2: LLM confirmation if name found.

        Returns True if the user should respond.
        """
        # Step 1: Fuzzy local check — does the latest chunk mention the user?
        matched_word = self._name_mentioned(latest_text)
        if not matched_word:
            return False

        logger.info(
            "🔍 Name match found: '%s' ≈ '%s' — running LLM check...",
            matched_word, self.user_name,
        )

        # Step 2: LLM confirmation
        return self._llm_confirm()

    def _name_mentioned(self, text: str) -> Optional[str]:
        """
        Fuzzy name matching — handles Whisper STT misspellings.
        Checks each word in the transcript against the user's name and aliases.
        Returns the matched word, or None if no match.
        """
        if not text or not self.user_name:
            return None

        text_lower = text.lower()

        # 1. Exact substring match (fastest path)
        for variant in self._name_variants:
            if variant in text_lower:
                return variant

        # 2. Fuzzy word-by-word match (handles Sivank ≈ Shivank)
        words = re.findall(r'[a-zA-Z]+', text)
        primary_name = self.user_name.lower()

        for word in words:
            word_lower = word.lower()
            # Skip short words and common words
            if len(word_lower) < 3:
                continue

            ratio = SequenceMatcher(None, primary_name, word_lower).ratio()
            if ratio >= NAME_SIMILARITY_THRESHOLD:
                logger.debug(
                    "Fuzzy match: '%s' ≈ '%s' (%.0f%% similarity)",
                    word, self.user_name, ratio * 100,
                )
                return word

        return None

    def _llm_confirm(self) -> bool:
        """Call LLM to confirm whether a response is expected."""
        recent = self.transcript_manager.get_recent_context(seconds=60)
        extended = self.transcript_manager.get_extended_context(minutes=5)

        if not recent:
            logger.warning("🎯 No recent context available — cannot confirm trigger")
            return False

        logger.info("🎯 LLM trigger check — recent context: '%s'", recent[:120])

        prompt = TRIGGER_CHECK_PROMPT.format(
            user_name=self.user_name,
            recent_context=recent,
            extended_context=extended,
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            response = self.llm_router.route("trigger_check", messages)
        except Exception as e:
            logger.error("🎯 Trigger check LLM call FAILED with exception: %s", e)
            return False

        if response is None:
            logger.warning("Trigger check LLM returned None — defaulting to NO")
            return False

        answer = response.strip().upper()

        # Parse response — look for YES anywhere in the response
        triggered = "YES" in answer and "NO" not in answer

        logger.info("🎯 Trigger check result: %s (raw: '%s')", triggered, answer)
        return triggered
