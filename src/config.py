"""Configuración y validación de variables de entorno."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr, ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]

_REQUIRED_ENV_VARS = (
    "IDONIA_BASE_URL",
    "IDONIA_API_KEY",
    "IDONIA_API_SECRET",
    "IDONIA_DICOM_DESTINATION",
    "IDONIA_REPORT_DESTINATION",
    "IDONIA_MAGIC_LINK_ID",
    "RECOG_BASE_URL",
    "RECOG_API_KEY",
    "PATIENT_DNI",
    "CASE_ACCESSION_NUMBER",
    "CASE_STUDY_DESCRIPTION",
    "STUDY_FILE_PATH",
    "REPORT_FILE_PATH",
    "HUMANIZED_REPORT_FILE_PATH",
)


class Settings(BaseModel):
    """Configuración runtime del flujo Idonia + Recog."""

    project_root: Path = PROJECT_ROOT
    idonia_base_url: str
    idonia_api_key: SecretStr
    idonia_api_secret: SecretStr
    idonia_dicom_destination: str
    idonia_report_destination: str
    idonia_magic_link_id: str
    idonia_magic_link_password: SecretStr | None = None
    recog_base_url: str
    recog_api_key: SecretStr
    patient_dni: str
    case_accession_number: str
    case_study_description: str
    study_file_path: Path
    report_file_path: Path
    humanized_report_file_path: Path


def _read_required_env() -> dict[str, str]:
    missing = []
    values: dict[str, str] = {}

    for name in _REQUIRED_ENV_VARS:
        value = os.getenv(name)
        if value is None or value.strip() == "":
            missing.append(name)
            continue
        values[name] = value.strip()

    if missing:
        raise RuntimeError(
            "Faltan variables obligatorias en el entorno o en .env: "
            + ", ".join(missing)
        )

    return values


def _resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value.strip()


@lru_cache(maxsize=1)
def get_settings(env_file: Path | None = None) -> Settings:
    """Carga `.env`, valida variables obligatorias y resuelve rutas del proyecto."""

    dotenv_path = env_file or PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=dotenv_path, override=False)
    values = _read_required_env()

    payload = {
        "idonia_base_url": values["IDONIA_BASE_URL"].rstrip("/"),
        "idonia_api_key": values["IDONIA_API_KEY"],
        "idonia_api_secret": values["IDONIA_API_SECRET"],
        "idonia_dicom_destination": values["IDONIA_DICOM_DESTINATION"],
        "idonia_report_destination": values["IDONIA_REPORT_DESTINATION"],
        "idonia_magic_link_id": values["IDONIA_MAGIC_LINK_ID"],
        "idonia_magic_link_password": _optional_env("IDONIA_MAGIC_LINK_PASSWORD"),
        "recog_base_url": values["RECOG_BASE_URL"].rstrip("/"),
        "recog_api_key": values["RECOG_API_KEY"],
        "patient_dni": values["PATIENT_DNI"],
        "case_accession_number": values["CASE_ACCESSION_NUMBER"],
        "case_study_description": values["CASE_STUDY_DESCRIPTION"],
        "study_file_path": _resolve_project_path(values["STUDY_FILE_PATH"]),
        "report_file_path": _resolve_project_path(values["REPORT_FILE_PATH"]),
        "humanized_report_file_path": _resolve_project_path(
            values["HUMANIZED_REPORT_FILE_PATH"]
        ),
    }

    try:
        return Settings(**payload)
    except ValidationError as exc:
        raise RuntimeError("Configuracion invalida para Idonia + Recog.") from exc
