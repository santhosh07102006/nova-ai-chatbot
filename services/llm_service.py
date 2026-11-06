import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "gemini-3.5-flash-lite"

load_dotenv(PROJECT_ROOT / ".env")


class GeminiServiceError(RuntimeError):
    """Raised when a Gemini request cannot be completed."""


def generate_response(messages: list[dict[str, str]]) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiServiceError(
            "GEMINI_API_KEY is missing. Add your key to the project's .env file."
        )

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=60_000),
    )
    try:
        contents = [
            types.Content(
                role="model" if message["role"] == "assistant" else "user",
                parts=[types.Part.from_text(text=message["content"])],
            )
            for message in messages
        ]
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
        )
    except errors.APIError as exc:
        if exc.code == 504:
            raise GeminiServiceError(
                "Gemini returned HTTP 504 (gateway timeout). Its model service "
                "did not respond in time; try again later or use a faster model."
            ) from exc
        if exc.code == 429:
            raise GeminiServiceError(
                "Gemini's API rate limit or quota was reached. Wait a little "
                "while before trying again, or check your Google AI Studio quota."
            ) from exc
        raise GeminiServiceError(
            f"Gemini API returned HTTP {exc.code}. Check the key, model "
            "access, and API quota."
        ) from exc
    except httpx.TimeoutException as exc:
        raise GeminiServiceError(
            "The Gemini request timed out after 60 seconds. Check your network "
            "connection and try again."
        ) from exc
    except httpx.HTTPError as exc:
        raise GeminiServiceError(
            "Could not reach the Gemini API. Check your network connection."
        ) from exc
    finally:
        client.close()

    response_text = response.text
    if not response_text:
        raise GeminiServiceError("Gemini returned no text for this request.")

    return response_text
