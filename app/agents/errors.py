"""Public error contract for application-owned agent invocations."""

from __future__ import annotations

from uuid import uuid4


class AgentServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.request_id = uuid4().hex

    def public_detail(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "message": str(self),
            "request_id": self.request_id,
            "retryable": self.retryable,
        }


def translate_agent_error(error: Exception) -> AgentServiceError:
    if isinstance(error, AgentServiceError):
        return error
    pending: list[BaseException] = [error]
    visited: set[int] = set()
    status = None
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        current_status = getattr(current, "status_code", None)
        if current_status is not None:
            status = current_status
        body = getattr(current, "body", None)
        if isinstance(body, dict):
            provider_error = body.get("error", body)
            if isinstance(provider_error, dict) and provider_error.get("code") == "DeploymentNotFound":
                return AgentServiceError(
                    "AI_DEPLOYMENT_NOT_FOUND", "The configured AI deployment is unavailable."
                )
        for nested in (current.__cause__, current.__context__, *current.args):
            if isinstance(nested, BaseException):
                pending.append(nested)
        if isinstance(current, TimeoutError):
            return AgentServiceError(
                "AI_TIMEOUT", "The AI request timed out.", 504, retryable=True
            )
    if status in (401, 403):
        return AgentServiceError("AI_AUTHENTICATION_ERROR", "The AI service is unavailable.")
    if status == 429 or (isinstance(status, int) and status >= 500):
        return AgentServiceError(
            "AI_SERVICE_UNAVAILABLE", "The AI service is temporarily unavailable.",
            503, retryable=True,
        )
    return AgentServiceError("AI_PROVIDER_ERROR", "The AI request could not be completed.")


def agent_response_text(response: object) -> str:
    text = response if isinstance(response, str) else getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    raise AgentServiceError("AI_EMPTY_RESPONSE", "The AI service returned no usable text.")


def agent_tools_called(response: object) -> list[str]:
    calls: dict[str, str] = {}
    completed: set[str] = set()
    for message in getattr(response, "messages", None) or []:
        for content in getattr(message, "contents", None) or []:
            kind = getattr(content, "type", None)
            call_id = getattr(content, "call_id", None)
            if not isinstance(call_id, str):
                continue
            if kind == "function_call":
                name = getattr(content, "name", None)
                if isinstance(name, str):
                    calls[call_id] = name
            elif kind == "function_result" and not getattr(content, "exception", None):
                completed.add(call_id)
    return list(dict.fromkeys(name for call_id, name in calls.items() if call_id in completed))