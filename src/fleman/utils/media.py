"""
Media utility functions using ffmpeg.
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional


class MediaError(Exception):
    """Exception raised for errors during media processing."""

    pass


class VideoInfo:
    """Store information about a video file."""

    def __init__(self, file_path: Path):
        """
        Initialize with video file path and extract metadata.

        Args:
            file_path: Path to the video file
        """
        self.file_path = file_path
        self._metadata = self._extract_metadata()

    def _extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata from video file using ffprobe."""
        try:
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(self.file_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            raise MediaError(
                f"Failed to extract metadata from {self.file_path}: {str(e)}"
            )

    @property
    def duration(self) -> float:
        """Get video duration in seconds."""
        try:
            return float(self._metadata.get("format", {}).get("duration", 0))
        except (ValueError, TypeError):
            return 0.0

    @property
    def has_audio(self) -> bool:
        """Check if video has audio stream."""
        streams = self._metadata.get("streams", [])
        return any(s.get("codec_type") == "audio" for s in streams)

    @property
    def video_codec(self) -> Optional[str]:
        """Get video codec."""
        streams = self._metadata.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "video":
                return stream.get("codec_name")
        return None

    @property
    def audio_codec(self) -> Optional[str]:
        """Get audio codec."""
        streams = self._metadata.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "audio":
                return stream.get("codec_name")
        return None

    @property
    def width(self) -> int:
        """Get video width."""
        streams = self._metadata.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "video":
                return int(stream.get("width", 0))
        return 0

    @property
    def height(self) -> int:
        """Get video height."""
        streams = self._metadata.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "video":
                return int(stream.get("height", 0))
        return 0

    @property
    def fps(self) -> float:
        """Get video framerate."""
        streams = self._metadata.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "video":
                # Handle different format possibilities
                fps_str = stream.get("r_frame_rate", "0/1")
                try:
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        return float(num) / float(den)
                    else:
                        return float(fps_str)
                except (ValueError, ZeroDivisionError):
                    return 0.0
        return 0.0


def extract_audio(
    video_path: Path,
    output_path: Optional[Path] = None,
    format: str = "wav",
    audio_opts: Optional[Dict[str, str]] = None,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
    bit_depth: Optional[int] = None,
    small: bool = True,  # Changed default to True
    max_size_mb: float = 19.5,
) -> Path:
    """
    Extract audio from video file using ffmpeg.

    Args:
        video_path: Path to the video file
        output_path: Path for the output audio file (default: same directory as video with .wav extension)
        format: Audio format (default: wav)
        audio_opts: Optional audio encoding options for ffmpeg
        sample_rate: Sample rate in Hz (e.g. 16000 for 16kHz)
        channels: Number of audio channels (1 for mono, 2 for stereo)
        bit_depth: Audio bit depth (8, 16 or 24)
        small: If True, uses optimized settings for smaller file size (16kHz, mono, 16-bit).
              Default is now True to ensure files stay under max_size_mb.
        max_size_mb: Maximum file size in MB (default: 19.5MB)

    Returns:
        Path to the extracted audio file
    """
    # Check if the video file exists
    if not video_path.exists():
        raise MediaError(f"Video file not found: {video_path}")

    # Get video information to calculate appropriate settings
    video_info = VideoInfo(video_path)
    duration = video_info.duration  # in seconds

    # Determine output path if not specified
    if output_path is None:
        output_path = video_path.with_suffix(f".{format}")

    # Base ffmpeg command
    cmd = ["ffmpeg", "-y", "-i", str(video_path)]

    # Use "small" optimized settings if specified
    if small:
        # Calculate appropriate sample rate to stay under max_size_mb
        # WAV file size calculation: duration * sample_rate * bit_depth/8 * channels

        # Start with reasonable defaults
        calculated_sample_rate = 16000  # 16kHz
        calculated_channels = 1  # Mono
        calculated_bit_depth = 16  # 16-bit

        # Calculate file size with these settings (in bytes)
        # 1 sample = (bit_depth/8) * channels bytes
        bytes_per_second = (
            calculated_sample_rate * (calculated_bit_depth / 8) * calculated_channels
        )
        estimated_size_mb = (duration * bytes_per_second) / (1024 * 1024)

        # If estimated size is still too large, adjust sample rate down
        if estimated_size_mb > max_size_mb and duration > 0:
            # Calculate max sample rate that would fit within max_size_mb
            max_bytes = max_size_mb * 1024 * 1024
            max_sample_rate = (
                max_bytes / duration / (calculated_bit_depth / 8) / calculated_channels
            )

            # Round down to common sample rates
            if max_sample_rate < 8000:
                calculated_sample_rate = 8000  # Minimum reasonable sample rate
            elif max_sample_rate < 16000:
                calculated_sample_rate = 8000
            elif max_sample_rate < 22050:
                calculated_sample_rate = 16000
            elif max_sample_rate < 44100:
                calculated_sample_rate = 22050
            else:
                calculated_sample_rate = 44100

        sample_rate = calculated_sample_rate
        channels = calculated_channels
        bit_depth = calculated_bit_depth

    # Add audio quality options
    if sample_rate:
        cmd.extend(["-ar", str(sample_rate)])

    if channels:
        cmd.extend(["-ac", str(channels)])

    # Handle bit depth for WAV
    if bit_depth and format.lower() == "wav":
        if bit_depth == 8:
            cmd.extend(["-acodec", "pcm_u8"])
        elif bit_depth == 16:
            cmd.extend(["-acodec", "pcm_s16le"])
        elif bit_depth == 24:
            cmd.extend(["-acodec", "pcm_s24le"])
        else:
            # Default to 16-bit if an unsupported bit depth is provided
            cmd.extend(["-acodec", "pcm_s16le"])

    # Add audio options if specified (these will override the above if there's overlap)
    if audio_opts:
        for k, v in audio_opts.items():
            cmd.extend([f"-{k}", v])

    # Add output file
    cmd.append(str(output_path))

    try:
        # Run ffmpeg
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except subprocess.SubprocessError as e:
        raise MediaError(f"Failed to extract audio from {video_path}: {str(e)}")
