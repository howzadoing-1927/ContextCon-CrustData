"""Azure OpenAI client for the two configured deployments (fast, decision).

One API family only: Chat Completions with structured output. If AZURE_OPENAI_API_VERSION is set the classic
`AzureOpenAI` client is used with that version; otherwise the Azure v1 endpoint (`<endpoint>/openai/v1/`).
Neither path, nor any model name, is assumed to work until a live smoke run records it.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

from services.core.config import Settings

DeploymentRole = Literal["fast", "decision"]


@dataclass
class ModelCall:
    role: DeploymentRole
    deployment: str
    prompt_version: str
    attempt: int
    output_mode: str
    latency_ms: int
    model_version: str | None = None
    usage: dict = field(default_factory=dict)
    content: str | None = None
    error: str | None = None
    degraded_from: DeploymentRole | None = None

    def ledger(self) -> dict:
        record = asdict(self)
        record.pop("content")
        return record


class ModelUnavailable(Exception):
    def __init__(self, message: str, calls: list[ModelCall]) -> None:
        super().__init__(message)
        self.calls = calls


class ModelClient(Protocol):
    def complete_json(
        self,
        *,
        role: DeploymentRole,
        system: str,
        user: str,
        schema_name: str,
        schema: dict,
        prompt_version: str,
        attempt: int,
    ) -> ModelCall: ...


def _error_text(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}{f' {status}' if status else ''}"


class AzureModelClient:
    def __init__(self, settings: Settings) -> None:
        import openai

        self._openai = openai
        self._deployments = {
            "fast": settings.azure_openai_fast_deployment,
            "decision": settings.azure_openai_decision_deployment,
        }
        timeout = float(settings.provider_timeout_seconds)
        endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
        if settings.azure_openai_api_version:
            self.api_path = f"azure api-version {settings.azure_openai_api_version}"
            self._client = openai.AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                timeout=timeout,
                max_retries=2,
            )
        else:
            self.api_path = "azure v1"
            self._client = openai.OpenAI(
                base_url=f"{endpoint}/openai/v1/", api_key=settings.azure_openai_api_key, timeout=timeout, max_retries=2
            )

    def _route(self, role: DeploymentRole) -> tuple[DeploymentRole, str, DeploymentRole | None]:
        if self._deployments.get(role):
            return role, self._deployments[role], None
        other: DeploymentRole = "decision" if role == "fast" else "fast"
        if self._deployments.get(other):
            return other, self._deployments[other], role
        raise ModelUnavailable("no Azure OpenAI deployment configured", [])

    def _create(self, deployment: str, system: str, user: str, response_format: dict):
        return self._client.chat.completions.create(
            model=deployment,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=response_format,
            max_completion_tokens=1200,
        )

    def complete_json(
        self,
        *,
        role: DeploymentRole,
        system: str,
        user: str,
        schema_name: str,
        schema: dict,
        prompt_version: str,
        attempt: int,
    ) -> ModelCall:
        routed, deployment, degraded_from = self._route(role)
        strict = {"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}}
        modes = [("json_schema_strict", strict), ("json_object_fallback", {"type": "json_object"})]
        calls: list[ModelCall] = []
        for mode, response_format in modes:
            started = time.monotonic()
            try:
                response = self._create(deployment, system, user, response_format)
            except self._openai.BadRequestError as exc:
                calls.append(
                    ModelCall(routed, deployment, prompt_version, attempt, mode, int((time.monotonic() - started) * 1000),
                              error=_error_text(exc), degraded_from=degraded_from)
                )
                if mode == "json_schema_strict" and "response_format" in str(exc).lower():
                    continue
                raise ModelUnavailable("model request rejected", calls) from exc
            except (self._openai.APIError, self._openai.APITimeoutError, self._openai.APIConnectionError) as exc:
                calls.append(
                    ModelCall(routed, deployment, prompt_version, attempt, mode, int((time.monotonic() - started) * 1000),
                              error=_error_text(exc), degraded_from=degraded_from)
                )
                raise ModelUnavailable("model provider unavailable", calls) from exc
            usage = response.usage
            return ModelCall(
                role=routed,
                deployment=deployment,
                prompt_version=prompt_version,
                attempt=attempt,
                output_mode=mode,
                latency_ms=int((time.monotonic() - started) * 1000),
                model_version=getattr(response, "model", None),
                usage={
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                },
                content=response.choices[0].message.content,
                degraded_from=degraded_from,
            )
        raise ModelUnavailable("structured output unsupported", calls)


def parse_json(content: str | None) -> dict:
    if not content:
        raise ValueError("empty model response")
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("model response is not a JSON object")
    return data
