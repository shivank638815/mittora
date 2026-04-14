"""
Transcript Manager — thread-safe rolling transcript buffer with JSON persistence.
Stores last 5 minutes of meeting transcript with role-tagged segments
(user speech vs bot replies) for multi-turn LLM context.
"""
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class TranscriptManager:
    """In-memory rolling transcript with periodic file persistence."""

    def __init__(
        self,
        meeting_id: str = "",
        buffer_minutes: float = 5.0,
        save_dir: Optional[Path] = None,
    ):
        self.meeting_id = meeting_id
        self.buffer_seconds = buffer_minutes * 60
        self.save_dir = save_dir

        self._segments: list[dict] = []
        self._llm_replies: list[dict] = []
        self._lock = threading.Lock()

        # For deduplication — last N texts to compare against
        self._recent_texts: list[str] = []
        self._max_dedup_history = 5

        # File persistence path
        self._transcript_path: Optional[Path] = None
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
            self._transcript_path = save_dir / "ai_transcript.json"
            self._init_file()

    def _init_file(self):
        """Initialize the transcript JSON file."""
        if not self._transcript_path:
            return
        try:
            data = {
                "meeting_id": self.meeting_id,
                "created_at": datetime.now().isoformat(),
                "segments": [],
                "llm_replies": [],
            }
            with open(self._transcript_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("📝 Transcript file initialized: %s", self._transcript_path)
        except Exception as e:
            logger.error("Failed to initialize transcript file: %s", e)

    def append(self, text: str) -> bool:
        """
        Add a new transcript segment. Returns False if duplicate detected.
        Thread-safe.
        """
        if not text or not text.strip():
            return False

        text = text.strip()

        with self._lock:
            # Deduplication: check if text is a substring of recent entries or vice versa
            if self._is_duplicate(text):
                logger.debug("Duplicate transcript skipped: '%s'", text[:50])
                return False

            segment = {
                "timestamp": datetime.now().isoformat(),
                "epoch": time.time(),
                "text": text,
                "role": "user",
            }

            self._segments.append(segment)
            self._recent_texts.append(text.lower())
            if len(self._recent_texts) > self._max_dedup_history:
                self._recent_texts.pop(0)

            # Prune old segments beyond buffer window
            self._prune()

            # Persist to file
            self._save_to_file()

        return True

    def record_reply(self, reply: str, trigger_context: str = ""):
        """
        Record an LLM-generated reply.
        Inserts into BOTH _llm_replies (for file logging) AND _segments
        (for context continuity) so subsequent LLM calls see prior answers.
        """
        with self._lock:
            now = datetime.now()
            epoch = time.time()

            # Archive entry for file persistence
            entry = {
                "timestamp": now.isoformat(),
                "reply": reply,
                "trigger_context": trigger_context[:200],
            }
            self._llm_replies.append(entry)

            # Inject into main timeline so get_recent_context / get_conversation_history
            # can see the bot's own answers in chronological order
            segment = {
                "timestamp": now.isoformat(),
                "epoch": epoch,
                "text": reply,
                "role": "assistant",
            }
            self._segments.append(segment)

            self._save_to_file()

    def get_recent_context(self, seconds: float = 60.0) -> str:
        """Get transcript text from the last N seconds with role labels."""
        cutoff = time.time() - seconds
        with self._lock:
            parts = []
            for seg in self._segments:
                if seg.get("epoch", 0) < cutoff:
                    continue
                role = seg.get("role", "user")
                text = seg["text"]
                if role == "assistant":
                    parts.append(f"[Bot replied]: {text}")
                else:
                    parts.append(text)
        return " ".join(parts)

    def get_conversation_history(self, max_pairs: int = 3) -> list[dict]:
        """
        Return the last N user→assistant exchange pairs as role-tagged dicts.
        Used by ReplyEngine to build multi-turn LLM messages.

        Returns list of {"role": "user"|"assistant", "content": str}.
        Capped to max_pairs to stay within token limits.
        """
        with self._lock:
            # Collect only segments that have a role (all should, but be safe)
            role_segments = [
                {"role": seg.get("role", "user"), "content": seg["text"]}
                for seg in self._segments
                if seg.get("role") in ("user", "assistant")
            ]

        if not role_segments:
            return []

        # Count assistant entries to determine how many pairs exist
        assistant_indices = [
            i for i, s in enumerate(role_segments) if s["role"] == "assistant"
        ]

        if not assistant_indices:
            # No bot replies yet — return last few user segments as context
            return role_segments[-max_pairs:]

        # Keep the last max_pairs assistant messages and everything between them
        if len(assistant_indices) <= max_pairs:
            start = 0
        else:
            start = assistant_indices[-max_pairs]

        return role_segments[start:]

    def get_extended_context(self, minutes: float = 5.0) -> str:
        """Get transcript text from the last N minutes."""
        return self.get_recent_context(seconds=minutes * 60)

    def _is_duplicate(self, new_text: str) -> bool:
        """Check if new text is effectively the same as a recent entry.

        Uses strict matching to avoid dropping corrected STT outputs.
        Example: 'tell me about you' vs 'tell me about yourself' are
        NOT duplicates — the second is a refined transcription.
        """
        new_lower = new_text.lower().strip()

        for recent in self._recent_texts:
            # Exact match
            if new_lower == recent:
                return True

            # Near-exact: one is a substring of the other AND covers 90%+
            # of the longer text. This catches true duplicates like
            # overlapping audio chunks repeating the same sentence.
            longer = max(len(new_lower), len(recent))
            if longer == 0:
                continue

            if new_lower in recent:
                if len(new_lower) / longer >= 0.90:
                    return True
            elif recent in new_lower:
                if len(recent) / longer >= 0.90:
                    return True

        return False

    def _prune(self):
        """Remove segments older than the buffer window."""
        cutoff = time.time() - self.buffer_seconds
        self._segments = [
            seg for seg in self._segments
            if seg.get("epoch", 0) >= cutoff
        ]

    def _save_to_file(self):
        """Persist current state to JSON file."""
        if not self._transcript_path:
            return
        try:
            data = {
                "meeting_id": self.meeting_id,
                "segments": [
                    {
                        "timestamp": s["timestamp"],
                        "text": s["text"],
                        "role": s.get("role", "user"),
                    }
                    for s in self._segments
                ],
                "llm_replies": self._llm_replies,
            }
            with open(self._transcript_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save transcript: %s", e)

    def clear(self):
        """Clear all segments."""
        with self._lock:
            self._segments.clear()
            self._recent_texts.clear()
            self._llm_replies.clear()
