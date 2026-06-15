"""Demo Streamlit del pipeline Idonia + Recog."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase_runner import (  # noqa: E402
    CONNECTION_ERROR_BASE_URL,
    EVIDENCE_DIR,
    MISSING_REPORT_FILE_NAME,
    MISSING_STUDY_ACCESSION_NUMBER,
    MISSING_STUDY_DESCRIPTION,
    MISSING_STUDY_PATIENT_DNI,
    PhaseRunResult,
    extract_pdf_preview,
    generate_qr_svg_data_uri,
    run_phase,
)
from src.config import Settings, get_settings  # noqa: E402
from src.models import PatientCase  # noqa: E402
from ui_utils import (  # noqa: E402
    apply_base_styles,
    format_bytes,
    format_path,
    render_card,
    render_evidence_summary,
    render_flow,
    render_header,
    render_key_values,
    status_badge,
)


SLIDES = [
    "Vision general",
    "Configuracion",
    "Fase 1 - Idonia",
    "Fase 2 - Recog",
    "Fase 3 - Magic Link",
    "Evidencias",
]
PHASE_LABELS = {
    "phase1": "Fase 1",
    "phase2": "Fase 2",
    "phase3": "Fase 3",
}
STATE_VERSION = "2026-06-15-error-scenarios"


def main() -> None:
    st.set_page_config(
        page_title="Reto Hackathon IA Biomed",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_base_styles()
    _init_session_state()
    settings, settings_error = _load_settings()

    _render_sidebar()

    current_slide = st.session_state["current_slide"]
    if current_slide == 0:
        _slide_overview()
    elif current_slide == 1:
        _slide_configuration(settings, settings_error)
    elif current_slide == 2:
        _slide_phase1(settings, settings_error)
    elif current_slide == 3:
        _slide_phase2(settings, settings_error)
    elif current_slide == 4:
        _slide_phase3(settings_error)
    else:
        _slide_closing(settings)

    _render_footer_navigation()


def _init_session_state() -> None:
    if st.session_state.get("state_version") != STATE_VERSION:
        st.session_state["state_version"] = STATE_VERSION
        st.session_state["phase_results"] = {}
        st.session_state["phase_status"] = {
            phase: "pending"
            for phase in PHASE_LABELS
        }

    if "current_slide" not in st.session_state:
        st.session_state["current_slide"] = 0
    if "phase_results" not in st.session_state:
        st.session_state["phase_results"] = {}
    if "phase_status" not in st.session_state:
        st.session_state["phase_status"] = {
            phase: "pending"
            for phase in PHASE_LABELS
        }


def _load_settings() -> tuple[Settings | None, str | None]:
    try:
        return get_settings(), None
    except Exception as exc:
        return None, str(exc)


def _render_sidebar() -> None:
    st.sidebar.title("Daniel Arias Suárez")
    st.sidebar.caption("Demo local para mostrar el funcionamiento.")
    st.sidebar.divider()

    for index, label in enumerate(SLIDES):
        button_type = "primary" if index == st.session_state["current_slide"] else "secondary"
        if st.sidebar.button(label, key=f"nav_{index}", use_container_width=True, type=button_type):
            st.session_state["current_slide"] = index
            st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("Estado")
    for phase, label in PHASE_LABELS.items():
        status = st.session_state["phase_status"].get(phase, "pending")
        st.sidebar.markdown(
            f"{label}: {status_badge(status)}",
            unsafe_allow_html=True,
        )


def _render_footer_navigation() -> None:
    st.divider()
    cols = st.columns([1, 3, 1])
    with cols[0]:
        if st.button("Anterior", disabled=st.session_state["current_slide"] == 0):
            st.session_state["current_slide"] -= 1
            st.rerun()
    with cols[1]:
        current = st.session_state["current_slide"] + 1
        st.caption(f"Pantalla {current} de {len(SLIDES)}")
    with cols[2]:
        if st.button(
            "Siguiente",
            disabled=st.session_state["current_slide"] == len(SLIDES) - 1,
            type="primary",
        ):
            st.session_state["current_slide"] += 1
            st.rerun()


def _slide_overview() -> None:
    render_header(
        "Reto Hackathon IA Biomed",
        "Interoperabilidad y humanizacion de la informacion medica",
        (
            "Demo visual del flujo Idonia + Recog: desde la ingesta del estudio "
            "hasta la entrega segura mediante Magic Link."
        ),
    )
    cols = st.columns([1, 1])
    with cols[0]:
        render_card(
            "Caso clinico",
            (
                "Paciente asturiano atendido en Cantabria, con RM e informe "
                "medico generados en Sierrallana y seguimiento posterior en Asturias."
            ),
        )
        render_card(
            "Necesidad asistencial",
            (
                "Acceso seguro al estudio, al informe original y a una version "
                "comprensible para paciente y medico."
            ),
        )
    with cols[1]:
        render_card(
            "Solucion propuesta",
            (
                "Interoperabilidad clinica, humanizacion del informe con IA, "
                "entrega segura y trazabilidad completa mediante evidencias JSON."
            ),
        )
        render_card(
            "Como se valida",
            (
                "Cada fase ejecuta APIs reales, deja logs capturados y guarda "
                "una evidencia tecnica sanitizada."
            ),
        )

    st.markdown("### Flujo de demostracion")
    render_flow(
        [
            "Hospital de Sierrallana",
            "Idonia",
            "Recog",
            "Idonia",
            "Magic Link",
            "Paciente / Medico",
        ]
    )


def _slide_configuration(settings: Settings | None, settings_error: str | None) -> None:
    render_header(
        "Configuracion",
        "Caso clinico y entorno de ejecucion",
        "La app carga `.env` como fuente de verdad y solo muestra variables no sensibles.",
    )
    if settings_error or settings is None:
        st.error(f"Configuracion invalida: {settings_error}")
        return

    patient_case = _patient_case(settings)
    render_key_values(
        {
            "IDONIA_BASE_URL": settings.idonia_base_url,
            "IDONIA_DICOM_DESTINATION": settings.idonia_dicom_destination,
            "IDONIA_REPORT_DESTINATION": settings.idonia_report_destination,
            "IDONIA_MAGIC_LINK_ID": settings.idonia_magic_link_id,
            "RECOG_BASE_URL": settings.recog_base_url,
            "PATIENT_DNI": settings.patient_dni,
            "CASE_ACCESSION_NUMBER": settings.case_accession_number,
            "CASE_STUDY_DESCRIPTION": settings.case_study_description,
            "STUDY_FILE_PATH": settings.study_file_path,
            "REPORT_FILE_PATH": settings.report_file_path,
            "HUMANIZED_REPORT_FILE_PATH": settings.humanized_report_file_path,
            "Ruta Idonia del caso": patient_case.idonia_case_route,
            "Ruta Magic Link": patient_case.idonia_magic_link_route,
        }
    )

    st.markdown("**Checks locales**")
    checks = _build_local_checks(settings)
    cols = st.columns(4)
    for index, (label, value) in enumerate(checks.items()):
        with cols[index % len(cols)]:
            st.metric(label, value)

    st.caption(
        "Variables ocultas: IDONIA_API_KEY, IDONIA_API_SECRET, RECOG_API_KEY "
        "e IDONIA_MAGIC_LINK_PASSWORD."
    )


def _slide_phase1(settings: Settings | None, settings_error: str | None) -> None:
    render_header(
        "Fase 1",
        "Ingesta e interoperabilidad con Idonia",
        (
            "Autenticacion JWT, subida de DICOMs individuales, agrupacion por "
            "metadatos DICOM y subida del informe original."
        ),
    )
    dicom_destination = settings.idonia_dicom_destination if settings else "dicom"
    report_destination = settings.idonia_report_destination if settings else "report"
    render_flow(
        [
            "GET /whoami",
            f"POST /files/{dicom_destination}",
            f"POST /files/{report_destination}",
            "evidence/phase1",
        ]
    )
    _phase1_controls(settings_error)
    _render_phase_result("phase1")


def _slide_phase2(settings: Settings | None, settings_error: str | None) -> None:
    render_header(
        "Fase 2",
        "Humanizacion del informe con Recog",
        (
            "Descarga del informe original desde Idonia, extraccion de texto, "
            "procesado con Recog, validacion del PDF y subida del informe para paciente."
        ),
    )
    render_flow(
        [
            "GET /whoami",
            "GET /file",
            "Extraer PDF",
            "POST Recog",
            "Validar PDF",
            "Guardar",
            "Subir a Idonia",
            "evidence/phase2",
        ]
    )
    _phase2_controls(settings_error)
    _render_phase_result("phase2")
    _render_pdf_comparison(settings)


def _slide_phase3(settings_error: str | None) -> None:
    render_header(
        "Fase 3",
        "Entrega segura mediante Magic Link",
        (
            "Generacion o recuperacion del Magic Link, URL final, PIN, "
            "QR visual y evidencia sanitizada."
        ),
    )
    render_flow(["GET /whoami", "PUT /ml", "GET /ml", "QR", "evidence/phase3"])
    _phase3_controls(settings_error)
    _render_magic_link_result()
    _render_phase_result("phase3")


def _slide_closing(settings: Settings | None) -> None:
    render_header(
        "Evidencias",
        "Cierre de la demo",
        (
            "Resumen de los artefactos reales generados por las fases y del "
            "estado global de la ejecucion."
        ),
    )

    rows: list[dict[str, Any]] = []
    for phase, label in PHASE_LABELS.items():
        result = _result_for_phase(phase)
        evidence_path = result.evidence_path if result else None
        status = st.session_state["phase_status"].get(phase, "pending")
        rows.append(
            {
                "fase": label,
                "estado": status,
                "evidencia": format_path(evidence_path) if evidence_path else "No ejecutada en esta sesion",
            }
        )

    st.dataframe(rows, use_container_width=True, hide_index=True)

    generated_files = {
        "Carpeta evidence/logs": format_path(EVIDENCE_DIR),
    }
    if settings is not None:
        generated_files["Informe humanizado PDF"] = format_path(settings.humanized_report_file_path)
    render_key_values(generated_files)

    st.success(
        "La solucion demuestra un flujo reproducible y trazable de "
        "interoperabilidad clinica, humanizacion mediante IA y entrega segura "
        "mediante Magic Link."
    )


def _phase_controls(phase_name: str, label: str, settings_error: str | None) -> None:
    if settings_error:
        st.error(f"No se puede ejecutar la fase: {settings_error}")
        return

    if st.button(label, type="primary", use_container_width=False):
        _run_and_store_phase(phase_name)


def _phase1_controls(settings_error: str | None) -> None:
    if settings_error:
        st.error(f"No se puede ejecutar la fase: {settings_error}")
        return

    cols = st.columns([1, 1, 2])
    with cols[0]:
        if st.button("Ejecutar Fase 1", type="primary", use_container_width=True):
            _run_and_store_phase("phase1")
    with cols[1]:
        if st.button("Simular Error Conexion", use_container_width=True):
            st.session_state["phase_status"]["phase1"] = "running"
            with st.spinner(
                "Ejecutando Fase 1 contra un endpoint Idonia invalido..."
            ):
                result = run_phase(
                    "phase1",
                    idonia_base_url_override=CONNECTION_ERROR_BASE_URL,
                )
            st.session_state["phase_results"]["phase1"] = result
            st.session_state["phase_status"]["phase1"] = "ok" if result.success else "error"
    with cols[2]:
        st.caption(
            "La simulacion usa el mismo pipeline, pero sustituye IDONIA_BASE_URL "
            f"por {CONNECTION_ERROR_BASE_URL} solo durante esta ejecucion."
        )


def _phase2_controls(settings_error: str | None) -> None:
    if settings_error:
        st.error(f"No se puede ejecutar la fase: {settings_error}")
        return

    cols = st.columns([1, 1, 1, 2])
    with cols[0]:
        if st.button("Ejecutar Fase 2", type="primary", use_container_width=True):
            _run_and_store_phase("phase2")
    with cols[1]:
        if st.button("Simular Error Informe", use_container_width=True):
            st.session_state["phase_status"]["phase2"] = "running"
            with st.spinner("Ejecutando Fase 2 con un informe inventado..."):
                result = run_phase(
                    "phase2",
                    original_report_file_name_override=MISSING_REPORT_FILE_NAME,
                )
            st.session_state["phase_results"]["phase2"] = result
            st.session_state["phase_status"]["phase2"] = "ok" if result.success else "error"
    with cols[2]:
        if st.button("Simular Error Recog", use_container_width=True):
            st.session_state["phase_status"]["phase2"] = "running"
            with st.spinner("Ejecutando Fase 2 contra un endpoint Recog invalido..."):
                result = run_phase(
                    "phase2",
                    recog_base_url_override=CONNECTION_ERROR_BASE_URL,
                )
            st.session_state["phase_results"]["phase2"] = result
            st.session_state["phase_status"]["phase2"] = "ok" if result.success else "error"
    with cols[3]:
        st.caption(
            "Las simulaciones usan el mismo pipeline: una cambia el nombre del "
            f"informe a {MISSING_REPORT_FILE_NAME}; la otra cambia RECOG_BASE_URL "
            f"a {CONNECTION_ERROR_BASE_URL} solo durante esa ejecucion."
        )


def _phase3_controls(settings_error: str | None) -> None:
    if settings_error:
        st.error(f"No se puede ejecutar la fase: {settings_error}")
        return

    cols = st.columns([1, 1, 2])
    with cols[0]:
        if st.button("Ejecutar Fase 3", type="primary", use_container_width=True):
            _run_and_store_phase("phase3")
    with cols[1]:
        if st.button("Simular Error Estudio", use_container_width=True):
            st.session_state["phase_status"]["phase3"] = "running"
            with st.spinner("Ejecutando Fase 3 con un estudio inventado..."):
                result = run_phase(
                    "phase3",
                    patient_dni_override=MISSING_STUDY_PATIENT_DNI,
                    accession_number_override=MISSING_STUDY_ACCESSION_NUMBER,
                    study_description_override=MISSING_STUDY_DESCRIPTION,
                )
            st.session_state["phase_results"]["phase3"] = result
            st.session_state["phase_status"]["phase3"] = "ok" if result.success else "error"
    with cols[2]:
        st.caption(
            "La simulacion usa el mismo Magic Link real de Idonia, pero con "
            f"ruta {MISSING_STUDY_PATIENT_DNI}/{MISSING_STUDY_ACCESSION_NUMBER} "
            "solo durante esa ejecucion."
        )


def _run_and_store_phase(phase_name: str) -> None:
    st.session_state["phase_status"][phase_name] = "running"
    with st.spinner(f"Ejecutando {PHASE_LABELS[phase_name]} con APIs reales..."):
        result = run_phase(phase_name)
    st.session_state["phase_results"][phase_name] = result
    st.session_state["phase_status"][phase_name] = "ok" if result.success else "error"


def _render_phase_result(phase_name: str) -> None:
    result = _result_for_phase(phase_name)

    st.markdown("**Resultado**")
    if result is None:
        st.info("Aun no se ha ejecutado esta fase en la sesion actual.")
        return

    evidence_json = result.evidence_json
    evidence_path = result.evidence_path

    if result.success:
        st.success("Fase completada correctamente.")
    else:
        st.error(result.error_message or "La fase ha fallado.")

    if evidence_path:
        st.caption(f"JSON de evidencia: {format_path(evidence_path)}")

    render_evidence_summary(evidence_json)

    if evidence_json:
        with st.expander("Ver JSON de evidencia", expanded=False):
            st.json(_compact_paths_for_display(evidence_json))

    if result is not None:
        with st.expander("Logs capturados", expanded=False):
            log_text = result.logs or "Sin logs capturados."
            st.code(log_text, language="text")
        if result.stdout:
            with st.expander("stdout", expanded=False):
                st.code(result.stdout, language="text")
        if result.stderr:
            with st.expander("stderr", expanded=False):
                st.code(result.stderr, language="text")


def _render_pdf_comparison(settings: Settings | None) -> None:
    st.divider()
    st.markdown("### Informe original vs informe para paciente")
    if settings is None:
        st.warning("No se puede mostrar la comparacion porque la configuracion no cargo.")
        return

    left, right = st.columns(2)
    with left:
        _render_pdf_preview("Informe original", settings.report_file_path, "original_pdf")
    with right:
        _render_pdf_preview(
            "Informe para paciente",
            settings.humanized_report_file_path,
            "humanized_pdf",
        )


def _render_pdf_preview(title: str, path: Path, key: str) -> None:
    preview = extract_pdf_preview(path)
    st.markdown(f"**{title}**")
    render_key_values(
        {
            "Ruta": path,
            "Existe": preview["exists"],
            "Tamano": format_bytes(preview["size_bytes"]),
            "Paginas": preview["pages"],
        }
    )
    if preview["error"]:
        st.warning(preview["error"])
    if preview["text_preview"]:
        st.text_area(
            "Preview limitado",
            value=preview["text_preview"],
            height=180,
            disabled=True,
            key=f"{key}_preview",
        )
    if path.exists():
        st.download_button(
            "Descargar PDF",
            data=path.read_bytes(),
            file_name=path.name,
            mime="application/pdf",
            key=f"{key}_download",
        )


def _render_magic_link_result() -> None:
    result = _result_for_phase("phase3")
    viewer_url = result.viewer_url if result and result.viewer_url else None

    if not viewer_url:
        st.info("El Magic Link aparecera aqui tras ejecutar la Fase 3 en esta sesion.")
        return

    cols = st.columns([1.2, 1])
    with cols[0]:
        render_key_values(
            {
                "URL final": viewer_url,
                "PIN": result.pin if result and result.pin else "Disponible solo tras la ejecucion actual",
            }
        )
        if hasattr(st, "link_button"):
            st.link_button("Abrir Magic Link", viewer_url)
        else:
            st.markdown(f"[Abrir Magic Link]({viewer_url})")
    with cols[1]:
        qr_data_uri = generate_qr_svg_data_uri(viewer_url)
        if qr_data_uri:
            st.markdown(
                f'<div class="qr-box"><img src="{qr_data_uri}" width="220" alt="QR Magic Link"></div>',
                unsafe_allow_html=True,
            )
        elif result and result.qr_ascii:
            st.code(result.qr_ascii, language="text")
        else:
            st.warning("No se pudo generar el QR visual.")


def _build_local_checks(settings: Settings) -> dict[str, str]:
    study_path = settings.study_file_path
    report_path = settings.report_file_path
    humanized_path = settings.humanized_report_file_path
    dicom_count = 0
    if study_path.exists() and study_path.is_dir():
        dicom_count = sum(
            1
            for path in study_path.rglob("*")
            if path.is_file() and not path.name.startswith(".")
        )

    return {
        "Carpeta estudio": "OK" if study_path.exists() else "No existe",
        "DICOMs": str(dicom_count),
        "Informe original": format_bytes(report_path.stat().st_size) if report_path.exists() else "No existe",
        "Informe humanizado": format_bytes(humanized_path.stat().st_size) if humanized_path.exists() else "Pendiente",
        "evidence/logs": "OK" if EVIDENCE_DIR.exists() else "No existe",
    }


def _patient_case(settings: Settings) -> PatientCase:
    return PatientCase(
        patient_dni=settings.patient_dni,
        accession_number=settings.case_accession_number,
        study_description=settings.case_study_description,
    )


def _result_for_phase(phase_name: str) -> PhaseRunResult | None:
    result = st.session_state["phase_results"].get(phase_name)
    return result if isinstance(result, PhaseRunResult) else None


def _compact_paths_for_display(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _compact_paths_for_display(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_compact_paths_for_display(item) for item in value]
    if isinstance(value, Path):
        return format_path(value)
    if isinstance(value, str) and str(PROJECT_ROOT) in value:
        return _compact_project_paths_in_text(value)
    return value


def _compact_project_paths_in_text(value: str) -> str:
    root_backslash = str(PROJECT_ROOT)
    root_slash = PROJECT_ROOT.as_posix()
    compacted = value.replace(root_backslash + "\\", "")
    compacted = compacted.replace(root_backslash + "/", "")
    compacted = compacted.replace(root_slash + "/", "")
    compacted = compacted.replace(root_backslash, ".")
    compacted = compacted.replace(root_slash, ".")
    return compacted.replace("\\", "/")


if __name__ == "__main__":
    main()
