"""
Audio transcription module for fleman.
"""

from .groq import transcribe_audio, WHISPER_MODEL, TranscriptionError

__all__ = ["transcribe_audio", "WHISPER_MODEL", "TranscriptionError"]
