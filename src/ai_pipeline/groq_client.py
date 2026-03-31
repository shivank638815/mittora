"""
Unified Groq API client for all AI pipeline operations.
Handles STT (Whisper), chat completions (LLama, Qwen, GPT-OSS), retry logic, and rate limit detection.
"""
import io
import logging
import os
import time
from typing import Optional

from groq import Groq, RateLimitError, APITimeoutError, APIError

logger = logging.getLogger(__name__)


class GroqClient:
    """Single client for all Groq API interactions."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self._api_key:
            raise ValueError("GROQ_API_KEY not set in environment or passed directly")

        self._client = Groq(api_key=self._api_key)
        self._rate_limited_until = 0.0

    @property
    def is_rate_limited(self) -> bool:
        return time.time() < self._rate_limited_until

    def _handle_rate_limit(self, retry_after: float = 30.0):
        """Mark client as rate-limited for a duration."""
        self._rate_limited_until = time.time() + retry_after
        logger.warning("⚠️  Groq rate limited — pausing for %.0fs", retry_after)

    def transcribe_audio(
        self,
        audio_buffer: io.BytesIO,
        model: str = "whisper-large-v3-turbo",
        language: str = "en",
    ) -> Optional[dict]:
        """
        Transcribe audio from an in-memory WAV buffer.

        Returns dict with keys: 'text', 'segments' (list with no_speech_prob metadata).
        Returns None on failure or rate limit.
        """
        if self.is_rate_limited:
            logger.debug("Skipping STT — rate limited")
            return None

        audio_buffer.seek(0)

        for attempt in range(2):  # 1 retry
            try:
                transcription = self._client.audio.transcriptions.create(
                    file=("chunk.wav", audio_buffer.read()),
                    model=model,
                    language=language,
                    response_format="verbose_json",
                    temperature=0.0,
                )

                segments = []
                if hasattr(transcription, "segments") and transcription.segments:
                    segments = [
                        {
                            "text": seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", ""),
                            "no_speech_prob": seg.get("no_speech_prob", 0) if isinstance(seg, dict) else getattr(seg, "no_speech_prob", 0),
                            "avg_logprob": seg.get("avg_logprob", 0) if isinstance(seg, dict) else getattr(seg, "avg_logprob", 0),
                        }
                        for seg in transcription.segments
                    ]

                return {
                    "text": transcription.text or "",
                    "segments": segments,
                }

            except RateLimitError as e:
                self._handle_rate_limit()
                return None

            except APITimeoutError:
                if attempt == 0:
                    logger.warning("STT timeout — retrying...")
                    audio_buffer.seek(0)
                    time.sleep(1)
                    continue
                logger.error("STT timeout on retry — giving up")
                return None

            except APIError as e:
                logger.error("Groq API error during STT: %s", e)
                if attempt == 0:
                    audio_buffer.seek(0)
                    time.sleep(1)
                    continue
                return None

            except Exception as e:
                logger.error("Unexpected STT error: %s", e)
                return None

        return None

    def chat_completion(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 256,
    ) -> Optional[str]:
        """
        Run a chat completion and return the response text.
        Returns None on failure or rate limit.
        """
        if self.is_rate_limited:
            logger.debug("Skipping chat completion — rate limited")
            return None

        for attempt in range(2):  # 1 retry
            try:
                completion = self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                    stream=False,
                )

                if completion.choices and completion.choices[0].message:
                    return completion.choices[0].message.content or ""
                return ""

            except RateLimitError:
                self._handle_rate_limit()
                return None

            except APITimeoutError:
                if attempt == 0:
                    logger.warning("Chat completion timeout — retrying...")
                    time.sleep(1)
                    continue
                logger.error("Chat completion timeout on retry — giving up")
                return None

            except APIError as e:
                logger.error("Groq API error during chat: %s", e)
                if attempt == 0:
                    time.sleep(1)
                    continue
                return None

            except Exception as e:
                logger.error("Unexpected chat completion error: %s", e)
                return None

        return None
