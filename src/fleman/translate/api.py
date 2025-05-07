import os
import json
import requests
from typing import Dict, Optional, Any


class TranslationError(Exception):
    """Exception raised for errors during translation."""

    pass


def translate_text(
    transcript: Dict[str, Any], target_language: str, api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Translate the transcript text to the target language using DeepL API.

    Args:
        transcript: Dictionary containing transcript data with 'text' key
        target_language: Target language code (e.g., 'ES', 'FR', 'JA')
        api_key: Optional API key (will use DEEPL_API_KEY env var if not provided)

    Returns:
        Updated transcript dictionary with translated text
    """
    # Use provided API key or get from environment
    deepl_api_key = api_key or os.environ.get("DEEPL_API_KEY")
    if not deepl_api_key:
        raise TranslationError(
            "API key is required. Provide it as parameter or set DEEPL_API_KEY environment variable."
        )

    # Extract text to translate
    text = transcript.get("text", "")
    if not text:
        raise TranslationError("No text found in transcript for translation")

    # DeepL API endpoint
    api_url = "https://api-free.deepl.com/v2/translate"

    # Prepare the request headers and payload
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"DeepL-Auth-Key {deepl_api_key}",
    }

    # Standardize language code for DeepL
    # DeepL uses uppercase language codes with some variations (e.g., EN-US, EN-GB)
    # For simplicity, we'll use uppercase codes for DeepL
    deepl_target_lang = target_language.upper()

    # Create a copy of the transcript for the result
    translated_transcript = transcript.copy()

    try:
        # 1. First translate the main text
        payload = {"text": [text], "target_lang": deepl_target_lang}

        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()

        # Parse the response
        result = response.json()

        # Extract translated text from response
        if "translations" in result and len(result["translations"]) > 0:
            translated_text = result["translations"][0]["text"]
        else:
            raise TranslationError("No translation returned from DeepL API")

        # Update the transcript with translated text
        translated_transcript["text"] = translated_text
        translated_transcript["language"] = target_language

        # 2. Translate segments if they exist (important for subtitles)
        segments = transcript.get("segments", [])
        if segments:
            # Collect all segment texts to translate in a batch
            segment_texts = [
                segment["text"] for segment in segments if segment.get("text")
            ]

            if segment_texts:
                # Translate all segment texts in one API call
                payload = {"text": segment_texts, "target_lang": deepl_target_lang}

                response = requests.post(
                    api_url, headers=headers, data=json.dumps(payload)
                )
                response.raise_for_status()

                # Parse the segment translations
                seg_result = response.json()

                if "translations" in seg_result and len(
                    seg_result["translations"]
                ) == len(segment_texts):
                    # Update each segment with its translation
                    translated_segments = []
                    text_index = 0

                    for segment in segments:
                        if segment.get("text"):
                            new_segment = segment.copy()
                            new_segment["text"] = seg_result["translations"][
                                text_index
                            ]["text"]
                            translated_segments.append(new_segment)
                            text_index += 1
                        else:
                            # Keep empty segments as they are
                            translated_segments.append(segment.copy())

                    # Update the segments in the result
                    translated_transcript["segments"] = translated_segments

        return translated_transcript

    except requests.exceptions.RequestException as e:
        raise TranslationError(f"DeepL API request failed: {str(e)}")
    except Exception as e:
        raise TranslationError(f"Translation failed: {str(e)}")


# Alternative implementation using a generic translation API (commented out for now)
"""
def translate_text_generic(
    transcript: Dict[str, Any], 
    target_language: str,
    api_key: Optional[str] = None,
    api_url: str = "https://translation-api-endpoint.com/translate"
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "text": transcript.get("text", ""),
        "source_language": "auto",
        "target_language": target_language
    }
    
    try:
        response = requests.post(
            api_url,
            headers=headers,
            data=json.dumps(payload)
        )
        response.raise_for_status()
        
        result = response.json()
        
        translated_transcript = transcript.copy()
        translated_transcript["text"] = result.get("translated_text", "")
        translated_transcript["language"] = target_language
        
        return translated_transcript
        
    except requests.exceptions.RequestException as e:
        raise TranslationError(f"Translation API request failed: {e}")
"""
