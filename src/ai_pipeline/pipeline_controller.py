"""
Pipeline Controller — the main orchestrator connecting all AI pipeline modules.
Receives audio chunks, drives the STT → Transcript → Trigger → Reply flow.
Uses a thread-safe queue for chat replies (Playwright is thread-bound).
"""
import logging
import os
import queue
import threading
import time
from typing import Callable, Optional

import numpy as np

from .groq_client import GroqClient
from .stt_engine import STTEngine
from .transcript_manager import TranscriptManager
from .llm_router import LLMRouter
from .trigger_detector import TriggerDetector
from .reply_engine import ReplyEngine

logger = logging.getLogger(__name__)


class PipelineController:
    """
    Orchestrates the full AI pipeline:
    Audio → STT → Transcript → Trigger Detection → Reply → Queue for Chat Send

    IMPORTANT: Playwright is greenlet/thread-bound. The pipeline runs in a
    background thread, so it CANNOT call Playwright directly. Instead, replies
    are placed in a thread-safe queue. The main thread (monitoring loop) polls
    get_pending_reply() and sends via Playwright.
    """

    def __init__(
        self,
        groq_client: GroqClient,
        stt_engine: STTEngine,
        transcript_manager: TranscriptManager,
        trigger_detector: TriggerDetector,
        reply_engine: ReplyEngine,
        chat_sender: Optional[Callable[[str], None]] = None,
        reply_cooldown: float = 60.0,
    ):
        self.groq_client = groq_client
        self.stt_engine = stt_engine
        self.transcript_manager = transcript_manager
        self.trigger_detector = trigger_detector
        self.reply_engine = reply_engine
        self.chat_sender = chat_sender  # kept for reference but NOT called from bg thread
        self.reply_cooldown = reply_cooldown

        self._running = False
        self._last_reply_time = 0.0
        self._process_thread: Optional[threading.Thread] = None

        # Thread-safe reply queue — pipeline puts, main thread gets
        self._reply_queue: queue.Queue[str] = queue.Queue()

        logger.info("🧠 Pipeline Controller initialized (cooldown=%ds)", reply_cooldown)

    def start(self):
        """Start the pipeline processing thread."""
        if self._running:
            return

        self._running = True
        self._process_thread = threading.Thread(
            target=self._processing_loop,
            daemon=True,
            name="ai-pipeline",
        )
        self._process_thread.start()
        logger.info("🧠 AI Pipeline STARTED")

    def stop(self):
        """Stop the pipeline gracefully."""
        self._running = False
        if self._process_thread:
            self._process_thread.join(timeout=5)
            self._process_thread = None
        self.stt_engine.reset()
        logger.info("🧠 AI Pipeline STOPPED")

    def on_audio_chunk(self, audio_data: np.ndarray):
        """
        Called by StereoMixRecorder's chunk listener.
        Feeds audio into the STT buffer. Non-blocking.
        """
        if not self._running:
            return
        self.stt_engine.feed_audio(audio_data)

    def get_pending_reply(self) -> Optional[str]:
        """
        Called by the MAIN THREAD (Playwright thread) to get a queued reply.
        Returns the next pending reply, or None if the queue is empty.
        Non-blocking.
        """
        try:
            return self._reply_queue.get_nowait()
        except queue.Empty:
            return None

    def _processing_loop(self):
        """Background thread: continuously processes buffered audio."""
        logger.info("🔄 Pipeline processing loop started")

        while self._running:
            try:
                self._process_cycle()
            except Exception as e:
                logger.error("❌ Pipeline processing error (non-fatal): %s", e)

            time.sleep(0.5)

        logger.info("🔄 Pipeline processing loop ended")

    def _process_cycle(self):
        """Run one processing cycle: STT → Transcript → Trigger → Reply → Queue."""
        # Step 1: Try to transcribe buffered audio
        text = self.stt_engine.try_transcribe()
        if not text:
            return

        # Step 2: Save to transcript manager
        was_new = self.transcript_manager.append(text)
        if not was_new:
            logger.debug("Transcript deduped, skipping pipeline")
            return

        # Step 3: Check trigger
        if self._is_on_cooldown():
            logger.debug("On cooldown — skipping trigger check")
            return

        triggered = self.trigger_detector.check(text)
        if not triggered:
            return

        logger.info("🚨 TRIGGER ACTIVATED — Generating reply...")

        # Step 4: Generate reply with multi-turn context
        recent = self.transcript_manager.get_recent_context(seconds=60)
        extended = self.transcript_manager.get_extended_context(minutes=5)
        history = self.transcript_manager.get_conversation_history(max_pairs=3)

        reply = self.reply_engine.generate(
            recent_context=recent,
            extended_context=extended,
            current_trigger_text=text,
            conversation_history=history,
        )
        if not reply:
            logger.info("Reply engine returned no response — skipping")
            return

        # Step 5: Queue reply for the main (Playwright) thread
        self._queue_reply(reply, recent)

    def _is_on_cooldown(self) -> bool:
        """Check if we're within the reply cooldown period."""
        if self._last_reply_time == 0:
            return False
        elapsed = time.time() - self._last_reply_time
        return elapsed < self.reply_cooldown

    def _queue_reply(self, reply: str, trigger_context: str):
        """Queue a reply for the main thread to send via Playwright."""
        logger.info("📤 Queuing reply for chat: %s", reply)
        self._reply_queue.put(reply)
        self._last_reply_time = time.time()

        # Record the reply in transcript
        self.transcript_manager.record_reply(reply, trigger_context)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def cooldown_remaining(self) -> float:
        """Seconds remaining on cooldown, or 0 if not on cooldown."""
        if self._last_reply_time == 0:
            return 0.0
        elapsed = time.time() - self._last_reply_time
        remaining = self.reply_cooldown - elapsed
        return max(0.0, remaining)

