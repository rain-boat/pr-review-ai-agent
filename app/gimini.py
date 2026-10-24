import os

from dotenv import load_dotenv
from google import genai


load_dotenv()


GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)


if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not configured"
    )


client = genai.Client(
    api_key=GEMINI_API_KEY
)


async def test_gemini() -> str:
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=(
            "You are a code review assistant. "
            "Reply with exactly: "
            "Gemini PR reviewer is working."
        ),
    )

    return response.text