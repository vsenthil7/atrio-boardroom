"""Boardpack PDF exporter.

Uses reportlab to lay out a clean board-pack PDF: cover, attendees, agenda,
positions per agent, dissent rounds, consensus, action list, audit summary.
The file is generated on demand; the URI is stored on the session row.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import AuditReader
from app.db.models import Document, Session as SessionRow, Turn


class BoardpackExporter:
    """Build a PDF report from a session's turns + audit + documents."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def build_for_session(
        self, *, tenant_id: str, session: SessionRow
    ) -> bytes:
        turns = (
            await self._db.execute(
                select(Turn)
                .where(Turn.tenant_id == tenant_id, Turn.session_id == session.id)
                .order_by(Turn.seq_no.asc())
            )
        ).scalars().all()
        docs = (
            await self._db.execute(
                select(Document)
                .where(
                    Document.tenant_id == tenant_id,
                    Document.session_id == session.id,
                )
                .order_by(Document.created_at.asc())
            )
        ).scalars().all()
        audit_events = await AuditReader(self._db).list_for_session(
            tenant_id=tenant_id, session_id=session.id
        )

        return self._render_pdf(
            session=session, turns=turns, docs=docs, audit_count=len(audit_events)
        )

    def _render_pdf(
        self,
        *,
        session: SessionRow,
        turns: list[Turn],
        docs: list[Document],
        audit_count: int,
    ) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=f"ATRIO Board Pack — {session.title or session.id}",
            author="ATRIO Boardroom",
        )
        styles = getSampleStyleSheet()
        h1 = ParagraphStyle(
            "AtrioH1",
            parent=styles["Heading1"],
            fontSize=20,
            leading=24,
            spaceAfter=8,
            textColor=colors.HexColor("#0B0F1E"),
        )
        h2 = ParagraphStyle(
            "AtrioH2",
            parent=styles["Heading2"],
            fontSize=13,
            leading=16,
            spaceAfter=6,
            textColor=colors.HexColor("#0B0F1E"),
        )
        body = ParagraphStyle(
            "AtrioBody",
            parent=styles["BodyText"],
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#171A2B"),
        )
        small = ParagraphStyle(
            "AtrioSmall",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#3B4055"),
        )

        story: list = []

        # --- cover
        story.append(Paragraph("ATRIO Board Pack", h1))
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph(
                f"<b>Session:</b> {session.title or session.id}<br/>"
                f"<b>Session ID:</b> {session.id}<br/>"
                f"<b>Started:</b> {session.started_at.isoformat() if session.started_at else '-'}<br/>"
                f"<b>Ended:</b> "
                f"{session.ended_at.isoformat() if session.ended_at else '(in progress)'}<br/>"
                f"<b>Mode:</b> {session.turn_taking_mode}<br/>"
                f"<b>Language:</b> {session.language_dominant}<br/>"
                f"<b>Consensus:</b> {session.consensus_kind or 'n/a'}<br/>"
                f"<b>Generated:</b> {datetime.utcnow().isoformat()}",
                body,
            )
        )
        story.append(Spacer(1, 6 * mm))

        # --- documents
        if docs:
            story.append(Paragraph("Documents in scope", h2))
            doc_rows = [["Filename", "Kind", "Size (bytes)", "SHA-256"]]
            for d in docs:
                doc_rows.append(
                    [
                        d.filename[:48],
                        d.kind,
                        f"{d.byte_size:,}",
                        d.sha256[:12] + "…",
                    ]
                )
            tbl = Table(doc_rows, hAlign="LEFT", colWidths=[70 * mm, 22 * mm, 30 * mm, 40 * mm])
            tbl.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8ECFF")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9AA1B6")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(tbl)
            story.append(Spacer(1, 6 * mm))

        # --- turns
        story.append(Paragraph("Discussion transcript", h2))
        for t in turns:
            if t.role == "user":
                story.append(
                    Paragraph(
                        f"<b>[USER]</b> {self._html_safe(t.payload_text)}",
                        body,
                    )
                )
            else:
                badge = f"[{(t.agent_id or 'AGENT').upper()}]"
                if t.dissent_round:
                    badge += f" (dissent r{t.dissent_round})"
                meta = (
                    f"<br/><font size=7 color='#888'>"
                    f"model: {t.model_used or '?'} • "
                    f"fallback: {t.model_was_fallback} • "
                    f"latency: {t.latency_ms or 0}ms"
                    f"</font>"
                )
                story.append(
                    Paragraph(
                        f"<b>{badge}</b> {self._html_safe(t.payload_text)}{meta}",
                        body,
                    )
                )
            story.append(Spacer(1, 2 * mm))

        story.append(PageBreak())

        # --- consensus
        story.append(Paragraph("Consensus", h2))
        story.append(
            Paragraph(
                self._html_safe(session.consensus_text or "(no consensus recorded)"),
                body,
            )
        )
        story.append(Spacer(1, 4 * mm))

        # --- action list
        if session.action_list:
            story.append(Paragraph("Action list", h2))
            for a in session.action_list:
                story.append(
                    Paragraph(
                        f"• <b>{a.get('owner', '?')}</b>: "
                        f"{self._html_safe(str(a.get('description', '?')))} "
                        f"(due in {a.get('due_days', '?')} days)",
                        body,
                    )
                )
            story.append(Spacer(1, 4 * mm))

        # --- audit summary footer
        story.append(Paragraph("Audit", h2))
        story.append(
            Paragraph(
                f"Total audit events for this session: <b>{audit_count}</b>. "
                f"Full event log is available via the API at "
                f"<font face='Courier'>/api/v1/audit/sessions/{session.id}</font>.",
                small,
            )
        )

        doc.build(story)
        buf.seek(0)
        return buf.read()

    @staticmethod
    def _html_safe(text: str) -> str:
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
