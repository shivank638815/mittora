"""
QA Engine — per-meeting isolated chatbot.
Each instance is bound to a SINGLE meeting session's data (transcript + summary).
No cross-meeting data leakage.
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .llm_router import LLMRouter
from .groq_client import GroqClient

logger = logging.getLogger(__name__)

QA_SYSTEM_PROMPT = """You are an AI assistant for a specific meeting/lecture. You help the user understand the meeting by answering their questions.

MEETING: {meeting_name}
DATE: {meeting_date}

=== MEETING TRANSCRIPT ===
{transcript}

=== MEETING SUMMARY ===
{summary}

RULES:
1. LANGUAGE MATCHING (CRITICAL):
   - ALWAYS reply in the SAME language the user uses.
   - If user writes in English → reply in English.
   - If user writes in Hindi → reply in Hindi.
   - If user writes in Hinglish (mixed Hindi-English) → reply in Hinglish.
   - Match the user's tone and script exactly.

2. MEETING CONTENT:
   - For questions about the meeting, answer ONLY from the transcript and summary above.
   - Do NOT make up information that is not in the meeting content.
   - If a meeting-related question cannot be answered, say so in the user's language.
   - Reference specific parts of the meeting when possible.

3. CONVERSATION AWARENESS:
   - You have access to the full chat history above.
   - If the user refers to previous messages (e.g., "what did I ask above", "upar kya pucha", "previous question"), look at the conversation history and answer accordingly.
   - You CAN answer questions about the conversation itself — these are NOT meeting-content questions.

