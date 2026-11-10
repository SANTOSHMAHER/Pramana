import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config


class ProviderError(RuntimeError):
    """Raised when an LLM provider cannot return a usable response."""


def _request_json(url, payload, headers, timeout=120):
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(3):
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise ProviderError("The LLM provider returned an invalid response.")
                return result
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            if error.code == 429 or 500 <= error.code < 600:
                if attempt < 2:
                    time.sleep(0.25 * (2**attempt))
                    continue
            raise ProviderError(
                f"The LLM provider returned HTTP {error.code}: {details or error.reason}"
            ) from error
        except (URLError, TimeoutError, ConnectionError) as error:
            if attempt < 2:
                time.sleep(0.25 * (2**attempt))
                continue
            raise ProviderError(f"Cannot reach the LLM provider: {error}") from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderError("The LLM provider returned invalid JSON.") from error
    raise ProviderError("The LLM provider request failed after retries.")


def generate(provider, model, messages):
    provider = (provider or config.DEFAULT_PROVIDER).casefold()
    model = (model or "").strip()
    if provider == "ollama":
        chosen_model = model or config.CHAT_MODEL
        response = _request_json(
            f"{config.OLLAMA_URL}/api/chat",
            {
                "model": chosen_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 256, "num_ctx": 4096},
            },
            {},
            timeout=config.OLLAMA_TIMEOUT,
        )
        answer = response.get("message", {}).get("content", "").strip()
    elif provider == "gemini":
        if not config.GEMINI_API_KEY:
            raise ProviderError("Set PRAMANA_GEMINI_API_KEY to use Gemini.")
        chosen_model = model or config.GEMINI_MODEL
        system_instruction = next(
            (message["content"] for message in messages if message["role"] == "system"),
            "",
        )
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
            if message["role"] != "system"
        ]
        payload = {"contents": contents, "generationConfig": {"temperature": 0.2}}
        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        response = _request_json(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{chosen_model}:generateContent",
            payload,
            {"x-goog-api-key": config.GEMINI_API_KEY},
        )
        candidates = response.get("candidates", [])
        answer = "".join(
            part.get("text", "")
            for part in candidates[0].get("content", {}).get("parts", [])
            if isinstance(part.get("text"), str)
        ).strip() if candidates else ""
    elif provider == "openai":
        if not config.OPENAI_API_KEY:
            raise ProviderError("Set PRAMANA_OPENAI_API_KEY to use OpenAI.")
        chosen_model = model or config.OPENAI_MODEL
        response = _request_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": chosen_model,
                "messages": messages,
                "temperature": 0.2,
            },
            {"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        )
        choices = response.get("choices", [])
        answer = (
            choices[0].get("message", {}).get("content", "").strip()
            if choices
            else ""
        )
    else:
        raise ProviderError("Provider must be one of: ollama, gemini, or openai.")
    if not answer:
        raise ProviderError(f"The {provider} model returned an empty answer.")
    return answer
