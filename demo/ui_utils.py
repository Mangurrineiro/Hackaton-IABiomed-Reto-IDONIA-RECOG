"""Utilidades visuales ligeras para la demo Streamlit."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]

STATUS_LABELS = {
    "pending": "Pendiente",
    "running": "Ejecutando",
    "ok": "Completado",
    "failed": "Error",
    "error": "Error",
}


def apply_base_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp [data-testid="stAppViewContainer"] .block-container {
            padding-top: 4.75rem;
            padding-bottom: 2rem;
            max-width: 1180px;
        }
        .demo-kicker {
            color: #0f766e;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .demo-title {
            color: #111827;
            font-size: 2.4rem;
            font-weight: 750;
            line-height: 1.12;
            margin: 0.15rem 0 0.45rem;
        }
        .demo-subtitle {
            color: #4b5563;
            font-size: 1.05rem;
            line-height: 1.55;
            margin-bottom: 1.1rem;
        }
        .demo-card {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 1rem;
            background: #ffffff;
            margin: 0.45rem 0 0.9rem;
        }
        .demo-card-title {
            color: #111827;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .demo-muted {
            color: #6b7280;
            font-size: 0.92rem;
        }
        .badge {
            border-radius: 999px;
            display: inline-block;
            font-size: 0.78rem;
            font-weight: 700;
            padding: 0.18rem 0.55rem;
        }
        .badge-pending {
            background: #f3f4f6;
            color: #374151;
        }
        .badge-running {
            background: #e0f2fe;
            color: #075985;
        }
        .badge-ok {
            background: #dcfce7;
            color: #166534;
        }
        .badge-error,
        .badge-failed {
            background: #fee2e2;
            color: #991b1b;
        }
        .flow {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            align-items: center;
            margin: 0.7rem 0 1.1rem;
        }
        .flow-step {
            border: 1px solid #d1d5db;
            border-radius: 8px;
            padding: 0.55rem 0.75rem;
            background: #f9fafb;
            color: #111827;
            font-size: 0.9rem;
            font-weight: 650;
        }
        .flow-arrow {
            color: #6b7280;
            font-weight: 700;
        }
        .kv {
            border-bottom: 1px solid #f3f4f6;
            padding: 0.35rem 0;
        }
        .kv span:first-child {
            color: #6b7280;
            display: inline-block;
            min-width: 15rem;
        }
        .qr-box {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            display: inline-block;
            padding: 0.8rem;
            background: #ffffff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str | None) -> str:
    normalized = (status or "pending").lower()
    if normalized == "failed":
        normalized = "error"
    label = STATUS_LABELS.get(normalized, normalized.title())
    return f'<span class="badge badge-{html.escape(normalized)}">{html.escape(label)}</span>'


def render_header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="demo-kicker">{html.escape(kicker)}</div>
        <div class="demo-title">{html.escape(title)}</div>
        <div class="demo-subtitle">{html.escape(subtitle)}</div>
        """,
        unsafe_allow_html=True,
    )


def render_card(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="demo-card">
            <div class="demo-card-title">{html.escape(title)}</div>
            <div class="demo-muted">{html.escape(body)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_flow(steps: list[str]) -> None:
    parts: list[str] = ['<div class="flow">']
    for index, step in enumerate(steps):
        if index:
            parts.append('<span class="flow-arrow">-&gt;</span>')
        parts.append(f'<span class="flow-step">{html.escape(step)}</span>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_key_values(items: dict[str, Any]) -> None:
    rows = []
    for key, value in items.items():
        rows.append(
            '<div class="kv">'
            f"<span>{html.escape(str(key))}</span>"
            f"<strong>{html.escape(format_value(value))}</strong>"
            "</div>"
        )
    st.markdown("\n".join(rows), unsafe_allow_html=True)


def format_value(value: Any) -> str:
    if isinstance(value, Path):
        return format_path(value)
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Si" if value else "No"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    return str(value)


def format_path(value: Path | str | None) -> str:
    if value is None:
        return "-"

    path = value if isinstance(value, Path) else Path(str(value))
    try:
        if path.is_absolute():
            return path.resolve().relative_to(PROJECT_ROOT).as_posix()
        return path.as_posix()
    except (OSError, ValueError):
        return str(value)


def format_bytes(size: int | None) -> str:
    if size is None:
        return "-"
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def evidence_status(evidence_json: dict[str, Any] | None) -> str:
    if not evidence_json:
        return "pending"
    status = str(evidence_json.get("status", "pending")).lower()
    return "ok" if status == "ok" else "error" if status == "failed" else status


def render_evidence_summary(evidence_json: dict[str, Any] | None) -> None:
    if not evidence_json:
        st.info("Todavia no hay evidencia JSON para esta fase.")
        return

    steps = evidence_json.get("steps") or []
    ok_steps = sum(1 for step in steps if step.get("status") == "ok")
    error_steps = sum(1 for step in steps if step.get("status") == "error")
    cols = st.columns(4)
    cols[0].markdown(status_badge(evidence_status(evidence_json)), unsafe_allow_html=True)
    cols[1].metric("Pasos", len(steps))
    cols[2].metric("OK", ok_steps)
    cols[3].metric("Error", error_steps)

    evidence_path = evidence_json.get("evidence_path")
    if evidence_path:
        st.caption(f"Evidencia: {format_path(evidence_path)}")

    if steps:
        st.markdown("**Pasos ejecutados**")
        for step in steps:
            step_cols = st.columns([2.1, 1, 4])
            step_cols[0].write(step.get("name", "-"))
            step_cols[1].markdown(
                status_badge(step.get("status")),
                unsafe_allow_html=True,
            )
            detail = step.get("details") or step.get("error") or ""
            step_cols[2].caption(_short_detail(detail))


def _short_detail(value: Any, limit: int = 180) -> str:
    text = format_value(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
