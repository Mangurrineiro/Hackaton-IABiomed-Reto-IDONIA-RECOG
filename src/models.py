"""Modelos de datos y evidencias de las fases del reto."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator


MADRID_TIMEZONE = ZoneInfo("Europe/Madrid")


def now_madrid_iso() -> str:
    return datetime.now(MADRID_TIMEZONE).isoformat()


class PatientCase(BaseModel):
    patient_dni: str  # DICOMPatientID enviado a Idonia
    accession_number: str  # DICOMAccessionNumber enviado a Idonia
    study_description: str  # DICOMStudyDescription enviado a Idonia

    @field_validator("patient_dni", "accession_number", "study_description")
    @classmethod
    def clean_route_part(cls, value: str) -> str:
        return value.strip(" /")

    @property
    def idonia_case_route(self) -> str:
        """Ruta técnica del caso en Idonia: DICOMPatientID/DICOMAccessionNumber/DICOMStudyDescription."""
        return f"{self.patient_dni}/{self.accession_number}/{self.study_description}"

    @property
    def idonia_magic_link_route(self) -> str:
        """Ruta de entrega para Magic Link: DICOMPatientID/DICOMAccessionNumber."""
        return f"{self.patient_dni}/{self.accession_number}"


# Representa cada paso del pipeline.
class PipelineStep(BaseModel):
    name: str
    status: str
    timestamp: str = Field(default_factory=now_madrid_iso)
    details: dict[str, Any] | None = None
    error: str | None = None


# Evidencia JSON de Fase 1.
class Phase1Evidence(BaseModel):
    phase: str
    status: str
    patient_dni: str
    accession_number: str
    expected_study_route: str | None = None
    expected_magic_link_route: str | None = None
    started_at: str
    finished_at: str | None = None
    steps: list[PipelineStep] = Field(default_factory=list)
    study_upload_response: Any = None
    report_upload_response: Any = None
    evidence_path: str | None = None


# Evidencia JSON de Fase 2.
class Phase2Evidence(BaseModel):
    phase: str
    status: str
    patient_dni: str
    accession_number: str
    source_report_route: str
    dicom_study_description: str
    expected_humanized_report_route: str
    humanized_report_path: str
    started_at: str
    finished_at: str | None = None
    steps: list[PipelineStep] = Field(default_factory=list)
    recog_response_summary: dict[str, Any] | None = None
    humanized_upload_response: Any = None
    evidence_path: str | None = None


# Evidencia JSON de Fase 3.
class Phase3Evidence(BaseModel):
    phase: str
    status: str
    patient_dni: str
    accession_number: str
    magic_link_route: str
    viewer_url: str
    started_at: str
    finished_at: str | None = None
    steps: list[PipelineStep] = Field(default_factory=list)
    magic_link_response_summary: dict[str, Any] | None = None
    evidence_path: str | None = None
