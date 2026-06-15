"""Utilidades comunes para trazabilidad, evidencias y sanitizado."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .models import PipelineStep


# Campos/headers sensibles que pueden aparecer en respuestas o errores de Idonia/Recog.
SENSITIVE_KEY_PARTS = (
    "authorization",
    "x-api-key",
    "x_api_key",
    "api_key",
    "apikey",
    "password",
    "pin",
)

T = TypeVar("T")
MADRID_TIMEZONE = ZoneInfo("Europe/Madrid")


def run_step(
    evidence: Any,
    name: str,
    action: Callable[[], T],
    logger: logging.Logger,
) -> T:
    """Ejecuta un paso, registra su estado y añade el resultado resumido a la evidencia."""

    logger.info("Ejecutando paso: %s", name)
    try:
        result = action()
    except Exception as exc:
        evidence.steps.append(
            PipelineStep(name=name, status="error", error=mask_sensitive_text(str(exc)))
        )
        logger.error("Paso fallido: %s", name)
        raise

    evidence.steps.append(
        PipelineStep(name=name, status="ok", details=summarize_response(result))
    )
    logger.info("Paso completado: %s", name)
    return result


def build_evidence_path(evidence_dir: Path, prefix: str) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir / f"{prefix}_{timestamp_for_file()}.json"


def save_evidence(evidence: BaseModel, evidence_path: Path) -> Path:
    evidence_path.write_text(
        evidence.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )
    return evidence_path


def timestamp_for_file() -> str:
    return datetime.now(MADRID_TIMEZONE).strftime("%Y%m%dT%H%M%S%f")


def summarize_response(value: Any) -> dict[str, Any]:
    """Resume respuestas sin persistir contenido clínico ni secretos."""

    value = sanitize(value)

    if isinstance(value, dict):
        if "pages" in value and "characters" in value:
            return {
                "pages": value["pages"],
                "characters": value["characters"],
            }

        if "uploaded_files" in value:
            file_uuids = [
                file_uuid
                for item in value.get("files", [])
                if isinstance(item, dict)
                for file_uuid in item.get("file_uuids", [])
            ]
            return {
                "uploaded_files": value.get("uploaded_files"),
                "request_file_name": value.get("request_file_name"),
                "file_uuids": file_uuids,
            }

        keys = ("actorId", "realActorId", "scopes")
        summary = {key: value[key] for key in keys if key in value}
        return summary or {"response_keys": list(value.keys())[:20]}

    if isinstance(value, list):
        if not value:
            return {"items": 0}
        if any(isinstance(item, dict) and "URL" in item for item in value):
            return summarize_magic_link_response(value)
        if all(isinstance(item, str) for item in value):
            return {"items": len(value), "file_uuids": value}
        return {"items": len(value), "response": value}

    if isinstance(value, bytes):
        return {"bytes": len(value)}

    if isinstance(value, str):
        return {"characters": len(value)}

    if isinstance(value, Path):
        return {"path": str(value)}

    if value is None:
        return {"response": None}

    return {"response": value}


def summarize_magic_link_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, list):
        return {"response": sanitize(response)}

    return {
        "items": len(response),
        "url_ids": [
            item.get("URL")
            for item in response
            if isinstance(item, dict) and "URL" in item
        ],
        "has_pin": [
            "PIN" in item
            for item in response
            if isinstance(item, dict)
        ],
        "is_expired": [
            item.get("is_expired")
            for item in response
            if isinstance(item, dict) and "is_expired" in item
        ],
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_as_text = str(key).lower()
            if any(part in key_as_text for part in SENSITIVE_KEY_PARTS):
                sanitized[key] = "***"
            else:
                sanitized[key] = sanitize(item)
        return sanitized

    if isinstance(value, list):
        return [sanitize(item) for item in value]

    if isinstance(value, str):
        return mask_sensitive_text(value)

    return value


def mask_sensitive_text(value: str) -> str:
    masked = re.sub(r"(api_key/)[^\s\"']+", r"\1***", value, flags=re.IGNORECASE)
    masked = re.sub(r"(Bearer\s+)[^\s\"']+", r"\1***", masked, flags=re.IGNORECASE)
    masked = re.sub(r"(rrk_)[^\s\"']+", r"\1***", masked, flags=re.IGNORECASE)
    masked = re.sub(
        r"(['\"]?PIN['\"]?\s*[:=]\s*)['\"]?[^,'\"\s}]+",
        r"\1***",
        masked,
        flags=re.IGNORECASE,
    )
    return masked
