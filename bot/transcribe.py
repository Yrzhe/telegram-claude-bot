"""Voice transcription module using OpenAI GPT-4o Transcribe API

Features:
- Automatic transcription of voice messages
- Long audio splitting using VAD (Voice Activity Detection)
- User-specific vocabulary dictionary for accuracy improvement
- Transcript storage and management
"""

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

# Maximum file size for single transcription (25MB)
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

# Default context prompt for transcription
DEFAULT_PROMPT = (
    "Transcribe this voice message accurately with proper punctuation. "
    "Pay attention to names, technical terms, and proper nouns. "
    "Use natural sentence structure and include all spoken content."
)


class VoiceDictionary:
    """Manages user-specific vocabulary for transcription accuracy"""

    def __init__(self, user_data_path: Path):
        self.user_data_path = Path(user_data_path)
        self.dict_file = self.user_data_path / "voice_dictionary.json"
        self._load()

    def _load(self):
        """Load dictionary from file"""
        if self.dict_file.exists():
            try:
                with open(self.dict_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.entries = data.get("entries", [])
                    self.context_prompt = data.get("context_prompt", "")
            except Exception as e:
                logger.error(f"Failed to load voice dictionary: {e}")
                self.entries = []
                self.context_prompt = ""
        else:
            self.entries = []
            self.context_prompt = ""

    def _save(self):
        """Save dictionary to file"""
        self.user_data_path.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.dict_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "entries": self.entries,
                    "context_prompt": self.context_prompt
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save voice dictionary: {e}")

    def add_entry(self, wrong: str, correct: str) -> bool:
        """Add a vocabulary entry"""
        # Check if entry already exists
        for entry in self.entries:
            if entry["wrong"].lower() == wrong.lower():
                entry["correct"] = correct
                self._save()
                return True

        self.entries.append({"wrong": wrong, "correct": correct})
        self._save()
        return True

    def remove_entry(self, wrong: str) -> bool:
        """Remove a vocabulary entry"""
        for i, entry in enumerate(self.entries):
            if entry["wrong"].lower() == wrong.lower():
                self.entries.pop(i)
                self._save()
                return True
        return False

    def set_context_prompt(self, prompt: str):
        """Set custom context prompt"""
        self.context_prompt = prompt
        self._save()

    def get_prompt(self) -> str:
        """Get the full prompt for transcription"""
        base_prompt = DEFAULT_PROMPT

        # Add user's custom context
        if self.context_prompt:
            base_prompt = f"{self.context_prompt}\n\n{base_prompt}"

        # Add vocabulary hints
        if self.entries:
            vocab_hints = ", ".join([f'"{e["correct"]}"' for e in self.entries[:20]])
            base_prompt += f"\n\nImportant terms that may appear: {vocab_hints}"

        return base_prompt

    def apply_corrections(self, text: str) -> str:
        """Apply vocabulary corrections to transcribed text"""
        result = text
        for entry in self.entries:
            # Case-insensitive replacement
            import re
            pattern = re.compile(re.escape(entry["wrong"]), re.IGNORECASE)
            result = pattern.sub(entry["correct"], result)
        return result

    def get_entries(self) -> List[dict]:
        """Get all dictionary entries"""
        return self.entries.copy()


class VoiceTranscriber:
    """Voice to text transcription using OpenAI GPT-4o Transcribe"""

    def __init__(self, api_key: str, model: str = "gpt-4o-transcribe"):
        """
        Initialize the transcriber.

        Args:
            api_key: OpenAI API key
            model: Transcription model to use
        """
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _split_audio_by_silence(self, audio_path: Path) -> List[Path]:
        """
        Split audio file by silence for long files.

        Args:
            audio_path: Path to the audio file

        Returns:
            List of paths to audio segments
        """
        try:
            from pydub import AudioSegment
            from pydub.silence import split_on_silence
        except ImportError:
            logger.warning("pydub not available, cannot split audio")
            return [audio_path]

        try:
            # Load audio
            audio = AudioSegment.from_file(str(audio_path))
            duration_ms = len(audio)

            # If audio is short enough, no need to split
            file_size = audio_path.stat().st_size
            if file_size <= MAX_FILE_SIZE_BYTES:
                return [audio_path]

            logger.info(f"Audio file too large ({file_size / 1024 / 1024:.1f}MB), splitting by silence")

            # Split on silence
            # min_silence_len: minimum length of silence (ms)
            # silence_thresh: silence threshold in dBFS
            # keep_silence: amount of silence to keep at boundaries (ms)
            chunks = split_on_silence(
                audio,
                min_silence_len=500,  # 500ms of silence
                silence_thresh=audio.dBFS - 16,  # 16dB below average
                keep_silence=200  # Keep 200ms of silence at boundaries
            )

            if not chunks:
                # If no silence found, split by duration
                logger.info("No silence detected, splitting by duration")
                chunk_duration_ms = 10 * 60 * 1000  # 10 minutes per chunk
                chunks = [audio[i:i + chunk_duration_ms]
                          for i in range(0, duration_ms, chunk_duration_ms)]

            # Merge small chunks to avoid too many API calls
            merged_chunks = []
            current_chunk = None
            max_chunk_duration_ms = 10 * 60 * 1000  # 10 minutes max per chunk

            for chunk in chunks:
                if current_chunk is None:
                    current_chunk = chunk
                elif len(current_chunk) + len(chunk) <= max_chunk_duration_ms:
                    current_chunk = current_chunk + chunk
                else:
                    merged_chunks.append(current_chunk)
                    current_chunk = chunk

            if current_chunk:
                merged_chunks.append(current_chunk)

            # Export chunks to temporary files
            temp_dir = audio_path.parent
            segment_paths = []

            for i, chunk in enumerate(merged_chunks):
                segment_path = temp_dir / f"{audio_path.stem}_part{i + 1}.mp3"
                chunk.export(str(segment_path), format="mp3")
                segment_paths.append(segment_path)
                logger.info(f"Created segment {i + 1}/{len(merged_chunks)}: {len(chunk) / 1000:.1f}s")

            return segment_paths

        except Exception as e:
            logger.error(f"Failed to split audio: {e}")
            return [audio_path]

    async def transcribe(
            self,
            audio_path: str | Path,
            dictionary: VoiceDictionary | None = None
    ) -> Tuple[str, List[Path]]:
        """
        Transcribe an audio file to text.

        Args:
            audio_path: Path to the audio file
            dictionary: Optional user dictionary for improved accuracy

        Returns:
            Tuple of (transcribed text, list of segment files to clean up)

        Raises:
            Exception: If transcription fails
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info(f"Transcribing audio file: {audio_path}")

        # Get prompt from dictionary or use default
        prompt = dictionary.get_prompt() if dictionary else DEFAULT_PROMPT

        # Split audio if needed
        segments = self._split_audio_by_silence(audio_path)
        transcripts = []
        cleanup_files = []

        try:
            for i, segment_path in enumerate(segments):
                logger.info(f"Transcribing segment {i + 1}/{len(segments)}: {segment_path}")

                with open(segment_path, "rb") as audio_file:
                    transcript = self.client.audio.transcriptions.create(
                        file=audio_file,
                        model=self.model,
                        response_format="text",
                        prompt=prompt
                    )

                transcripts.append(transcript)

                # Mark segment files for cleanup (but not the original)
                if segment_path != audio_path:
                    cleanup_files.append(segment_path)

            # Combine all transcripts
            full_transcript = " ".join(transcripts)

            # Apply dictionary corrections
            if dictionary:
                full_transcript = dictionary.apply_corrections(full_transcript)

            logger.info(f"Transcription completed: {len(full_transcript)} characters")
            return full_transcript, cleanup_files

        except Exception as e:
            # Clean up segment files on error
            for f in cleanup_files:
                try:
                    f.unlink()
                except Exception:
                    pass
            logger.error(f"Transcription failed: {e}")
            raise


class TranscriptManager:
    """Manages transcript storage and voice file cleanup"""

    def __init__(self, user_data_path: Path):
        self.user_data_path = Path(user_data_path)
        self.transcripts_dir = self.user_data_path / "transcripts"
        self.voice_temp_dir = self.user_data_path / ".voice_temp"

    def save_transcript(self, text: str, original_filename: str = None) -> Path:
        """
        Save transcript to file.

        Args:
            text: Transcribed text
            original_filename: Original audio filename (optional)

        Returns:
            Path to saved transcript file
        """
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"transcript_{timestamp}.txt"

        transcript_path = self.transcripts_dir / filename

        # Build content with metadata
        content_lines = []
        content_lines.append(f"Transcription Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if original_filename:
            content_lines.append(f"Source: {original_filename}")
        content_lines.append("-" * 40)
        content_lines.append("")
        content_lines.append(text)

        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(content_lines))

        logger.info(f"Transcript saved: {transcript_path}")
        return transcript_path

    def get_voice_temp_dir(self) -> Path:
        """Get temp directory for voice files (kept for 1 day)"""
        self.voice_temp_dir.mkdir(parents=True, exist_ok=True)
        return self.voice_temp_dir

    def cleanup_old_voice_files(self, max_age_hours: int = 24):
        """
        Clean up voice files older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours (default 24)
        """
        if not self.voice_temp_dir.exists():
            return

        from datetime import timedelta
        now = datetime.now()
        cutoff = now - timedelta(hours=max_age_hours)
        cleaned = 0

        for file_path in self.voice_temp_dir.iterdir():
            if file_path.is_file():
                try:
                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff:
                        file_path.unlink()
                        cleaned += 1
                except Exception as e:
                    logger.error(f"Failed to clean up voice file {file_path}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old voice files")


def create_transcriber(api_key: str, model: str = "gpt-4o-transcribe") -> VoiceTranscriber | None:
    """
    Create a voice transcriber instance.

    Args:
        api_key: OpenAI API key
        model: Transcription model to use

    Returns:
        VoiceTranscriber instance or None if api_key is empty
    """
    if not api_key:
        logger.warning("OpenAI API key not configured, voice transcription disabled")
        return None

    return VoiceTranscriber(api_key=api_key, model=model)
