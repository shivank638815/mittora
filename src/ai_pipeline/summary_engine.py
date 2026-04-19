"""
Summary Engine — generates structured meeting summaries from transcripts.
Produces JSON summary + PDF export using fpdf2.
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .llm_router import LLMRouter

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM_PROMPT = """You are a meeting summarizer. Given a meeting transcript, produce a concise structured summary.

OUTPUT FORMAT (JSON):
{
  "title": "Brief meeting title based on content",
  "key_topics": ["topic1", "topic2", "topic3"],
  "summary": "A comprehensive 3-5 paragraph summary covering all major points discussed.",
  "important_points": ["point1", "point2", "point3"],
  "action_items": ["action1", "action2"],
  "questions_discussed": ["question1", "question2"]
}

RULES:
- Extract the MAIN topics discussed, not filler conversation.
- The summary should be detailed enough for revision but concise.
- List action items if any homework, assignments, or tasks were mentioned.
- List questions that were asked and discussed.
- If the transcript is from a lecture/class, focus on educational content.
- Output ONLY valid JSON. No markdown, no explanation, no preamble."""

SUMMARY_USER_PROMPT = """Meeting Transcript:
{transcript}

Generate a structured JSON summary of this meeting."""


class SummaryEngine:
    """Generates meeting summaries from transcript data."""

    def __init__(self, llm_router: LLMRouter):
        self.llm_router = llm_router

    def generate(
        self,
        transcript_text: str,
        meeting_name: str = "Meeting",
        meeting_date: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Generate a structured summary from transcript text.

        Args:
            transcript_text: Full transcript text.
            meeting_name: Name of the meeting.
            meeting_date: ISO date string (auto-detected if None).

        Returns:
            Summary dict or None if generation fails.
        """
        if not transcript_text or len(transcript_text.strip()) < 50:
            logger.warning("Transcript too short for summarization (%d chars)", len(transcript_text or ""))
            return None

        if not meeting_date:
            meeting_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Truncate very long transcripts to stay within token limits
        max_chars = 12000
        if len(transcript_text) > max_chars:
            transcript_text = transcript_text[:max_chars] + "\n...[transcript truncated]..."

        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": SUMMARY_USER_PROMPT.format(transcript=transcript_text)},
        ]

        raw_response = self.llm_router.route("summarize", messages)
        if not raw_response:
            logger.error("Summary generation failed — LLM returned None")
            return None

        summary = self._parse_summary(raw_response)
        if not summary:
            logger.error("Failed to parse summary JSON from LLM response")
            return None

        # Attach metadata
        summary["meeting_name"] = meeting_name
        summary["meeting_date"] = meeting_date
        summary["generated_at"] = datetime.now().isoformat()
        summary["transcript_length"] = len(transcript_text)

        logger.info("Summary generated: %s (%d topics)", summary.get("title", "Untitled"), len(summary.get("key_topics", [])))
        return summary

    def save_summary(self, summary: dict, output_dir: Path) -> Optional[Path]:
        """Save summary as JSON file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "meeting_summary.json"

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            logger.info("Summary saved: %s", json_path)
            return json_path
        except Exception as e:
            logger.error("Failed to save summary JSON: %s", e)
            return None

    def export_pdf(self, summary: dict, output_dir: Path) -> Optional[Path]:
        """Export summary as a formatted PDF using fpdf2 with Unicode support."""
        try:
            from fpdf import FPDF
        except ImportError:
            logger.error("fpdf2 not installed — cannot export PDF. Install with: pip install fpdf2")
            return None

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "meeting_summary.pdf"

        try:
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=20)

            # Register Unicode-capable font (Mangal supports Hindi/Devanagari)
            font_name = "Helvetica"
            mangal_regular = Path("C:/Windows/Fonts/mangal.ttf")
            mangal_bold = Path("C:/Windows/Fonts/mangalb.ttf")
            if mangal_regular.exists():
                pdf.add_font("Mangal", "", str(mangal_regular))
                if mangal_bold.exists():
                    pdf.add_font("Mangal", "B", str(mangal_bold))
                else:
                    pdf.add_font("Mangal", "B", str(mangal_regular))
                font_name = "Mangal"
                logger.info("PDF: Using Mangal font (Unicode/Hindi support)")
            else:
                logger.warning("PDF: Mangal font not found, using Helvetica (no Hindi support)")

            pdf.add_page()

            # Helper to safely encode text for PDF
            def safe_text(text: str) -> str:
                """Ensure text is safe for PDF rendering."""
                if not text:
                    return ""
                return str(text).replace("\r\n", "\n").replace("\r", "\n")

            # Title
            pdf.set_font(font_name, "B", 20)
            pdf.set_text_color(30, 30, 30)
            title = safe_text(summary.get("title", "Meeting Summary"))
            pdf.cell(0, 14, title, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(4)

            # Meeting info
            pdf.set_font(font_name, "", 10)
            pdf.set_text_color(100, 100, 100)
            meeting_name = safe_text(summary.get("meeting_name", "Meeting"))
            meeting_date = safe_text(summary.get("meeting_date", ""))
            pdf.cell(0, 6, f"Meeting: {meeting_name}  |  Date: {meeting_date}", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(8)

            # Separator line
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(8)

            # Key Topics
            key_topics = summary.get("key_topics", [])
            if key_topics:
                pdf.set_font(font_name, "B", 13)
                pdf.set_text_color(30, 30, 30)
                pdf.cell(0, 10, "Key Topics", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font_name, "", 11)
                pdf.set_text_color(50, 50, 50)
                for topic in key_topics:
                    pdf.cell(0, 7, f"  - {safe_text(topic)}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(6)

            # Summary
            summary_text = safe_text(summary.get("summary", ""))
            if summary_text:
                pdf.set_font(font_name, "B", 13)
                pdf.set_text_color(30, 30, 30)
                pdf.cell(0, 10, "Summary", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font_name, "", 11)
                pdf.set_text_color(50, 50, 50)
                pdf.multi_cell(0, 6, summary_text)
                pdf.ln(6)

            # Important Points
            important = summary.get("important_points", [])
            if important:
                pdf.set_font(font_name, "B", 13)
                pdf.set_text_color(30, 30, 30)
                pdf.cell(0, 10, "Important Points", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font_name, "", 11)
                pdf.set_text_color(50, 50, 50)
                for point in important:
                    pdf.multi_cell(0, 6, f"  - {safe_text(point)}")
                pdf.ln(6)

            # Action Items
            action_items = summary.get("action_items", [])
            if action_items:
                pdf.set_font(font_name, "B", 13)
                pdf.set_text_color(30, 30, 30)
                pdf.cell(0, 10, "Action Items", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font_name, "", 11)
                pdf.set_text_color(50, 50, 50)
                for item in action_items:
                    pdf.multi_cell(0, 6, f"  - {safe_text(item)}")
                pdf.ln(6)

            # Questions Discussed
            questions = summary.get("questions_discussed", [])
            if questions:
                pdf.set_font(font_name, "B", 13)
                pdf.set_text_color(30, 30, 30)
                pdf.cell(0, 10, "Questions Discussed", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font_name, "", 11)
                pdf.set_text_color(50, 50, 50)
                for q in questions:
                    pdf.multi_cell(0, 6, f"  - {safe_text(q)}")
                pdf.ln(6)

            # Footer
            pdf.ln(10)
            pdf.set_font(font_name, "", 8)
            pdf.set_text_color(150, 150, 150)
            generated_at = summary.get("generated_at", datetime.now().isoformat())
            pdf.cell(0, 5, f"Generated by Mittora AI  |  {generated_at}", new_x="LMARGIN", new_y="NEXT")

            pdf.output(str(pdf_path))
            logger.info("PDF exported: %s", pdf_path)
            return pdf_path

        except Exception as e:
            logger.error("Failed to export PDF: %s", e)
            return None

    def _parse_summary(self, raw_text: str) -> Optional[dict]:
        """Parse LLM response into a structured summary dict."""
        text = raw_text.strip()

        # Strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        # Strip <think> blocks (Qwen models)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"<think>.*", "", text, flags=re.DOTALL).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        logger.error("Could not parse JSON from: %s", text[:200])
        return None

    @staticmethod
    def load_transcript_from_file(transcript_path: Path) -> Optional[str]:
        """Load transcript text from an ai_transcript.json file."""
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            segments = data.get("segments", [])
            if not segments:
                return None

            parts = []
            for seg in segments:
                role = seg.get("role", "user")
                text = seg.get("text", "")
                if text:
                    if role == "assistant":
                        parts.append(f"[Bot]: {text}")
                    else:
                        parts.append(text)

            full_text = " ".join(parts)
            return full_text if len(full_text) >= 50 else None

        except Exception as e:
            logger.error("Failed to load transcript: %s", e)
            return None