4. FORMAT:
   - Be concise and educational.
   - Use markdown formatting (bold, bullets, numbered lists) for structured answers.
   - Do NOT use <think> tags or reasoning blocks.
   - Respond directly with your answer."""


class QAEngine:
    """Per-meeting isolated Q&A chatbot. Each instance is bound to one meeting."""

    def __init__(
        self,
        meeting_folder: Path,
        groq_client: Optional[GroqClient] = None,
        llm_router: Optional[LLMRouter] = None,
    ):
        """
        Initialize QA engine for a specific meeting.

        Args:
            meeting_folder: Root folder of the meeting session (e.g., Daily_Standup/).
            groq_client: Shared Groq client (creates new one if None).
            llm_router: Shared LLM router (creates new one if None).
        """
        self.meeting_folder = Path(meeting_folder)
        self._meeting_name = self.meeting_folder.name.replace("_", " ")
        self._meeting_date = ""
        self._transcript_text = ""
        self._summary_text = ""
        self._chat_history: list[dict] = []
        self._qa_history_path: Optional[Path] = None

        # Initialize LLM
        if llm_router:
            self.llm_router = llm_router
        else:
            client = groq_client or GroqClient()
            self.llm_router = LLMRouter(groq_client=client)

        # Load meeting data (isolated to this folder only)
        self._load_meeting_data()
        self._load_qa_history()

        logger.info(
            "QA Engine initialized for '%s' (transcript: %d chars, summary: %d chars, history: %d msgs)",
            self._meeting_name,
            len(self._transcript_text),
            len(self._summary_text),
            len(self._chat_history),
        )

    @property
    def meeting_name(self) -> str:
        return self._meeting_name

    @property
    def meeting_date(self) -> str:
        return self._meeting_date

    @property
    def has_data(self) -> bool:
        """Check if this meeting has any transcript/summary data to work with."""
        return bool(self._transcript_text or self._summary_text)

    @property
    def chat_history(self) -> list[dict]:
        """Return the chat history (read-only copy)."""
        return list(self._chat_history)

    def ask(self, question: str) -> Optional[str]:
        """
        Ask a question about this specific meeting.

        Args:
            question: The user's question.

        Returns:
            Answer text, or None if generation fails.
        """
        if not question or not question.strip():
            return None

        question = question.strip()

        if not self.has_data:
            return "No transcript or summary data available for this meeting. The meeting may not have been recorded with the AI pipeline enabled."

        # Build messages with system context + conversation history
        messages = self._build_messages(question)

        # Call LLM
        raw_answer = self.llm_router.route("qa", messages)
        if not raw_answer:
            logger.warning("QA LLM returned None for question: %s", question[:80])
            return "I couldn't generate an answer. Please try again."

        answer = self._clean_answer(raw_answer)

        # Save to history
        self._chat_history.append({
            "role": "user",
            "content": question,
            "timestamp": datetime.now().isoformat(),
        })
        self._chat_history.append({
            "role": "assistant",
            "content": answer,
            "timestamp": datetime.now().isoformat(),
        })
        self._save_qa_history()

        logger.info("QA answer: %s", answer[:100])
        return answer

    def clear_history(self):
        """Clear the Q&A chat history for this meeting."""
        self._chat_history.clear()
        self._save_qa_history()

    def _build_messages(self, current_question: str) -> list[dict]:
        """Build LLM messages with system context + prior Q&A history."""
        msgs: list[dict] = []

        # System prompt with meeting content injected
        system_content = QA_SYSTEM_PROMPT.format(
            meeting_name=self._meeting_name,
            meeting_date=self._meeting_date,
            transcript=self._transcript_text[:8000] if self._transcript_text else "(No transcript available)",
            summary=self._summary_text[:3000] if self._summary_text else "(No summary available)",
        )
        msgs.append({"role": "system", "content": system_content})

        # Add last 10 messages from history as context (5 Q&A pairs max)
        recent_history = self._chat_history[-10:]
        for entry in recent_history:
            msgs.append({
                "role": entry["role"],
                "content": entry["content"],
            })

        # Current question
        msgs.append({"role": "user", "content": current_question})

        return msgs

    def _load_meeting_data(self):
        """Load transcript and summary from the meeting folder. Isolated — only reads from self.meeting_folder."""
        # Find chatlog subdirectory
        chatlog_dirs = [
            d for d in self.meeting_folder.iterdir()
            if d.is_dir() and "chatlog" in d.name.lower()
        ] if self.meeting_folder.exists() else []

        if not chatlog_dirs:
            logger.warning("No Chatlog directory found in %s", self.meeting_folder)
            return

        chatlog_dir = chatlog_dirs[0]

        # Load transcript
        transcript_path = chatlog_dir / "ai_transcript.json"
        if transcript_path.exists():
            self._transcript_text = self._read_transcript(transcript_path) or ""

        # Load summary
        summary_path = chatlog_dir / "meeting_summary.json"
        if summary_path.exists():
            self._summary_text = self._read_summary(summary_path) or ""

        # Get meeting date from folder modification time
        try:
            mtime = self.meeting_folder.stat().st_mtime
            self._meeting_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            self._meeting_date = ""

    def _read_transcript(self, path: Path) -> Optional[str]:
        """Read transcript JSON into plain text."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            segments = data.get("segments", [])
            parts = []
            for seg in segments:
                role = seg.get("role", "user")
                text = seg.get("text", "")
                if text:
                    if role == "assistant":
                        parts.append(f"[Bot]: {text}")
                    else:
                        parts.append(text)

            return " ".join(parts) if parts else None
        except Exception as e:
            logger.error("Failed to read transcript: %s", e)
            return None

    def _read_summary(self, path: Path) -> Optional[str]:
        """Read summary JSON into readable text."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            parts = []
            if data.get("title"):
                parts.append(f"Title: {data['title']}")
            if data.get("key_topics"):
                parts.append(f"Key Topics: {', '.join(data['key_topics'])}")
            if data.get("summary"):
                parts.append(f"Summary: {data['summary']}")
            if data.get("important_points"):
                parts.append("Important Points: " + "; ".join(data["important_points"]))
            if data.get("action_items"):
                parts.append("Action Items: " + "; ".join(data["action_items"]))

            return "\n".join(parts) if parts else None
        except Exception as e:
            logger.error("Failed to read summary: %s", e)
            return None

    def _load_qa_history(self):
        """Load existing Q&A history from file."""
        chatlog_dirs = [
            d for d in self.meeting_folder.iterdir()
            if d.is_dir() and "chatlog" in d.name.lower()
        ] if self.meeting_folder.exists() else []

        if not chatlog_dirs:
            return

        self._qa_history_path = chatlog_dirs[0] / "qa_history.json"

        if self._qa_history_path.exists():
            try:
                with open(self._qa_history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._chat_history = data.get("messages", [])
            except Exception as e:
                logger.error("Failed to load QA history: %s", e)
                self._chat_history = []

    def _save_qa_history(self):
        """Persist Q&A history to file."""
        if not self._qa_history_path:
            # Find or create chatlog dir
            chatlog_dirs = [
                d for d in self.meeting_folder.iterdir()
                if d.is_dir() and "chatlog" in d.name.lower()
            ] if self.meeting_folder.exists() else []

            if chatlog_dirs:
                self._qa_history_path = chatlog_dirs[0] / "qa_history.json"
            else:
                return

        try:
            data = {
                "meeting_name": self._meeting_name,
                "messages": self._chat_history,
                "updated_at": datetime.now().isoformat(),
            }
            with open(self._qa_history_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save QA history: %s", e)

    @staticmethod
    def _clean_answer(text: str) -> str:
        """Clean LLM response."""
        text = text.strip()

        # Strip <think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"<think>.*", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"</think>", "", text).strip()

        # Remove surrounding quotes
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            text = text[1:-1].strip()

        return text if text else "I couldn't generate an answer."
