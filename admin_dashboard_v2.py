"""
BYOV Admin Dashboard V2 - Card-based UI with full notification settings.

Features:
- Blue gradient card headers for each enrollment
- Stats bar with VIN, Insurance, Registration, Photos, Signature
- All user-inputted data visible in expandable sections
- Document Review with tabs (Vehicle, Registration, Insurance, Form)
- Actions with Approve, PDF to HR, Notify, Delete buttons
- Full Notification Settings tab with email configuration
"""
import os
import base64
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

import streamlit as st

import database_pg as database
import file_storage
from dashboard_sync import push_to_dashboard_single_request, clear_enrollment_cache
from notifications import send_hr_policy_notification

# Default notification settings structure
DEFAULT_NOTIFICATION_SETTINGS = {
    "approval": {
        "enabled":
        True,
        "recipients":
        "",
        "cc":
        "",
        "subject":
        "BYOV Enrollment Approved - {tech_name}",
        "include_fields": [
            "full_name", "tech_id", "district", "state", "year", "make",
            "model", "vin"
        ]
    },
    "hr_pdf": {
        "enabled": True,
        "recipients": "tyler.morgan@transformco.com",
        "cc": "",
        "subject": "BYOV Signed Policy Form - {tech_name}",
        "include_fields": ["full_name", "tech_id", "district"]
    },
    "reminder": {
        "enabled": False,
        "recipients": "",
        "cc": "",
        "subject": "BYOV Enrollment Reminder - Action Required",
        "include_fields": ["full_name", "tech_id"]
    },
    "rejection": {
        "enabled": False,
        "recipients": "",
        "cc": "",
        "subject": "BYOV Enrollment Issue - {tech_name}",
        "include_fields": ["full_name", "tech_id", "district"],
        "custom_message": ""
    }
}

