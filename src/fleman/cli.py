#!/usr/bin/env python3
import typer
from pathlib import Path
from typing import Optional
import tempfile
from rich.console import Console

from fleman.transcribe.groq import transcribe_audio, WHISPER_MODEL
from fleman.translate.api import translate_text
from fleman.subtitles.generator import create_subtitles
from fleman.utils.media import extract_audio, MediaError
from fleman.encode.subtitle import embed_subtitles, EncodeError

app = typer.Typer(help="Burn Your Dream")
console = Console()


def is_video_file(file_path: Path) -> bool:
    """Check if file is a video based on extension."""
    video_extensions = [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"]
    return file_path.suffix.lower() in video_extensions


def is_audio_file(file_path: Path) -> bool:
    """Check if file is an audio based on extension."""
    audio_extensions = [".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"]
    return file_path.suffix.lower() in audio_extensions


@app.command()
def process(
    media_file: Path = typer.Argument(
        ..., help="Path to the audio/video file to transcribe"
    ),
    target_language: str = typer.Option(
        "en", "--lang", "-l", help="Target language for translation"
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output subtitle file path"
    ),
    groq_api_key: Optional[str] = typer.Option(
        None,
        "--groq-api-key",
        envvar="GROQ_API_KEY",
        help="Groq API key for transcription",
    ),
    deepl_api_key: Optional[str] = typer.Option(
        None,
        "--deepl-api-key",
        envvar="DEEPL_API_KEY",
        help="DeepL API key for translation",
    ),
    model: str = typer.Option(
        WHISPER_MODEL, "--model", "-m", help="Whisper model to use for transcription"
    ),
    source_language: Optional[str] = typer.Option(
        None, "--source-lang", "-s", help="Source language of the audio (optional)"
    ),
    no_translate: bool = typer.Option(
        False, "--no-translate", help="Skip translation step"
    ),
    dual_subtitles: bool = typer.Option(
        False,
        "--dual",
        "-d",
        help="Create dual-language subtitles (translated - English)",
    ),
    keep_extracted: bool = typer.Option(
        False, "--keep-extracted", help="Keep extracted audio file (for video inputs)"
    ),
    encode_video: bool = typer.Option(
        False, "--encode", "-e", help="Encode the video with the generated subtitles"
    ),
    burn_subtitles: bool = typer.Option(
        True,
        "--burn/--no-burn",
        help="Whether to burn subtitles into the video or just mux them as a stream",
    ),
    encoded_output: Optional[Path] = typer.Option(
        None,
        "--encoded-output",
        help="Output path for the encoded video (if --encode is used)",
    ),
    output_format: str = typer.Option(
        "mkv",
        "--format",
        "-f",
        help="Output video format (mkv or mp4). Default is mkv.",
    ),
):
    """
    Process audio/video file: transcribe, translate, and generate subtitle file.
    Optionally encode video with embedded subtitles.
    """
    if not media_file.exists():
        console.print(f"[red]Error:[/red] Media file {media_file} not found")
        raise typer.Exit(1)

    # Validate output format
    if output_format.lower() not in ["mkv", "mp4"]:
        console.print(
            f"[red]Error:[/red] Invalid output format: {output_format}. Use 'mkv' or 'mp4'"
        )
        raise typer.Exit(1)

    # Check if input is a video file and extract audio if needed
    audio_file = media_file
    extracted_audio = None
    is_video = is_video_file(media_file)

    if is_video:
        console.print(f"[blue]Detected video file:[/blue] {media_file}")
        try:
            # Extract audio to a temporary file if not keeping it
            if not keep_extracted:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    extracted_audio = Path(tmp.name)
            else:
                # Create the audio file in the same directory
                extracted_audio = media_file.with_suffix(".wav")

            console.print("[yellow]Extracting audio...[/yellow]")
            audio_file = extract_audio(
                video_path=media_file, output_path=extracted_audio, format="wav"
            )
            console.print("[green]Audio extracted successfully![/green]")
        except MediaError as e:
            console.print(f"[red]Error extracting audio from video:[/red] {str(e)}")
            raise typer.Exit(1)

    # Determine output file if not specified
    if output_file is None:
        # Add language code to file name
        file_stem = media_file.stem
        suffix = ".ass"

        # Determine language suffix for the file name
        if no_translate:
            # Just use "en" if no translation
            lang_suffix = "-en"
        else:
            # For translation use target language, or lang/en for dual
            if dual_subtitles and target_language.lower() != "en":
                lang_suffix = f"-{target_language.lower()}&en"
            else:
                lang_suffix = f"-{target_language.lower()}"

        output_file = media_file.with_name(f"{file_stem}{lang_suffix}{suffix}")

    console.print(f"[blue]Processing[/blue] {media_file}")
    console.print(f"[blue]Using model:[/blue] {model}")

    # Step 1: Transcribe audio using Groq's Whisper API
    console.print("[yellow]Transcribing audio...[/yellow]")
    try:
        transcript = transcribe_audio(
            audio_path=audio_file,
            api_key=groq_api_key,
            model=model,
            language=source_language,
        )
        console.print("[green]Transcription successful![/green]")
    except Exception as e:
        console.print(f"[red]Error during transcription:[/red] {str(e)}")
        # Clean up extracted audio if it was temporary
        if extracted_audio and not keep_extracted and is_video:
            extracted_audio.unlink(missing_ok=True)
        raise typer.Exit(1)

    # Store the original English transcript if we'll need it for dual subtitles
    original_transcript = None
    if dual_subtitles and not no_translate and target_language.lower() != "en":
        original_transcript = transcript.copy()

    # Step 2: Translate text (unless skipped)
    if not no_translate and target_language.lower() != "en":
        console.print(
            f"[yellow]Translating to {target_language} using DeepL...[/yellow]"
        )
        try:
            transcript = translate_text(
                transcript, target_language, api_key=deepl_api_key
            )
            console.print("[green]Translation successful![/green]")
        except Exception as e:
            console.print(f"[red]Error during translation:[/red] {str(e)}")
            console.print("[yellow]Continuing with original transcription...[/yellow]")
            original_transcript = None  # Reset since translation failed

    # Step 3: Generate subtitle file
    console.print(f"[yellow]Generating subtitle file at {output_file}...[/yellow]")
    try:
        create_subtitles(
            transcript,
            output_file,
            original_transcript=original_transcript if dual_subtitles else None,
        )
        console.print("[green]Subtitle file created successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error creating subtitle file:[/red] {str(e)}")
        # Clean up extracted audio if it was temporary
        if extracted_audio and not keep_extracted and is_video:
            extracted_audio.unlink(missing_ok=True)
        raise typer.Exit(1)

    # Step 4: Optionally encode video with embedded subtitles
    if encode_video and is_video:
        # Determine output path for encoded video
        if encoded_output is None:
            suffix = "-subtitled" if burn_subtitles else "-sub-muxed"
            encoded_output = media_file.with_name(
                f"{media_file.stem}{suffix}.{output_format}"
            )
        else:
            # Ensure encoded_output has the correct extension
            encoded_output = encoded_output.with_suffix(f".{output_format}")

        console.print(
            f"[yellow]Encoding video with subtitles to {encoded_output}...[/yellow]"
        )
        try:
            embed_subtitles(
                video_path=media_file,
                subtitle_path=output_file,
                output_path=encoded_output,
                burn_subtitles=burn_subtitles,
                output_format=output_format,
            )
            console.print("[green]Video with subtitles created successfully![/green]")
        except EncodeError as e:
            console.print(f"[red]Error encoding video with subtitles:[/red] {str(e)}")

    # Clean up extracted audio if it was temporary
    if extracted_audio and not keep_extracted and is_video:
        try:
            extracted_audio.unlink(missing_ok=True)
        except Exception:
            pass  # Ignore errors when cleaning up

    console.print(
        f"[green]✓[/green] All processing complete! Subtitle file saved to {output_file}"
    )


if __name__ == "__main__":
    app()
