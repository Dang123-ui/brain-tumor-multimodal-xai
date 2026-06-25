import os


def get_agent_model():
    """Return the Gemini chat model used by the Agent.

    The API key must come from the environment. Do not hard-code secrets in
    source code. Accepted variables:
    - GOOGLE_API_KEY
    - GEMINI_API_KEY
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY or GEMINI_API_KEY for Agent LLM")

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency langchain-google-genai. Rebuild/install backend requirements."
        ) from exc

    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        temperature=0,
        google_api_key=api_key,
    )

