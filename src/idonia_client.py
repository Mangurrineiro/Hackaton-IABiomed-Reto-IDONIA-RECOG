"""Cliente para interactuar con la API de Idonia Connect Cloud."""

from __future__ import annotations

import base64
import binascii
import hashlib
import time
from pathlib import Path
from typing import Any

import jwt
import requests


class IdoniaAPIError(RuntimeError):
    """Error de red, autenticación o respuesta inesperada de Idonia."""


def _decode_api_secret(api_secret: str) -> bytes:
    """Prepara el API secret de Idonia para firmar JWT con HS256."""

    secret = api_secret[2:] if api_secret.startswith("S2") else api_secret
    if not secret:
        raise ValueError("IDONIA_API_SECRET esta vacio o no es valido.")

    # El padding permite decodificar secretos base64 URL-safe aunque vengan sin "=" finales.
    padded_secret = secret + "=" * (-len(secret) % 4)
    try:
        return base64.urlsafe_b64decode(padded_secret)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "IDONIA_API_SECRET no se pudo decodificar como base64 URL-safe."
        ) from exc


def build_idonia_jwt(
    api_key: str,
    api_secret: str,
    ttl_seconds: int = 300,
) -> str:
    """Construye el JWT HS256 requerido por Idonia.
    PyJWT se encarga de generar cabecera y firma. En el código solo definimos
    el payload exigido por el manual: sub, iat y exp.
    """

    now = int(time.time())
    payload = {
        "sub": api_key,
        "iat": now - ttl_seconds,
        "exp": now + ttl_seconds,
    }
    signing_key = _decode_api_secret(api_secret)
    return jwt.encode(payload, signing_key, algorithm="HS256")


class IdoniaClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()

    def _headers(self) -> dict[str, str]:
        """Genera un JWT nuevo para cada llamada a Idonia."""

        token = build_idonia_jwt(self.api_key, self.api_secret)
        return {
            "Authorization": f"Bearer {token}",
            "accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        timeout: int = 60,
        expected_status: int | tuple[int, ...] | None = None,
    ) -> requests.Response:
        """Centraliza llamadas autenticadas, errores HTTP y status esperados."""

        try:
            response = self.session.request(
                method=method.upper(),
                url=self._build_url(path),
                params=params,
                files=files,
                headers=self._headers(),
                timeout=timeout,
            )
        except requests.RequestException as exc:
            self._raise_network_error(method, path, exc)

        self._raise_http_error_if_needed(response, method, path)
        self._raise_unexpected_status_if_needed(response, method, path, expected_status)
        return response

    # -- Endpoints Idonia usados por el hackathon --

    def whoami(self) -> dict[str, Any]:
        response = self._request("GET", "/whoami")
        parsed = self._parse_response(response)
        return parsed if isinstance(parsed, dict) else {"response": parsed}

    def upload_file_to_destination(
        self,
        destination: str,
        file_path: Path,
        patient_id: str,
        accession_number: str,
        study_description: str,
        upload_file_name: str | None = None,
    ) -> list[str]:
        """Sube un documento o DICOM usando el multipart definido por Idonia."""

        if not file_path.exists() or not file_path.is_file():
            raise IdoniaAPIError(f"No existe el archivo a subir: {file_path}")

        with file_path.open("rb") as file_handle:
            multipart_form_data = {
                "file": (upload_file_name or file_path.name, file_handle),
                "DICOMPatientID": (None, patient_id),
                "DICOMAccessionNumber": (None, accession_number),
                "DICOMStudyDescription": (None, study_description),
            }
            response = self._request(
                "POST",
                f"/files/{destination}",
                files=multipart_form_data,
                timeout=120,
                expected_status=201,
            )

        parsed = self._parse_response(response)
        # Siguiendo el manual de Idonia, se espera que una subida correcta devuelva HTTP 201 y un array de
        # file_uuid. Cualquier otro formato se considera respuesta inesperada.
        if not isinstance(parsed, list) or not all(
            isinstance(item, str) for item in parsed
        ):
            raise IdoniaAPIError(
                "Respuesta inesperada de Idonia "
                f"POST /files/{destination}: se esperaba un array de file_uuid, "
                f"response={parsed}"
            )

        return parsed

    def get_file(self, route: str) -> requests.Response:
        """Descarga un documento desde su ruta exacta en Idonia."""

        response = self._request("GET", "/file", params={"route": route}, timeout=120)
        content_type = response.headers.get("content-type", "").lower()
        # Siguiendo el manual de Idonia, se espera obtener un application/octet-stream.
        # No obstante, tras consulta al soporte, se ha comprobado que para PDFs también puede devolver un application/pdf.
        # Cualquier otro formato se considera respuesta inesperada.
        if (
            "application/octet-stream" not in content_type
            and "application/pdf" not in content_type
        ):
            raise IdoniaAPIError(
                "Respuesta inesperada de Idonia "
                "GET /file: se esperaba application/octet-stream o application/pdf, "
                f"content_type={content_type or '<empty>'}"
            )
        return response

    def get_magic_link(self, route: str, return_expired: bool = False) -> Any:
        """Obtiene un Magic Link existente para la ruta indicada."""

        params: dict[str, Any] = {"route": route}
        if return_expired:
            params["return_expired"] = "true"

        response = self._request(
            "GET",
            "/ml",
            params=params,
            expected_status=(200, 204),
        )
        parsed = self._parse_response(response)
        if parsed is not None and not isinstance(parsed, list):
            raise IdoniaAPIError(
                "Respuesta inesperada de Idonia "
                f"GET /ml: se esperaba array de Magic Link o respuesta vacia, "
                f"response={parsed}"
            )
        return parsed

    def create_magic_link(
        self,
        route: str,
        plain_password: str | None = None,
        expired_creation_mode: str = "create",
    ) -> Any:
        """Crea o recupera un Magic Link para la ruta del estudio."""

        if expired_creation_mode not in {"create", "skip", "update"}:
            raise IdoniaAPIError(
                "expired_creation_mode invalido para /ml. "
                "Valores permitidos: create, skip, update"
            )

        params: dict[str, Any] = {
            "route": route,
            "expired_creation_mode": expired_creation_mode,
        }
        if plain_password:
            params["password"] = self._build_magic_link_password(plain_password)

        response = self._request(
            "PUT",
            "/ml",
            params=params,
            expected_status=(200, 201),
        )
        parsed = self._parse_response(response)
        if not isinstance(parsed, list):
            raise IdoniaAPIError(
                "Respuesta inesperada de Idonia "
                f"PUT /ml: se esperaba array de Magic Link, response={parsed}"
            )
        return parsed

    # -- Utilidades internas --

    @staticmethod
    def _build_magic_link_password(password: str) -> str:
        """Aplica SHA256 y base64 a la password como indica el manual."""

        sha256_hex = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return base64.b64encode(sha256_hex.encode("utf-8")).decode("ascii")

    @staticmethod
    def _parse_response(response: requests.Response) -> Any:
        """Devuelve JSON si existe, texto si no, o None para respuestas vacías."""

        if response.status_code == 204 or not response.content:
            return None

        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            return response.json()

        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _safe_response_text(response: requests.Response) -> str:
        text = response.text.strip()
        if not text:
            return "<empty>"
        return text[:2000]

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _raise_network_error(
        method: str,
        path: str,
        exc: requests.RequestException,
    ) -> None:
        raise IdoniaAPIError(
            f"Error de red llamando a Idonia {method.upper()} {path}: {exc}"
        ) from exc

    def _raise_http_error_if_needed(
        self,
        response: requests.Response,
        method: str,
        path: str,
    ) -> None:
        """Convierte errores HTTP de Idonia en una excepción propia trazable."""

        if response.status_code < 400:
            return

        parsed_error = self._parse_error_response(response)
        raise IdoniaAPIError(
            "Idonia API devolvio error "
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
        """Detecta respuestas 2xx válidas HTTP pero no válidas para el endpoint."""

        if expected_status is None:
            return

        expected_statuses = (
            expected_status if isinstance(expected_status, tuple) else (expected_status,)
        )
        if response.status_code in expected_statuses:
            return

        raise IdoniaAPIError(
            "Respuesta inesperada de Idonia "
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