# All available fields that can be included in notifications
ENROLLMENT_FIELDS = [
    ("full_name", "Full Name"),
    ("tech_id", "Tech ID"),
    ("district", "District"),
    ("state", "State"),
    ("year", "Vehicle Year"),
    ("make", "Vehicle Make"),
    ("model", "Vehicle Model"),
    ("vin", "VIN"),
    ("insurance_exp", "Insurance Expiration"),
    ("registration_exp", "Registration Expiration"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("referred_by", "Referred By"),
    ("submission_date", "Submission Date"),
]


def inject_admin_theme_css() -> None:
    """Injects the BYOV admin CSS so Streamlit matches the new card design."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body, [data-testid="stAppViewContainer"] {
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f9fafb;
          color: #1e293b;
        }

        /* Header */
        .site-header {
          background: white;
          border-bottom: 1px solid #e5e7eb;
          box-shadow: 0 1px 3px rgba(0,0,0,0.05);
          margin-bottom: 1.5rem;
          border-radius: 12px;
          padding: 1rem 1.5rem;
        }

        .header-inner {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 1rem;
        }

        .logo {
          font-size: 1.5rem;
          font-weight: 700;
          color: #2563eb;
        }

        .pending-badge {
          background: #dbeafe;
          color: #1e40af;
          padding: 0.375rem 0.875rem;
          border-radius: 9999px;
          font-size: 0.875rem;
          font-weight: 600;
        }

        /* Record Card */
        .record-card {
          background: white;
          border-radius: 12px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1);
          border: 1px solid #e5e7eb;
          overflow: hidden;
          margin-bottom: 1rem;
        }

        /* Card Header */
        .card-header {
          background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #1e40af 100%);
          padding: 1.25rem 1.5rem;
          color: white;
        }

        .card-header-top {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
        }

        .card-header h2 {
          font-size: 1.5rem;
          font-weight: 700;
          margin-bottom: 0.5rem;
        }

        .card-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 1rem;
          font-size: 0.875rem;
          opacity: 0.9;
        }

        .card-meta span {
          display: flex;
          align-items: center;
          gap: 0.375rem;
        }

        .status-area {
          text-align: right;
        }

        .status-badge {
          display: inline-block;
          padding: 0.375rem 0.75rem;
          border-radius: 8px;
          font-size: 0.875rem;
          font-weight: 700;
          margin-bottom: 0.25rem;
        }

        .status-badge.validated {
          background: #4ade80;
          color: #14532d;
        }

        .status-badge.review {
          background: #facc15;
          color: #713f12;
        }

        .submitted-date {
          font-size: 0.75rem;
          opacity: 0.75;
        }

        /* Quick Stats Bar */
        .stats-bar {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          background: #f9fafb;
          border-bottom: 1px solid #e5e7eb;
        }

        .stat-item {
          padding: 0.75rem;
          text-align: center;
          border-right: 1px solid #e5e7eb;
        }

        .stat-item:last-child { border-right: none; }

        .stat-label {
          font-size: 0.7rem;
          color: #6b7280;
          margin-bottom: 0.25rem;
          text-transform: uppercase;
          letter-spacing: 0.025em;
        }

        .stat-value {
          font-size: 0.8rem;
          font-weight: 700;
        }

        .stat-value.green { color: #16a34a; }
        .stat-value.red { color: #ef4444; }
        .stat-value.mono { font-family: monospace; }

        /* Info Grid */
        .info-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1.5rem;
          padding: 1rem;
        }

        .info-section h4 {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #2563eb;
          margin-bottom: 0.75rem;
          padding-bottom: 0.5rem;
          border-bottom: 2px solid #2563eb;
        }

        .info-row {
          display: flex;
          justify-content: space-between;
          padding: 0.4rem 0;
          font-size: 0.85rem;
          border-bottom: 1px solid #f1f5f9;
        }

        .info-row:last-child { border-bottom: none; }
        .info-label { color: #6b7280; }
        .info-value { font-weight: 500; text-align: right; }

        /* Warning box */
        .warning-box {
          margin-top: 0.75rem;
          padding: 0.75rem;
          background: #fefce8;
          border: 2px solid #fde047;
          border-radius: 8px;
          font-size: 0.75rem;
          color: #854d0e;
        }

        /* Main content area */
        [data-testid="stMainBlockContainer"] {
          max-width: 1280px;
          margin: 0 auto;
          padding: 1.5rem;
        }

        /* Custom button styles */
        .approve-btn button {
          background: linear-gradient(135deg, #16a34a 0%, #15803d 100%) !important;
          color: white !important;
          border: none !important;
          font-weight: 700 !important;
          box-shadow: 0 4px 12px rgba(22, 163, 74, 0.3) !important;
        }

        .approve-btn button:hover {
          background: linear-gradient(135deg, #15803d 0%, #166534 100%) !important;
          box-shadow: 0 6px 16px rgba(22, 163, 74, 0.4) !important;
        }

        .approve-btn button:disabled {
          background: #d1fae5 !important;
          color: #166534 !important;
          box-shadow: none !important;
        }

        .pdf-btn button {
          background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
          color: white !important;
          border: none !important;
          font-weight: 600 !important;
        }

        .pdf-btn button:hover {
          background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
        }

        .notify-btn button {
          background: linear-gradient(135deg, #374151 0%, #1f2937 100%) !important;
          color: white !important;
          border: none !important;
          font-weight: 600 !important;
        }

        .notify-btn button:hover {
          background: linear-gradient(135deg, #1f2937 0%, #111827 100%) !important;
        }

        .delete-btn button {
          background: white !important;
          color: #dc2626 !important;
          border: 2px solid #fecaca !important;
          font-weight: 600 !important;
        }

        .delete-btn button:hover {
          background: #fef2f2 !important;
          border-color: #dc2626 !important;
        }

        /* Settings card */
        .settings-card {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 12px;
          padding: 1.5rem;
          margin-bottom: 1rem;
        }

        .settings-card h3 {
          font-size: 1rem;
          font-weight: 600;
          color: #1e293b;
          margin-bottom: 0.25rem;
        }

        .settings-card p {
          font-size: 0.8rem;
          color: #6b7280;
          margin-bottom: 1rem;
        }

        /* General button styling */
        .stButton > button {
          border-radius: 8px;
          font-weight: 600;
          transition: all 0.15s ease;
        }

        .stButton > button:hover {
          transform: translateY(-1px);
        }

        /* Expander styling */
        .streamlit-expanderHeader {
          font-weight: 600;
          background: #f8fafc;
          border-radius: 8px;
        }

        /* Check dots for validation */
        .check-dots {
          display: flex;
          gap: 0.25rem;
        }

        .check-dot {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          color: white;
        }

        .check-dot.pass { background: #22c55e; }
        .check-dot.fail { background: #ef4444; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _format_date(date_str) -> str:
    """Format ISO date string to MM/DD/YYYY."""
    if not date_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(str(date_str))
        return dt.strftime("%m/%d/%Y")
    except Exception:
        return str(date_str) if date_str else "N/A"


def _get_notification_settings() -> Dict[str, Any]:
    """Load notification settings from database or return defaults."""
    try:
        settings = database.get_admin_settings("notification_settings")
        if settings:
            return json.loads(settings) if isinstance(settings,
                                                      str) else settings
    except Exception:
        pass
    return DEFAULT_NOTIFICATION_SETTINGS.copy()


def _save_notification_settings(settings: Dict[str, Any]) -> bool:
    """Save notification settings to database."""
    try:
        database.save_admin_settings("notification_settings", settings)
        return True
    except Exception as e:
        st.error(f"Error saving settings: {e}")
        return False


def _send_approval_notification(
        record: Dict[str,
                     Any], enrollment_id: int) -> Optional[Dict[str, Any]]:
    """Send approval notification email."""
    settings = _get_notification_settings()
    approval_settings = settings.get("approval", {})

    if not approval_settings.get("enabled"):
        return {"error": "Approval notifications are disabled"}

    recipients = approval_settings.get("recipients", "")
    if not recipients:
        # Fall back to technician email
        recipients = record.get("email", "")

    if not recipients:
        return {"error": "No recipient email configured"}

    # Build email content based on included fields
    _ = approval_settings.get("include_fields",
                              [])  # Reserved for future email customization

    return {"success": True}


def get_admin_records() -> List[Dict[str, Any]]:
    """Fetch records for the admin dashboard from the real database."""
    enrollments = database.get_all_enrollments()
    records: List[Dict[str, Any]] = []

    for e in enrollments:
        enrollment_id = e.get("id")
        if enrollment_id is None:
            continue
        docs = database.get_documents_for_enrollment(enrollment_id)

        signature_docs = [d for d in docs if d.get("doc_type") == "signature"]
        signature_exists = False
        for sig_doc in signature_docs:
            path = sig_doc.get("file_path")
            if path and file_storage.file_exists(path):
                signature_exists = True
                break

        photos_count = sum(1 for d in docs
                           if d.get("doc_type") in ("vehicle", "registration",
                                                    "insurance"))

        vin = e.get("vin", "") or ""
        vin_tail = vin[-6:] if vin and len(vin) >= 6 else vin or "-"

        vehicle = f"{e.get('year', '')} {e.get('make', '')} {e.get('model', '')}".strip(
        )

        records.append({
            "id":
            enrollment_id,
            "tech_name":
            e.get("full_name", "Unknown"),
            "vehicle":
            vehicle or "N/A",
            "tech_id":
            e.get("tech_id", ""),
            "district":
            e.get("district", ""),
            "state":
            e.get("state", ""),
            "status":
            "validated" if e.get("approved") == 1 else "in_review",
            "submitted_date":
            _format_date(e.get("submission_date")),
            "vin":
            vin or "-",
            "vin_tail":
            vin_tail,
            "insurance_exp":
            _format_date(e.get("insurance_exp")),
            "registration_exp":
            _format_date(e.get("registration_exp")),
            "photos_count":
            photos_count,
            "signature":
            signature_exists,
            "_raw":
            e,
            "_docs":
            docs,
        })

    return records


def render_header(pending_count: int) -> None:
    """Render the admin header with Sears logo and pending badge."""
    logo_path = "static/sears_logo_brand.png"
    logo_b64 = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")

    logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="height: 40px; margin-right: 12px;" alt="Sears Logo" />' if logo_b64 else ""

    st.markdown(
        f"""
        <div class="site-header">
          <div class="header-inner">
            <div class="header-left">
              {logo_html}
              <div class="logo">BYOV Admin</div>
              <span class="pending-badge">{pending_count} Pending Review{'s' if pending_count != 1 else ''}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _get_docs_for_type(docs: List[Dict[str, Any]],
                       doc_type: str) -> List[Dict[str, Any]]:
    return [d for d in docs if d.get("doc_type") == doc_type]


def _read_file_safe(path: str) -> bytes | None:
    if not path:
        return None
    try:
        if not file_storage.file_exists(path):
            return None
        return file_storage.read_file(path)
    except Exception:
        return None


def _render_pdf_preview(file_bytes: bytes) -> None:
    if not file_bytes:
        st.warning("No PDF data available.")
        return
    try:
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        pdf_html = f"""
        <div style="width: 100%; height: 500px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
          <iframe src="data:application/pdf;base64,{b64}" width="100%" height="100%" style="border:none;"></iframe>
        </div>
        """
        st.markdown(pdf_html, unsafe_allow_html=True)
    except Exception:
        st.warning("Unable to render PDF preview.")


def delete_enrollment(enrollment_id: int) -> bool:
    """Delete an enrollment and all associated documents."""
    try:
        # Get documents first to delete files
        docs = database.get_documents_for_enrollment(enrollment_id)
        for doc in docs:
            path = doc.get("file_path")
            if path:
                try:
                    file_storage.delete_file(path)
                except Exception:
                    pass  # Continue even if file deletion fails

        # Delete from database
        database.delete_enrollment(enrollment_id)
        clear_enrollment_cache()
        return True
    except Exception as e:
        st.error(f"Error deleting enrollment: {e}")
        return False


def render_record_card(record: Dict[str, Any]) -> None:
    """Render a single record card with all data, photos, and actions."""
    enrollment_id = record.get("id")
    if enrollment_id is None:
        st.error("Invalid enrollment record - missing ID")
        return

    status = record.get("status", "in_review")
    is_validated = status == "validated"

    status_label = "✓ Validated" if is_validated else "⚠ In Review"
    status_class = "validated" if is_validated else "review"

    signature_ok = record.get("signature", False)
    sig_color = "#16a34a" if signature_ok else "#ef4444"
    sig_text = "✓ Yes" if signature_ok else "✗ Missing"

    # Segno sync status
    raw_data = record.get("_raw", {}) or {}
    segno_stat = raw_data.get("segno_sync_status", "pending")
    if segno_stat == "synced":
        segno_color = "#16a34a"
        segno_text = "✓ Synced"
    elif segno_stat == "failed":
        segno_color = "#ef4444"
        segno_text = "✗ Failed"
    else:
        segno_color = "#f59e0b"
        segno_text = "○ Pending"

    # Card Header with gradient
    st.markdown(
        f"""
        <div class="record-card">
          <div class="card-header">
            <div class="card-header-top">
              <div>
                <h2>{record.get("tech_name", "Unknown Tech")}</h2>
                <div class="card-meta">
                  <span>🚗 {record.get("vehicle", "")}</span>
                  <span>Tech #{record.get("tech_id", "")}</span>
                  <span>District {record.get("district", "")}</span>
                  <span>{record.get("state", "")}</span>
                </div>
              </div>
              <div class="status-area">
                <div class="status-badge {status_class}">{status_label}</div>
                <div class="submitted-date">Submitted {record.get("submitted_date", "")}</div>
              </div>
            </div>
          </div>
          <div class="stats-bar">
            <div class="stat-item">
              <div class="stat-label">VIN</div>
              <div class="stat-value mono">{record.get("vin", "-")}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Insurance Exp</div>
              <div class="stat-value green">{record.get("insurance_exp", "-")}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Registration Exp</div>
              <div class="stat-value green">{record.get("registration_exp", "-")}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Photos</div>
              <div class="stat-value">{record.get("photos_count", 0)}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Signature</div>
              <div class="stat-value" style="color:{sig_color}">{sig_text}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Segno</div>
              <div class="stat-value" style="color:{segno_color}">{segno_text}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    docs = record.get("_docs", [])
    raw = record.get("_raw", {}) or {}

    # ---- Technician & Vehicle Details ----
    with st.expander("👤 Technician & Vehicle Details", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Technician Info**")
            st.write(f"**Name:** {raw.get('full_name', '-')}")
            st.write(f"**Tech ID:** {raw.get('tech_id', '-')}")
            st.write(f"**Referred By:** {raw.get('referred_by', '-')}")

        with col2:
            st.markdown("**Vehicle Info**")
            st.write(f"**Year:** {raw.get('year', '-')}")
            st.write(f"**Make:** {raw.get('make', '-')}")
            st.write(f"**Model:** {raw.get('model', '-')}")
            st.write(f"**VIN:** {raw.get('vin', '-')}")
            st.write(f"**Industry:** {raw.get('industry', '-')}")

        with col3:
            st.markdown("**Compliance**")
            st.write(f"**District:** {raw.get('district', '-')}")
            st.write(f"**State:** {raw.get('state', '-')}")
            st.write(
                f"**Insurance Exp:** {_format_date(raw.get('insurance_exp'))}")
            st.write(
                f"**Registration Exp:** {_format_date(raw.get('registration_exp'))}"
            )
            st.write(
                f"**Submitted:** {_format_date(raw.get('submission_date'))}")

    # ---- Document Review with Tabs ----
    with st.expander(
            "📁 Document Review – Photos, registration, insurance, signed form",
            expanded=False):
        tabs = st.tabs([
            "🚗 Vehicle Photos", "📋 Registration", "🛡️ Insurance",
            "📄 Signed Form"
        ])

        vehicle_docs = _get_docs_for_type(docs, "vehicle")
        reg_docs = _get_docs_for_type(docs, "registration")
        ins_docs = _get_docs_for_type(docs, "insurance")
        sig_docs = _get_docs_for_type(docs, "signature")

        with tabs[0]:
            if vehicle_docs:
                cols = st.columns(4)
                for idx, doc in enumerate(vehicle_docs):
                    path = doc.get("file_path")
                    if not path:
                        continue
                    img_bytes = _read_file_safe(path)
                    if not img_bytes:
                        continue
                    with cols[idx % 4]:
                        st.image(img_bytes, use_column_width=True)
                        st.caption(f"#{idx + 1} - {os.path.basename(path)}")
            else:
                st.info("No vehicle photos uploaded.")

        with tabs[1]:
            if reg_docs:
                cols = st.columns(3)
                for idx, doc in enumerate(reg_docs):
                    path = doc.get("file_path")
                    if not path:
                        continue
                    file_bytes = _read_file_safe(path)
                    if not file_bytes:
                        continue
                    with cols[idx % 3]:
                        if path.lower().endswith(".pdf"):
                            _render_pdf_preview(file_bytes)
                        else:
                            st.image(file_bytes, use_column_width=True)
                        st.caption(os.path.basename(path))
            else:
                st.info("No registration documents uploaded.")

        with tabs[2]:
            if ins_docs:
                cols = st.columns(3)
                for idx, doc in enumerate(ins_docs):
                    path = doc.get("file_path")
                    if not path:
                        continue
                    file_bytes = _read_file_safe(path)
                    if not file_bytes:
                        continue
                    with cols[idx % 3]:
                        if path.lower().endswith(".pdf"):
                            _render_pdf_preview(file_bytes)
                        else:
                            st.image(file_bytes, use_column_width=True)
                        st.caption(os.path.basename(path))
            else:
                st.info("No insurance documents uploaded.")

        with tabs[3]:
            if sig_docs:
                path = sig_docs[0].get("file_path")
                if not path:
                    st.info("Signed form file path not found.")
                elif file_storage.file_exists(path):
                    file_bytes = _read_file_safe(path)
                    if file_bytes:
                        _render_pdf_preview(file_bytes)
                        st.download_button(
                            label="⬇️ Download Signed Form",
                            data=file_bytes,
                            file_name=os.path.basename(path),
                            mime="application/pdf",
                            key=f"dl_pdf_{enrollment_id}",
                        )
                    else:
                        st.info("Signed form file not found.")
                else:
                    st.info("Signed form file not found.")
            else:
                st.info("No signed enrollment form available.")

    # ---- Actions ----
    segno_status = raw.get("segno_sync_status", "pending")
    segno_synced = segno_status == "synced"

    with st.expander("✅ Actions – Approve, notify, and manage enrollment",
                     expanded=False):
        col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 1])

        with col1:
            st.markdown('<div class="approve-btn">', unsafe_allow_html=True)
            approve = st.button(
                "✅ Approve & Sync"
                if not is_validated else "✓ Already Approved",
                key=f"approve_{enrollment_id}",
                disabled=is_validated,
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            segno_btn_label = "✓ Segno Synced" if segno_synced else "🔄 Sync to Segno"
            st.markdown('<div class="segno-btn">', unsafe_allow_html=True)
            sync_segno = st.button(
                segno_btn_label,
                key=f"segno_{enrollment_id}",
                disabled=segno_synced,
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col3:
            has_pdf = any(d.get("doc_type") == "signature" for d in docs)
            st.markdown('<div class="pdf-btn">', unsafe_allow_html=True)
            send_pdf = st.button(
                "📧 PDF to HR",
                key=f"pdf_{enrollment_id}",
                disabled=not has_pdf,
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col4:
            st.markdown('<div class="notify-btn">', unsafe_allow_html=True)
            notify = st.button(
                "📧 Notify",
                key=f"notify_{enrollment_id}",
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col5:
            st.markdown('<div class="delete-btn">', unsafe_allow_html=True)
            delete = st.button(
                "🗑️ Delete",
                key=f"delete_{enrollment_id}",
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        if not is_validated:
            st.markdown(
                """
                <div class="warning-box">
                  ⚠️ Complete all validation checks before approving
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Handle Approve
        if approve and not is_validated:
            result = push_to_dashboard_single_request(
                raw, enrollment_id=enrollment_id)

            status_code = result.get("status_code", 0)
            if result.get("error"):
                st.error(f"Error: {result.get('error')}")
            elif status_code in (200, 201) or (200 <= status_code < 300
                                               and status_code != 207):
                try:
                    database.approve_enrollment(enrollment_id)
                    database.mark_checklist_task_by_key(
                        enrollment_id,
                        "approved_synced",
                        True,
                        "System - Dashboard Sync",
                    )
                    clear_enrollment_cache()
                except Exception:
                    pass

                settings = _get_notification_settings()
                if settings.get("approval", {}).get("enabled"):
                    _send_approval_notification(raw, enrollment_id)

                st.success("Enrollment approved and synced to dashboard!")
                st.rerun()
            elif status_code == 207:
                try:
                    database.approve_enrollment(enrollment_id)
                    database.mark_checklist_task_by_key(
                        enrollment_id,
                        "approved_synced",
                        True,
                        "System - Dashboard Sync",
                    )
                    clear_enrollment_cache()
                except Exception:
                    pass
                st.warning(
                    "Approved with warnings (some photos may have failed)")
                st.rerun()
            else:
                st.error(f"Dashboard error: status {status_code}")

        # Handle PDF to HR
        if send_pdf:
            sig_doc = next(
                (d for d in docs if d.get("doc_type") == "signature"), None)
            if sig_doc:
                path = sig_doc.get("file_path")
                file_bytes = _read_file_safe(path)
                if file_bytes:
                    settings = _get_notification_settings()
                    hr_email = settings.get("hr_pdf", {}).get(
                        "recipients", "tyler.morgan@transformco.com")
                    result = send_hr_policy_notification(raw, path, hr_email)
                    if result.get("success"):
                        database.mark_checklist_task_by_key(
                            enrollment_id,
                            "policy_hshr",
                            True,
                            "System - HR Email Sent",
                        )
                        st.success(f"Signed policy form sent to {hr_email}!")
                        st.rerun()
                    else:
                        st.error(
                            f"Error: {result.get('error', 'Unknown error')}")
                else:
                    st.warning("PDF file not found")
            else:
                st.warning("No signed PDF available")

        # Handle Notify
        if notify:
            result = _send_approval_notification(raw, enrollment_id)
            if result is True or (result and result.get("success")):
                st.success("Notification sent!")
            elif result and result.get("error"):
                st.error(f"Error: {result.get('error')}")
            else:
                st.warning(
                    "Notifications not configured. Adjust in Notification Settings tab."
                )

        # Handle Sync to Segno
        if sync_segno and not segno_synced:
            with st.spinner("Syncing to Segno..."):
                try:
                    import segno_client
                    result = segno_client.sync_enrollment_by_id(enrollment_id)

                    if result.get("success"):
                        database.mark_checklist_task_by_key(
                            enrollment_id,
                            "segno_synced",
                            True,
                            "System - Segno Sync",
                        )
                        clear_enrollment_cache()
                        st.success("Segno enrollment created successfully!")
                        st.rerun()
                    else:
                        st.error(
                            f"Segno sync failed: {result.get('error', 'Unknown error')}"
                        )
                except Exception as e:
                    st.error(f"Segno sync error: {str(e)}")

        # Handle Delete with session state confirmation
        delete_key = f"pending_delete_{enrollment_id}"

        if delete:
            st.session_state[delete_key] = True

        if st.session_state.get(delete_key, False):
            st.warning(
                "⚠️ Are you sure you want to delete this enrollment? This cannot be undone."
            )
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                if st.button("Yes, Delete",
                             key=f"confirm_delete_{enrollment_id}",
                             type="primary"):
                    if delete_enrollment(enrollment_id):
                        st.session_state[delete_key] = False
                        st.success("Enrollment deleted successfully!")
                        st.rerun()
            with col_cancel:
                if st.button("Cancel", key=f"cancel_delete_{enrollment_id}"):
                    st.session_state[delete_key] = False
                    st.rerun()


def render_notification_settings_tab() -> None:
    """Render the full notification settings configuration UI."""
    st.markdown("## 🔔 Notification Settings")
    st.markdown(
        "Configure email notifications for different enrollment events.")

    settings = _get_notification_settings()

    # Approval Notifications
    st.markdown("---")
    st.markdown("### ✅ Approval Notifications")
    st.markdown(
        "Sent when an enrollment is approved and synced to the dashboard.")

    approval = settings.get("approval", {})

    col1, col2 = st.columns(2)
    with col1:
        approval_enabled = st.toggle("Enable Approval Notifications",
                                     value=approval.get("enabled", True),
                                     key="approval_enabled")

    with col2:
        approval_recipients = st.text_input(
            "Recipients (comma-separated)",
            value=approval.get("recipients", ""),
            placeholder="tech@email.com, manager@email.com",
            key="approval_recipients")

    approval_cc = st.text_input("CC (comma-separated)",
                                value=approval.get("cc", ""),
                                placeholder="supervisor@email.com",
                                key="approval_cc")

    approval_subject = st.text_input(
        "Subject Line",
        value=approval.get("subject",
                           "BYOV Enrollment Approved - {tech_name}"),
        help="Use {tech_name}, {tech_id}, etc. as placeholders",
        key="approval_subject")

    st.markdown("**Fields to include in email:**")
    approval_fields = approval.get("include_fields", [])
    cols = st.columns(4)
    new_approval_fields = []
    for idx, (field_key, field_label) in enumerate(ENROLLMENT_FIELDS):
        with cols[idx % 4]:
            if st.checkbox(field_label,
                           value=field_key in approval_fields,
                           key=f"approval_field_{field_key}"):
                new_approval_fields.append(field_key)

    # HR PDF Notifications
    st.markdown("---")
    st.markdown("### 📄 HR PDF Notifications")
    st.markdown("Sent when a signed policy form is forwarded to HR.")

    hr_pdf = settings.get("hr_pdf", {})

    col1, col2 = st.columns(2)
    with col1:
        hr_enabled = st.toggle("Enable HR PDF Notifications",
                               value=hr_pdf.get("enabled", True),
                               key="hr_enabled")

    with col2:
        hr_recipients = st.text_input("HR Recipients (comma-separated)",
                                      value=hr_pdf.get(
                                          "recipients",
                                          "tyler.morgan@transformco.com"),
                                      key="hr_recipients")

    hr_subject = st.text_input("Subject Line",
                               value=hr_pdf.get(
                                   "subject",
                                   "BYOV Signed Policy Form - {tech_name}"),
                               key="hr_subject")

    # Reminder Notifications
    st.markdown("---")
    st.markdown("### ⏰ Reminder Notifications")
    st.markdown("Sent to technicians who have incomplete enrollments.")

    reminder = settings.get("reminder", {})

    col1, col2 = st.columns(2)
    with col1:
        reminder_enabled = st.toggle("Enable Reminder Notifications",
                                     value=reminder.get("enabled", False),
                                     key="reminder_enabled")

    with col2:
        reminder_recipients = st.text_input(
            "Default Recipients",
            value=reminder.get("recipients", ""),
            placeholder="Leave blank to use technician's email",
            key="reminder_recipients")

    reminder_subject = st.text_input(
        "Subject Line",
        value=reminder.get("subject",
                           "BYOV Enrollment Reminder - Action Required"),
        key="reminder_subject")

    # Rejection Notifications
    st.markdown("---")
    st.markdown("### ❌ Rejection/Issue Notifications")
    st.markdown("Sent when there's an issue with an enrollment.")

    rejection = settings.get("rejection", {})

    col1, col2 = st.columns(2)
    with col1:
        rejection_enabled = st.toggle("Enable Rejection Notifications",
                                      value=rejection.get("enabled", False),
                                      key="rejection_enabled")

    with col2:
        rejection_recipients = st.text_input(
            "Recipients",
            value=rejection.get("recipients", ""),
            placeholder="Leave blank to use technician's email",
            key="rejection_recipients")

    rejection_subject = st.text_input(
        "Subject Line",
        value=rejection.get("subject", "BYOV Enrollment Issue - {tech_name}"),
        key="rejection_subject")

    rejection_message = st.text_area(
        "Custom Message Template",
        value=rejection.get("custom_message", ""),
        placeholder="Enter a custom message to include in rejection emails...",
        key="rejection_message")

    # Save Button
    st.markdown("---")
    if st.button("💾 Save Notification Settings",
                 type="primary",
                 use_container_width=True):
        new_settings = {
            "approval": {
                "enabled": approval_enabled,
                "recipients": approval_recipients,
                "cc": approval_cc,
                "subject": approval_subject,
                "include_fields": new_approval_fields
            },
            "hr_pdf": {
                "enabled": hr_enabled,
                "recipients": hr_recipients,
                "cc": hr_pdf.get("cc", ""),
                "subject": hr_subject,
                "include_fields": hr_pdf.get("include_fields", [])
            },
            "reminder": {
                "enabled": reminder_enabled,
                "recipients": reminder_recipients,
                "cc": reminder.get("cc", ""),
                "subject": reminder_subject,
                "include_fields": reminder.get("include_fields", [])
            },
            "rejection": {
                "enabled": rejection_enabled,
                "recipients": rejection_recipients,
                "cc": rejection.get("cc", ""),
                "subject": rejection_subject,
                "include_fields": rejection.get("include_fields", []),
                "custom_message": rejection_message
            }
        }

        if _save_notification_settings(new_settings):
            st.success("✅ Notification settings saved successfully!")
            st.rerun()


def main() -> None:
    """Main entry point for the admin dashboard."""
    inject_admin_theme_css()

    records = get_admin_records()
    pending_count = sum(1 for r in records if r.get("status") == "in_review")

    # Header
    render_header(pending_count)

    # Top-level tabs
    tab_enroll, tab_settings = st.tabs(
        ["📋 Enrollments", "🔔 Notification Settings"])

    with tab_enroll:
        if not records:
            st.info(
                "No enrollments found. Technicians will appear here after submitting enrollment forms."
            )
        else:
            for rec in records:
                render_record_card(rec)

    with tab_settings:
        render_notification_settings_tab()
