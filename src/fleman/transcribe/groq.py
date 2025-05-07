import os
from pathlib import Path
from typing import Optional, Dict, Any
import contextlib
import wave
from groq import Groq

# Default models for transcription
WHISPER_MODEL = "whisper-large-v3"


class TranscriptionError(Exception):
    """Exception raised for errors during audio transcription."""

    pass


def get_audio_duration(file_path: Path) -> float:
    """
    Get duration of audio file in seconds.

    Args:
        file_path: Path to the audio file

    Returns:
        Duration in seconds
    """
    try:
        with contextlib.closing(wave.open(str(file_path), "r")) as f:
            frames = f.getnframes()
            rate = f.getframerate()
            duration = frames / float(rate)
            return duration
    except Exception:
        # If we can't determine duration, return a default estimate
        return 0.0


def transcribe_audio(
    audio_path: Path,
    api_key: Optional[str] = None,
    model: str = WHISPER_MODEL,
    language: Optional[str] = None,
    response_format: str = "verbose_json",
) -> Dict[str, Any]:
    """
    Transcribe audio using Groq's Whisper API.

    Args:
        audio_path: Path to the audio file
        api_key: Groq API key (optional if set as GROQ_API_KEY env var)
        model: Model to use for transcription (default is whisper-large-v3)
        language: Source language of the audio (optional)
        response_format: Response format (default is verbose_json)

    Returns:
        Dictionary containing transcription and metadata
    """
    # Use provided API key or get from environment
    groq_api_key = api_key or os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        raise TranscriptionError(
            "Groq API key is required. Provide it as parameter or set GROQ_API_KEY environment variable."
        )

    # Initialize Groq client
    client = Groq(api_key=groq_api_key)

    try:
        # Get audio file path as string
        file_path = str(audio_path)

        # Open and read the file for sending to Groq API
        with open(audio_path, "rb") as audio_file:
            file_content = audio_file.read()

            # Call the Groq audio transcription API
            transcription = client.audio.transcriptions.create(
                file=(file_path, file_content),
                model=model,
                response_format=response_format,
                language=language,
            )

        # For verbose_json format, extract segments and text
        if response_format == "verbose_json":
            text = transcription.text
            segments = (
                transcription.segments if hasattr(transcription, "segments") else []
            )

            # Create segments structure compatible with our system
            formatted_segments = []
            for segment in segments:
                formatted_segments.append(
                    {
                        "start": segment.get("start", 0),
                        "end": segment.get("end", 0),
                        "text": segment.get("text", ""),
                    }
                )

            return {
                "text": text,
                "audio_file": str(audio_path),
                "duration": get_audio_duration(audio_path),
                "language": language,
                "segments": formatted_segments,
            }

        # For simple text format
        else:
            return {
                "text": transcription.text
                if hasattr(transcription, "text")
                else str(transcription),
                "audio_file": str(audio_path),
                "duration": get_audio_duration(audio_path),
                "language": language,
                "segments": [],
            }

    except Exception as e:
        raise TranscriptionError(f"Transcription failed: {str(e)}")
