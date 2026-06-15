"""Cliente para interactuar con la API de Recog."""

from __future__ import annotations

from typing import Any

import requests


class RecogAPIError(RuntimeError):
    """Excepción propia que se lanza cuando hay error de red o la API devuelve un error HTTP."""


class RecogClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        """Cabeceras de Recog: autenticación por X-API-Key."""

        return {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        timeout: int = 60,
        expected_status: int | tuple[int, ...] | None = None,
    ) -> requests.Response:
        """Centraliza llamadas HTTP a Recog y normaliza los errores."""

        url = self._build_url(path)

        try:
            response = self.session.request(
                method=method.upper(),
                url=url,
                headers=self._headers(),
                json=json_body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            self._raise_network_error(method, path, exc)

        self._raise_http_error_if_needed(response, method, path)
        self._raise_unexpected_status_if_needed(response, method, path, expected_status)

        return response

    # -- Métodos para interactuar con endpoints de la API --

    def humanize_text(
        self,
        dictation_report: str,
        timeout: int = 120,
    ) -> bytes:
        """Genera el PDF humanizado para paciente desde el texto del informe."""

        if not dictation_report.strip():
            raise RecogAPIError("El texto del informe original esta vacio.")

        response = self._request(
            "POST",
            "/relisten/dictation/process/report-results",
            json_body={"dictationReport": dictation_report},
            timeout=timeout,
            expected_status=200,
        )

        # Se espera que Recog devuelva un PDF. Si devuelve JSON, HTML o
        # una respuesta vacía, se trata como error antes de llegar al pipeline.
        if not response.content:
            raise RecogAPIError(
                "Respuesta inesperada de Recog "
                "POST /relisten/dictation/process/report-results: respuesta vacia"
            )

        content_type = response.headers.get("content-type", "").lower()
        if "application/pdf" not in content_type:
            raise RecogAPIError(
                "Respuesta inesperada de Recog "
                "POST /relisten/dictation/process/report-results: se esperaba PDF, "
                f"content_type={content_type or '<empty>'}"
            )

        return response.content

    # -- Métodos auxiliares para URLs, errores y validación de respuestas --

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _safe_response_text(response: requests.Response) -> str:
        text = response.text.strip()
        if not text:
            return "<empty>"
        return text[:2000]

    @staticmethod
    def _raise_network_error(
        method: str,
        path: str,
        exc: requests.RequestException,
    ) -> None:
        raise RecogAPIError(
            f"Error de red llamando a Recog {method.upper()} {path}: {exc}"
        ) from exc

    def _raise_http_error_if_needed(
        self,
        response: requests.Response,
        method: str,
        path: str,
    ) -> None:
        """Convierte errores HTTP de Recog en una excepción propia trazable."""

        if response.status_code < 400:
            return

        parsed_error = self._parse_error_response(response)
        raise RecogAPIError(
            "Recog API devolvio error "
            f"{method.upper()} {path}: status_code={response.status_code}, "
            f"error={parsed_error}"
        )

    def _raise_unexpected_status_if_needed(
        self,
        response: requests.Response,
        method: str,
        path: str,
        expected_status: int | tuple[int, ...] | None,
    ) -> None:
        """Detecta respuestas 2xx que no coinciden con lo esperado."""

        if expected_status is None:
            return

        expected_statuses = (
            expected_status if isinstance(expected_status, tuple) else (expected_status,)
        )
        if response.status_code in expected_statuses:
            return

        raise RecogAPIError(
            "Respuesta inesperada de Recog "
            f"{method.upper()} {path}: status_code={response.status_code}, "
            f"expected_status={expected_statuses}, "
            f"response={self._safe_response_text(response)}"
        )

    def _parse_error_response(self, response: requests.Response) -> dict[str, Any] | str:
        try:
            parsed = response.json()
        except ValueError:
            return self._safe_response_text(response)

        if isinstance(parsed, dict):
            return {
                "error": parsed.get("error"),
                "message": parsed.get("message"),
                "raw": parsed,
            }
        return parsed
