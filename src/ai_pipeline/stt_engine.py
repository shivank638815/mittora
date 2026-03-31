"""
Speech-to-Text engine — buffers raw audio chunks, converts to WAV in-memory,
sends to Groq Whisper API, and returns cleaned transcript text.
"""
import io
import logging
import re
import threading
from typing import Optional

import numpy as np
import soundfile as sf

from .groq_client import GroqClient

logger = logging.getLogger(__name__)

# Common Whisper hallucination phrases that appear in silence or noise
HALLUCINATION_PHRASES = {
    "thank you for watching",
    "thanks for watching",
    "subscribe",
    "like and subscribe",
    "please subscribe",
    "thank you",
    "thanks",
    "bye",
    "goodbye",
    "see you next time",
    "silence",
    "you",
    "the end",
    "music",
    "applause",
    "laughter",
}


class AudioChunkBuffer:
    """Accumulates raw audio numpy arrays until a target duration is reached."""

    def __init__(self, chunk_duration: float = 20.0, overlap: float = 5.0, sample_rate: int = 16000):
        self.chunk_duration = chunk_duration
        self.overlap = overlap
        self.sample_rate = sample_rate
        self._buffer: list[np.ndarray] = []
        self._total_samples = 0
        self._lock = threading.Lock()

    @property
    def duration_seconds(self) -> float:
        return self._total_samples / self.sample_rate if self.sample_rate else 0.0

    @property
    def is_ready(self) -> bool:
        return self.duration_seconds >= self.chunk_duration

    def add(self, audio_data: np.ndarray):
        """Add a numpy audio chunk to the buffer."""
        with self._lock:
            self._buffer.append(audio_data)
            self._total_samples += len(audio_data)

    def consume(self) -> Optional[np.ndarray]:
        """
        Return the full buffer as a single numpy array and keep overlap samples.
        Returns None if buffer isn't ready.
        """
        if not self.is_ready:
            return None

        with self._lock:
            full_audio = np.concatenate(self._buffer, axis=0)

            # Keep the last `overlap` seconds for context continuity
            overlap_samples = int(self.overlap * self.sample_rate)
            if overlap_samples > 0 and len(full_audio) > overlap_samples:
                self._buffer = [full_audio[-overlap_samples:]]
                self._total_samples = overlap_samples
            else:
                self._buffer = []
                self._total_samples = 0

            return full_audio

    def clear(self):
        with self._lock:
            self._buffer.clear()
            self._total_samples = 0


class STTEngine:
    """Converts buffered audio to text via Groq Whisper API."""

    def __init__(
        self,
        groq_client: GroqClient,
        chunk_duration: float = 20.0,
        chunk_overlap: float = 5.0,
        sample_rate: int = 16000,
        channels: int = 2,
        no_speech_threshold: float = 0.8,
    ):
        self.groq_client = groq_client
        self.sample_rate = sample_rate
        self.channels = channels
        self.no_speech_threshold = no_speech_threshold

        self.buffer = AudioChunkBuffer(
            chunk_duration=chunk_duration,
            overlap=chunk_overlap,
            sample_rate=sample_rate,
        )

    def feed_audio(self, audio_data: np.ndarray):
        """Feed raw audio data from the recorder callback."""
        self.buffer.add(audio_data)

    def try_transcribe(self) -> Optional[str]:
        """
        If enough audio is buffered, transcribe it and return cleaned text.
        Returns None if buffer isn't ready or transcription fails.
        """
        if not self.buffer.is_ready:
            return None

        audio = self.buffer.consume()
        if audio is None:
            return None

        # Convert stereo to mono if needed
        if audio.ndim > 1 and audio.shape[1] > 1:
            audio = np.mean(audio, axis=1)

        # Ensure float32
        audio = audio.astype(np.float32)

        # Check if audio is pure silence (RMS below threshold)
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.001:
            logger.debug("Audio chunk is silence (RMS=%.6f), skipping STT", rms)
            return None

        # Convert to WAV in memory
        wav_buffer = self._numpy_to_wav_bytes(audio)
        if wav_buffer is None:
            return None

        # Send to Groq Whisper
        result = self.groq_client.transcribe_audio(wav_buffer)
        if result is None:
            return None

        raw_text = result.get("text", "")
        segments = result.get("segments", [])

        # Silence filter via no_speech_prob metadata
        if segments and self._is_no_speech(segments):
            logger.debug("All segments flagged as no-speech, skipping")
            return None

        # Clean and filter the text
        cleaned = self._clean_text(raw_text)
        if not cleaned:
            return None

        logger.info("🎤 STT: %s", cleaned[:100])
        return cleaned

    def _numpy_to_wav_bytes(self, audio: np.ndarray) -> Optional[io.BytesIO]:
        """Convert numpy audio array to WAV bytes in memory."""
        try:
            buf = io.BytesIO()
            sf.write(buf, audio, self.sample_rate, format="WAV", subtype="PCM_16")
            buf.seek(0)
            return buf
        except Exception as e:
            logger.error("Failed to create WAV buffer: %s", e)
            return None

    def _is_no_speech(self, segments: list[dict]) -> bool:
        """Check if all segments indicate no speech."""
        if not segments:
            return False
        return all(
            seg.get("no_speech_prob", 0) > self.no_speech_threshold
            for seg in segments
        )

    def _clean_text(self, text: str) -> Optional[str]:
        """Clean transcription text: remove hallucinations, dedup, filter empty."""
        if not text or not text.strip():
            return None

        text = text.strip()

        # Remove common hallucination phrases
        text_lower = text.lower().strip().rstrip(".")
        if text_lower in HALLUCINATION_PHRASES:
            logger.debug("Filtered hallucination: '%s'", text)
            return None

        # Remove repeated phrases (e.g., "hello hello hello")
        text = self._remove_repeated_phrases(text)

        # Too short after cleaning
        words = text.split()
        if len(words) < 3:
            logger.debug("Text too short after cleaning: '%s'", text)
            return None

        return text

    @staticmethod
    def _remove_repeated_phrases(text: str) -> str:
        """Remove consecutively repeated phrases."""
        # Match patterns like "word word word" or "phrase phrase"
        cleaned = re.sub(r'\b(\w+(?:\s+\w+){0,3})\s+(?:\1\s*)+', r'\1', text, flags=re.IGNORECASE)
        return cleaned.strip()

    def reset(self):
        """Clear the audio buffer."""
        self.buffer.clear()
