"""
Subtitle embedding functionality using ffmpeg.
"""

import subprocess
from pathlib import Path
from typing import Dict, Optional

from ..utils.media import VideoInfo


class EncodeError(Exception):
    """Exception raised for errors during video encoding."""

    pass


def escape_path_for_ffmpeg(path: Path) -> str:
    """
    Properly escape a path for use in ffmpeg filters.

    Args:
        path: Path to escape

    Returns:
        Escaped path string safe for ffmpeg filters
    """
    # For ffmpeg filter strings, we need to:
    # 1. Convert path to string and normalize slashes
    path_str = str(path).replace("\\", "/")

    # 2. Escape special characters
    # For the subtitles filter, we need to escape colons, backslashes, and single quotes
    path_str = path_str.replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")

    # 3. Wrap in quotes
    return f"'{path_str}'"


def embed_subtitles(
    video_path: Path,
    subtitle_path: Path,
    output_path: Optional[Path] = None,
    font_name: Optional[str] = None,
    font_size: Optional[int] = None,
    font_color: Optional[str] = None,
    outline_width: Optional[float] = None,
    outline_color: Optional[str] = None,
    position: Optional[str] = None,
    encoding_options: Optional[Dict[str, str]] = None,
    burn_subtitles: bool = True,
    copy_video: bool = True,
    output_format: str = "mkv",
) -> Path:
    """
    Embed subtitles into a video using ffmpeg.

    Args:
        video_path: Path to the input video file
        subtitle_path: Path to the subtitle file (ASS, SRT, etc.)
        output_path: Path for the output video file (default: same dir with "-sub" suffix)
        font_name: Font name for the subtitles (when burning in). If None, use style from ASS file.
        font_size: Font size for the subtitles. If None, use style from ASS file.
        font_color: Font color for the subtitles. If None, use style from ASS file.
        outline_width: Width of the text outline. If None, use style from ASS file.
        outline_color: Color of the text outline. If None, use style from ASS file.
        position: Position of subtitles. If None, use style from ASS file.
        encoding_options: Additional ffmpeg encoding options
        burn_subtitles: Whether to burn subtitles into the video (True) or just mux them (False)
        copy_video: Whether to copy video stream directly (True) or re-encode (False)
        output_format: Output container format ("mkv" or "mp4", default is "mkv")

    Returns:
        Path to the output video file with embedded subtitles
    """
    # Check if files exist
    if not video_path.exists():
        raise EncodeError(f"Video file not found: {video_path}")
    if not subtitle_path.exists():
        raise EncodeError(f"Subtitle file not found: {subtitle_path}")

    # Get video info
    try:
        video_info = VideoInfo(video_path)
    except Exception as e:
        raise EncodeError(f"Failed to get video information: {str(e)}")

    # Validate and normalize output format
    output_format = output_format.lower()
    if output_format not in ["mkv", "mp4", "webm"]:
        raise EncodeError(
            f"Unsupported output format: {output_format}. Use 'mkv', 'mp4', or 'webm'"
        )

    # Determine output path if not specified
    if output_path is None:
        output_path = video_path.with_name(f"{video_path.stem}-sub.{output_format}")
    else:
        # Ensure the output path has the correct extension
        if output_path.suffix.lower() not in [f".{output_format}"]:
            output_path = output_path.with_suffix(f".{output_format}")

    # Base ffmpeg command
    cmd = ["ffmpeg", "-y", "-i", str(video_path)]

    # Handle subtitle embedding
    if burn_subtitles:
        # For ASS files, we respect their internal styling by default
        is_ass_file = subtitle_path.suffix.lower() in [".ass", ".ssa"]

        # Properly escape the subtitle path
        escaped_subtitle_path = escape_path_for_ffmpeg(subtitle_path)

        # Build subtitle filter based on whether it's an ASS file and if any style overrides are provided
        if is_ass_file and not any(
            [font_name, font_size, font_color, outline_width, outline_color, position]
        ):
            # Use ASS file as is without style overrides
            subtitle_filter = f"subtitles={escaped_subtitle_path}"
        else:
            # Apply overrides if provided, otherwise use defaults
            force_style_parts = []

            if font_name:
                force_style_parts.append(f"FontName={font_name}")
            if font_size:
                force_style_parts.append(f"FontSize={font_size}")
            if font_color:
                force_style_parts.append(f"PrimaryColour=&H{font_color}")
            if outline_color:
                force_style_parts.append(f"OutlineColour=&H{outline_color}")
            if outline_width:
                force_style_parts.append(f"Outline={outline_width}")
            if position:
                # Map position codes to alignment values
                alignment_map = {
                    "tl": 7,
                    "tc": 8,
                    "tr": 9,  # top row
                    "ml": 4,
                    "mc": 5,
                    "mr": 6,  # middle row
                    "bl": 1,
                    "bc": 2,
                    "br": 3,  # bottom row
                }
                alignment = alignment_map.get(
                    position.lower(), 2
                )  # default to bottom center
                force_style_parts.append(f"Alignment={alignment}")

            # Add BorderStyle=1 (outline + drop shadow) if any style is being forced
            if force_style_parts:
                force_style_parts.append("BorderStyle=1")

            # Create the force_style string if we have any parts
            force_style = (
                f":force_style='{','.join(force_style_parts)}'"
                if force_style_parts
                else ""
            )
            subtitle_filter = f"subtitles={escaped_subtitle_path}{force_style}"

        if copy_video:
            # Copy video codec but apply subtitle filter
            cmd.extend(
                [
                    "-map",
                    "0:v",
                    "-map",
                    "0:a?",
                    "-c:a",
                    "copy",
                    "-vf",
                    subtitle_filter,
                ]
            )

            # Choose video codec based on output format
            if output_format == "webm":
                # WebM requires VP8, VP9 or AV1
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"])
                # WebM requires Vorbis or Opus audio
                cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
            elif output_format == "mp4":
                # For MP4, use h264
                cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast"])
            else:  # mkv - most flexible container
                # If it's h264 or h265, use libx264/libx265 for compatibility
                if video_info.video_codec in ["h264", "avc1"]:
                    cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast"])
                elif video_info.video_codec in ["hevc", "hvc1", "h265"]:
                    cmd.extend(["-c:v", "libx265", "-crf", "22", "-preset", "fast"])
                else:
                    # For other formats, use H.264 for better compatibility
                    cmd.extend(["-c:v", "libx264", "-crf", "18"])
        else:
            # Re-encode with subtitle filter
            cmd.extend(
                [
                    "-vf",
                    subtitle_filter,
                    "-map",
                    "0:a?",
                ]
            )

            # Set appropriate codecs for re-encoding based on container
            if output_format == "webm":
                cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"])
                cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
            elif output_format == "mp4":
                cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast"])
                cmd.extend(["-c:a", "aac", "-b:a", "192k"])
            else:  # mkv
                cmd.extend(["-c:v", "libx264", "-crf", "18", "-preset", "fast"])
                cmd.extend(["-c:a", "copy"])
    else:
        # Just mux subtitles (add them as a stream, not burned in)
        cmd.extend(
            [
                "-i",
                str(subtitle_path),
                "-map",
                "0:v",
                "-map",
                "0:a?",
                "-map",
                "1",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
            ]
        )

        # Choose subtitle codec based on output format
        if output_format == "mp4":
            cmd.extend(["-c:s", "mov_text"])
        elif output_format == "webm":
            # WebM only supports WebVTT subtitles
            # Since we can't convert on the fly, we'll need to warn about this limitation
            raise EncodeError(
                "WebM format only supports WebVTT subtitles when not burning in. "
                "Please use burn_subtitles=True or select mkv/mp4 output format."
            )
        else:  # mkv
            cmd.extend(["-c:s", "copy"])  # MKV can handle various subtitle formats

    # Add any additional encoding options
    if encoding_options:
        for k, v in encoding_options.items():
            cmd.extend([f"-{k}", str(v)])

    # Add output file
    cmd.append(str(output_path))

    try:
        # Run ffmpeg
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path
    except subprocess.SubprocessError as e:
        stderr = e.stderr if hasattr(e, "stderr") and isinstance(e.stderr, str) else ""
        raise EncodeError(f"Failed to embed subtitles: {str(e)}\n{stderr}")
