"""
Transcript Manager — thread-safe rolling transcript buffer with JSON persistence.
Stores last 5 minutes of meeting transcript and supports deduplication.
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
        """Record an LLM-generated reply for the transcript log."""
        with self._lock:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "reply": reply,
                "trigger_context": trigger_context[:200],
            }
            self._llm_replies.append(entry)
            self._save_to_file()

    def get_recent_context(self, seconds: float = 60.0) -> str:
        """Get transcript text from the last N seconds."""
        cutoff = time.time() - seconds
        with self._lock:
            texts = [
                seg["text"]
                for seg in self._segments
                if seg.get("epoch", 0) >= cutoff
            ]
        return " ".join(texts)

    def get_extended_context(self, minutes: float = 5.0) -> str:
        """Get transcript text from the last N minutes."""
        return self.get_recent_context(seconds=minutes * 60)

    def _is_duplicate(self, new_text: str) -> bool:
        """Check if new text substantially overlaps with recent entries."""
        new_lower = new_text.lower()

        for recent in self._recent_texts:
            # If new text is a substring of a recent entry
            if new_lower in recent:
                return True
            # If a recent entry is a substring of new text (partial overlap)
            if recent in new_lower and len(recent) > 20:
                # Only count as duplicate if the overlap is substantial
                overlap_ratio = len(recent) / len(new_lower)
                if overlap_ratio > 0.7:
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
                    {"timestamp": s["timestamp"], "text": s["text"]}
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
