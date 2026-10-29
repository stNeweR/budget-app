import httpx

from app.core.config import Settings, get_settings


class LLMError(Exception):
    pass


class LLMClient:
    """Minimal OpenAI-compatible chat completions client with tool calling."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload: dict = {"model": self.settings.llm_model, "messages": messages}
        if tools:
            payload["tools"] = tools

        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        if self.settings.llm_http_referer:
            headers["HTTP-Referer"] = self.settings.llm_http_referer
        if self.settings.llm_title:
            headers["X-Title"] = self.settings.llm_title

        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"Не удалось обратиться к LLM: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError(f"LLM вернул некорректный ответ (HTTP {response.status_code})") from exc

        if isinstance(data, dict) and data.get("error"):
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise LLMError(f"LLM error: {message}")

        if response.status_code >= 300:
            raise LLMError(f"LLM request failed: HTTP {response.status_code}")

        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise LLMError("LLM не вернул вариантов ответа")

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise LLMError("LLM вернул некорректное сообщение")
        return message
