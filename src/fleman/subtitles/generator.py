import pysubs2
from pathlib import Path
import re
from typing import Dict, Any, Optional, List


class SubtitleError(Exception):
    """Exception raised for errors during subtitle generation."""

    pass


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to avoid issues with ffmpeg subtitle filter.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename without spaces and problematic characters
    """
    # Replace spaces with underscores
    sanitized = re.sub(r"\s+", "_", filename)
    # Remove special characters that might cause issues with ffmpeg
    sanitized = re.sub(r"[&?*:;|<>]", "", sanitized)
    return sanitized


def create_subtitles(
    transcript: Dict[str, Any],
    output_file: Path,
    max_chars_per_line: int = 42,
    style: Optional[Dict[str, Any]] = None,
    original_transcript: Optional[Dict[str, Any]] = None,
) -> Path:  # Changed return type to Path
    """
    Create an ASS subtitle file from transcript data.

    Args:
        transcript: Dictionary containing transcript data with 'text' key
        output_file: Path where the subtitle file will be saved
        max_chars_per_line: Maximum characters per subtitle line
        style: Optional custom style settings
        original_transcript: Optional original transcript for dual-language subtitles

    Returns:
        Path to the created subtitle file with sanitized filename
    """
    try:
        # Sanitize the output filename to avoid issues with ffmpeg subtitle filter
        parent_dir = output_file.parent
        output_name = sanitize_filename(output_file.name)
        sanitized_output_file = parent_dir / output_name

        # Extract text from transcript
        text = transcript.get("text", "")
        if not text:
            raise SubtitleError("No text found in transcript for subtitle creation")

        # Create a new subtitle file
        subs = pysubs2.SSAFile()

        # Create default styles if none provided
        if style is None:
            # Style for English text
            en_style = {
                "fontname": "Apple Braille",
                "fontsize": 30,
                "primarycolor": "&H00FFFFFF",  # White
                "secondarycolor": "&H000000FF", 
                "outlinecolor": "&H00000000",  # Black
                "backcolor": "&H00000000",
                "bold": 0,
                "italic": 0,
                "underline": 0,
                "strikeout": 0,
                "scalex": 100,
                "scaley": 100,
                "spacing": 0,
                "angle": 0,
                "borderstyle": 1,
                "outline": 1,
                "shadow": 1,
                "alignment": 2,  # Middle center
                "marginl": 10,
                "marginr": 10,
                "marginv": 5,
                "encoding": 1,
            }
            
            # Style for Chinese text (primary)
            cn_style = {
                "fontname": "PingFang SC",
                "fontsize": 48,
                "primarycolor": "&H00FFFFFF",  # White
                "secondarycolor": "&H000000FF",
                "outlinecolor": "&H00000000",  # Black
                "backcolor": "&H00000000",
                "bold": -1,
                "italic": 0,
                "underline": 0,
                "strikeout": 0,
                "scalex": 100,
                "scaley": 100,
                "spacing": 0,
                "angle": 0,
                "borderstyle": 1,
                "outline": 1,
                "shadow": 1,
                "alignment": 2,  # Middle center
                "marginl": 10,
                "marginr": 10,
                "marginv": 10,
                "encoding": 1,
            }
            
            # Style for Chinese tips
            cn_tip_style = {
                "fontname": "PingFang SC",
                "fontsize": 48,
                "primarycolor": "&H00FFFFFF",  # White
                "secondarycolor": "&H000000FF",
                "outlinecolor": "&H00000000",  # Black
                "backcolor": "&H00000000",
                "bold": -1,
                "italic": 0,
                "underline": 0,
                "strikeout": 0,
                "scalex": 100,
                "scaley": 100,
                "spacing": 0,
                "angle": 0,
                "borderstyle": 1,
                "outline": 1.5,
                "shadow": 1,
                "alignment": 7,  # Bottom left
                "marginl": 10,
                "marginr": 10,
                "marginv": 10,
                "encoding": 1,
            }

            # Add styles to the subtitle file
            subs.styles["EN"] = pysubs2.SSAStyle(**en_style)
            subs.styles["CN"] = pysubs2.SSAStyle(**cn_style)
            subs.styles["CN - tip"] = pysubs2.SSAStyle(**cn_tip_style)
            subs.styles["Default"] = pysubs2.SSAStyle(**cn_style)  # Default style as CN
        else:
            # If custom style is provided, use it
            subs.styles["Default"] = pysubs2.SSAStyle(**style)

        # If we have more information like segments with timestamps, use that
        # Otherwise, create basic subtitles with estimated timing
        if transcript.get("segments") and len(transcript["segments"]) > 0:
            # Get original segments if we're doing dual subtitles
            original_segments = None
            if original_transcript and original_transcript.get("segments"):
                original_segments = original_transcript.get("segments", [])

            for i, segment in enumerate(transcript["segments"]):
                start_time = segment.get("start", 0) * 1000  # Convert to milliseconds
                end_time = segment.get("end", 0) * 1000
                text = segment.get("text", "").strip()
                
                # For dual language subtitles with original_transcript
                if (
                    original_transcript
                    and original_segments
                    and i < len(original_segments)
                    and text
                ):
                    original_text = original_segments[i].get("text", "").strip()
                    
                    # First add the English subtitle (will appear below)
                    subs.events.append(
                        pysubs2.SSAEvent(
                            start=int(start_time),
                            end=int(end_time),
                            text=original_text,
                            style="EN"
                        )
                    )
                    
                    # Then add the Chinese subtitle (will appear above)
                    subs.events.append(
                        pysubs2.SSAEvent(
                            start=int(start_time),
                            end=int(end_time),
                            text=text,
                            style="CN"
                        )
                    )
                # For single language subtitles
                elif text:
                    subs.events.append(
                        pysubs2.SSAEvent(
                            start=int(start_time),
                            end=int(end_time),
                            text=text,
                            style="Default",
                        )
                    )
        else:
            # Split text into sentences or chunks for better readability
            sentences = split_into_sentences(text)
            chunks = create_subtitle_chunks(sentences, max_chars_per_line)

            # For dual subtitles without segments, we need to handle original text differently
            original_chunks = None
            if original_transcript:
                original_sentences = split_into_sentences(
                    original_transcript.get("text", "")
                )
                original_chunks = create_subtitle_chunks(
                    original_sentences, max_chars_per_line
                )

            # Create basic subtitles with estimated timing
            # Each subtitle will be displayed for about 3 seconds
            display_time = 3000  # milliseconds
            start_time = 0

            for i, chunk in enumerate(chunks):
                # Estimate duration based on character count (about 15 chars per second)
                duration = max(display_time, len(chunk) * 1000 // 15)
                end_time = start_time + duration

                # For dual subtitles
                if original_chunks and i < len(original_chunks):
                    # First add the English subtitle (will appear below)
                    subs.events.append(
                        pysubs2.SSAEvent(
                            start=start_time,
                            end=end_time,
                            text=original_chunks[i],
                            style="EN"
                        )
                    )
                    
                    # Then add the Chinese subtitle (will appear above)
                    subs.events.append(
                        pysubs2.SSAEvent(
                            start=start_time,
                            end=end_time,
                            text=chunk,
                            style="CN"
                        )
                    )
                else:
                    subs.events.append(
                        pysubs2.SSAEvent(
                            start=start_time,
                            end=end_time,
                            text=chunk,
                            style="Default"
                        )
                    )

                start_time = end_time + 100  # Small gap between subtitles

        # Save the subtitle file
        subs.save(sanitized_output_file)
        return sanitized_output_file

    except Exception as e:
        raise SubtitleError(f"Failed to create subtitle file: {str(e)}")


def split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences.

    Args:
        text: Text to split

    Returns:
        List of sentences
    """
    # Simple sentence splitting by punctuation
    # In a real implementation, you would use NLP libraries for better sentence segmentation
    import re

    # Split on sentence endings and keep the punctuation with the sentence
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def create_subtitle_chunks(sentences: List[str], max_chars_per_line: int) -> List[str]:
    """
    Create subtitle chunks from sentences, respecting maximum characters per line.

    Args:
        sentences: List of sentences to chunk
        max_chars_per_line: Maximum characters per line

    Returns:
        List of subtitle chunks
    """
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        # If the sentence is very long, split it further
        if len(sentence) > max_chars_per_line * 2:
            words = sentence.split()
            current_line = ""

            for word in words:
                if len(current_line) + len(word) + 1 <= max_chars_per_line:
                    current_line += " " + word if current_line else word
                else:
                    if current_chunk:
                        if (
                            len(current_chunk + "\\N" + current_line)
                            <= max_chars_per_line * 2
                        ):
                            current_chunk += "\\N" + current_line
                        else:
                            chunks.append(current_chunk)
                            current_chunk = current_line
                    else:
                        current_chunk = current_line

                    current_line = word

            # Add the last line
            if current_line:
                if current_chunk:
                    if (
                        len(current_chunk + "\\N" + current_line)
                        <= max_chars_per_line * 2
                    ):
                        current_chunk += "\\N" + current_line
                    else:
                        chunks.append(current_chunk)
                        current_chunk = current_line
                else:
                    current_chunk = current_line
        else:
            # For shorter sentences, try to group them together
            if current_chunk:
                if (
                    len(current_chunk) + len(sentence) + 4 <= max_chars_per_line * 2
                ):  # 4 for " | " separator
                    current_chunk += " | " + sentence
                else:
                    chunks.append(current_chunk)
                    current_chunk = sentence
            else:
                current_chunk = sentence

    # Add the last chunk if there is one
    if current_chunk:
        chunks.append(current_chunk)

    return chunks
