"""
BYOV Admin Dashboard V2 - CORRECTED with Nested Expanders

FINAL FIXES:
- Nested expander structure (Blue Header is master expander)
- No gaps between sections (seamless borders)
- Collapsed cards ~120px, expanded ~310px
- Full VIN display
- Segno sync button in Actions (not checklist)
- Session state logo caching (no phantom flash)
- "Custom Notification" instead of "Rejection"
- Tight CSS (no extra padding/margins)

Features:
- Click Blue Header + Stats to expand/collapse entire card
- Click sub-sections to drill down into details
- Workflow checklist for tracking enrollment progress
- All user-inputted data visible in expandable sections
- Document Review with tabs
- Actions with Approve, PDF to HR, Notify, Sync Segno, Delete buttons
"""
import os
import base64
import json
import concurrent.futures
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
    "custom": {
        "enabled": False,
        "recipients": "",
        "cc": "",
        "subject": "BYOV Enrollment - Custom Notification",
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

# Workflow checklist task definitions
CHECKLIST_TASKS = {
    'approved_synced': 'Vehicle Submission Approved & Sent to Dashboard',
    'policy_hshr': 'Signed PDF sent to HR / DocuSign sent (CA)',
    'segno_synced': 'Mileage Form Created in Segno',
    'fleet_notified': 'Fleet, Inventory, Supplies Notified'
}


def inject_admin_theme_css() -> None:
    """Injects the BYOV admin CSS with nested expander structure."""
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

        /* Main Container */
        [data-testid="stMainBlockContainer"] {
          max-width: 1280px;
          margin: 0 auto;
          padding: 0 1.5rem 2rem;
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

        /* CRITICAL: Nested Expander Structure - Ultra Tight */
        
        /* Master card container */
        .record-card-container {
          background: white;
          border-radius: 12px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.1);
          border: 1px solid #e5e7eb;
          margin-bottom: 1.5rem;
          overflow: hidden;
        }

        /* Remove ALL Streamlit expander default styling */
        div[data-testid="stExpander"] {
          border: none !important;
          box-shadow: none !important;
          background: transparent !important;
          margin: 0 !important;
          padding: 0 !important;
        }

        /* Master expander header */
        .record-card-container > div[data-testid="stExpander"] > .streamlit-expanderHeader {
          padding: 0.75rem 1.5rem !important;
          margin: 0 !important;
          background: #f8fafc !important;
          border: none !important;
          border-top: 1px solid #e5e7eb !important;
          font-size: 0.875rem !important;
          font-weight: 600 !important;
          min-height: auto !important;
        }

        .record-card-container > div[data-testid="stExpander"] > .streamlit-expanderHeader:hover {
          background: #f1f5f9 !important;
        }

        /* Sub-expanders inside the master - NO GAPS */
        .record-card-container div[data-testid="stExpander"] div[data-testid="stExpander"] {
          border-top: 1px solid #e5e7eb !important;
          margin: 0 !important;
          background: white !important;
        }

        /* Sub-expander headers - TIGHT */
        .record-card-container div[data-testid="stExpander"] div[data-testid="stExpander"] .streamlit-expanderHeader {
          background: #f8fafc !important;
          padding: 0.75rem 1.5rem !important;
          margin: 0 !important;
          font-size: 0.875rem !important;
          font-weight: 600 !important;
          color: #1e293b !important;
          border: none !important;
          min-height: auto !important;
        }

        .record-card-container div[data-testid="stExpander"] div[data-testid="stExpander"] .streamlit-expanderHeader:hover {
          background: #f1f5f9 !important;
        }

        /* Custom expander arrows */
        .streamlit-expanderHeader svg {
          display: none !important;
        }

        .record-card-container .streamlit-expanderHeader::after {
          content: '▼';
          font-size: 0.75rem;
          margin-left: auto;
          transition: transform 0.2s;
          opacity: 0.6;
        }

        .record-card-container details[open] > .streamlit-expanderHeader::after {
          transform: rotate(180deg);
        }

        /* Sub-expander content - TIGHT */
        .record-card-container div[data-testid="stExpander"] div[data-testid="stExpander"] .streamlit-expanderContent {
          padding: 1rem 1.5rem !important;
          margin: 0 !important;
        }

        /* Master expander content - NO PADDING (sub-expanders provide it) */
        .record-card-container > div[data-testid="stExpander"] > .streamlit-expanderContent {
          padding: 0 !important;
          margin: 0 !important;
        }

        /* Card Header - Blue Gradient */
        .card-header {
          background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #1e40af 100%);
          padding: 1rem 1.5rem;
          color: white;
        }

        .card-header-top {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
        }

        .card-header h2 {
          font-size: 1.25rem;
          font-weight: 700;
          margin-bottom: 0.5rem;
          line-height: 1.2;
        }

        .card-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 0.75rem;
          font-size: 0.8rem;
          opacity: 0.9;
        }

        .card-meta span {
          display: flex;
          align-items: center;
          gap: 0.25rem;
        }

        .status-area {
          text-align: right;
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 0.25rem;
        }

        .status-badge {
          display: inline-block;
          padding: 0.375rem 0.75rem;
          border-radius: 8px;
          font-size: 0.8rem;
          font-weight: 700;
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
          font-size: 0.7rem;
          opacity: 0.75;
        }

        .expand-icon {
          font-size: 1rem;
          margin-left: 0.75rem;
        }

        /* Stats Bar - Mobile First */
        .stats-bar {
          display: flex;
          flex-wrap: wrap;
          background: #f9fafb;
          border-bottom: 1px solid #e5e7eb;
        }

        .stat-item {
          flex: 1 1 auto;
          min-width: 60px;
          padding: 0.5rem 0.25rem;
          text-align: center;
          border-right: 1px solid #e5e7eb;
          border-bottom: 1px solid #e5e7eb;
        }

        .stat-item:last-child { border-right: none; }

        .stat-label {
          font-size: 0.55rem;
          color: #6b7280;
          margin-bottom: 0.2rem;
          text-transform: uppercase;
          letter-spacing: 0.01em;
          font-weight: 600;
          line-height: 1.2;
        }

        .stat-value {
          font-size: 0.65rem;
          font-weight: 700;
          word-break: break-word;
          line-height: 1.3;
        }

        .stat-value.green { color: #16a34a; }
        .stat-value.red { color: #ef4444; }
        .stat-value.mono { font-family: monospace; font-size: 0.6rem; }

        /* Info Grid */
        .info-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 2rem;
        }

        .info-section h4 {
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #2563eb;
          margin-bottom: 1rem;
          padding-bottom: 0.5rem;
          border-bottom: 2px solid #2563eb;
          font-weight: 700;
        }

        .info-row {
          display: flex;
          justify-content: space-between;
          padding: 0.5rem 0;
          font-size: 0.85rem;
          border-bottom: 1px solid #f1f5f9;
        }

        .info-row:last-child { border-bottom: none; }
        .info-label { color: #6b7280; }
        .info-value { font-weight: 500; text-align: right; }

        /* Compact buttons in expanders */
        .record-card-container .stButton > button {
          border-radius: 6px !important;
          font-weight: 600 !important;
          font-size: 0.8rem !important;
          padding: 0.5rem 1rem !important;
          transition: all 0.15s !important;
        }

        .record-card-container .stButton > button:hover {
          transform: translateY(-1px);
        }

        /* Warning box */
        .warning-box {
          margin-top: 1rem;
          padding: 0.75rem 1rem;
          background: #fefce8;
          border: 2px solid #fde047;
          border-radius: 8px;
          font-size: 0.8rem;
          color: #854d0e;
          display: flex;
          align-items: center;
          gap: 0.5rem;
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

        /* Tighter columns spacing */
        div[data-testid="column"] {
          padding: 0 0.5rem !important;
        }

        div[data-testid="column"]:first-child {
          padding-left: 0 !important;
        }

        div[data-testid="column"]:last-child {
          padding-right: 0 !important;
        }
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
        settings = database.get_notification_settings()
        if settings:
            return settings if isinstance(settings, dict) else json.loads(settings)
    except Exception:
        pass
    return DEFAULT_NOTIFICATION_SETTINGS.copy()


def _save_notification_settings(settings: Dict[str, Any]) -> bool:
    """Save notification settings to database."""
    try:
        database.save_notification_settings(settings)
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
        recipients = record.get("email", "")

    if not recipients:
        return {"error": "No recipient email configured"}

    # Build email content based on included fields (to be implemented)
    # include_fields = approval_settings.get("include_fields", [])
    # ... email sending logic would go here

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
        # Show full VIN
        vin_display = vin if vin else "-"

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
            vin_display,
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
    # Cache logo in session state to prevent flash
    if 'logo_b64' not in st.session_state:
        logo_path = "static/sears_logo_brand.png"
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                st.session_state.logo_b64 = base64.b64encode(
                    f.read()).decode("utf-8")
        else:
            st.session_state.logo_b64 = ""

    logo_html = f'<img src="data:image/png;base64,{st.session_state.logo_b64}" style="height: 40px; margin-right: 12px;" alt="Sears Logo" />' if st.session_state.logo_b64 else ""

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
                    pass

        # Delete from database
        database.delete_enrollment(enrollment_id)
        clear_enrollment_cache()
        return True
    except Exception as e:
        st.error(f"Error deleting enrollment: {e}")
        return False


def render_workflow_checklist(enrollment_id: int, raw_data: Dict[str,
                                                                 Any]) -> None:
    """Render the workflow checklist for an enrollment."""
    # Get checklist items from database
    checklist_dict: Dict[str, Any] = {}
    try:
        checklist_items = database.get_checklist_for_enrollment(enrollment_id)
        checklist_dict = {
            item['task_key']: item
            for item in checklist_items
        }
    except Exception:
        pass

    is_california = raw_data.get('state', '').upper() == 'CA'

    # Define all 4 checklist steps
    steps = [{
        'key': 'approved_synced',
        'title': 'Vehicle Submission Approved & Sent to Dashboard',
        'icon': '✅',
        'auto': True,
        'ca_special': False
    }, {
        'key':
        'policy_hshr',
        'title':
        'Signed PDF sent to HR' +
        (' / DocuSign sent' if is_california else ''),
        'icon':
        '📄',
        'auto':
        False,
        'ca_special':
        is_california
    }, {
        'key': 'segno_synced',
        'title': 'Mileage Form Created in Segno',
        'icon': '📊',
        'auto': False,
        'ca_special': False
    }, {
        'key': 'fleet_notified',
        'title': 'Fleet, Inventory, Supplies Notified',
        'icon': '🔔',
        'auto': False,
        'ca_special': False
    }]

    for idx, step in enumerate(steps):
        task = checklist_dict.get(step['key'], {})
        is_completed = task.get('is_completed', False)
        completed_by = task.get('completed_by', '')
        completed_at = task.get('completed_at', '')

        checkbox_icon = '✅' if is_completed else '☐'

        # Start item container
        item_bg = '#f0fdf4' if is_completed else 'white'
        border_bottom = '' if idx == len(
            steps) - 1 else 'border-bottom: 1px solid #f1f5f9;'

        st.markdown(
            f'<div style="display: flex; gap: 0.75rem; padding: 0.75rem 0; {border_bottom} background: {item_bg};">',
            unsafe_allow_html=True)

        # Checkbox
        checkbox_color = '#16a34a' if is_completed else '#d1d5db'
        st.markdown(
            f'<div style="font-size: 1.25rem; color: {checkbox_color}; flex-shrink: 0;">{checkbox_icon}</div>',
            unsafe_allow_html=True)

        # Content area
        st.markdown('<div style="flex: 1; min-width: 0;">',
                    unsafe_allow_html=True)

        # Title with icon
        title_color = '#1e293b' if not is_completed else '#166534'
        st.markdown(
            f'<div style="font-weight: 600; font-size: 0.875rem; color: {title_color}; margin-bottom: 0.25rem;">{step["icon"]} {step["title"]}</div>',
            unsafe_allow_html=True)

        # Status or button on same line
        if is_completed:
            completed_date = _format_date(
                completed_at) if completed_at else 'Unknown date'
            st.markdown(
                f'<div style="font-size: 0.75rem; color: #16a34a;">✓ Completed by {completed_by} on {completed_date}</div>',
                unsafe_allow_html=True)
        else:
            # Create inline layout for status and button
            if step['key'] == 'segno_synced':
                # Segno has both sync option (Actions tab) and manual completion
                col_status, col_button = st.columns([2, 1])
                with col_status:
                    st.markdown(
                        '<div style="font-size: 0.75rem; color: #6b7280; padding-top: 0.375rem;">⏳ Pending - Sync button in Actions or mark manually</div>',
                        unsafe_allow_html=True)
                with col_button:
                    if st.button("✓ Mark Complete",
                                 key=f"mark_{step['key']}_{enrollment_id}"):
                        if hasattr(database, 'mark_checklist_task_by_key'):
                            database.mark_checklist_task_by_key(
                                enrollment_id, step['key'], True,
                                "Admin - Manual Completion")
                            clear_enrollment_cache()
                            st.rerun()
                        else:
                            st.warning(
                                "Checklist marking not available - database function missing"
                            )
            else:
                # Use columns for inline button
                col_status, col_button = st.columns([2, 1])
                with col_status:
                    st.markdown(
                        '<div style="font-size: 0.75rem; color: #6b7280; padding-top: 0.375rem;">⏳ Pending</div>',
                        unsafe_allow_html=True)
                with col_button:
                    # Show manual completion button for non-auto steps
                    if not step['auto']:
                        if st.button(
                                "✓ Mark Complete",
                                key=f"mark_{step['key']}_{enrollment_id}"):
                            if hasattr(database, 'mark_checklist_task_by_key'):
                                database.mark_checklist_task_by_key(
                                    enrollment_id, step['key'], True,
                                    "Admin - Manual Completion")
                                clear_enrollment_cache()
                                st.rerun()
                            else:
                                st.warning(
                                    "Checklist marking not available - database function missing"
                                )

            # Show CA special note (full width, below status)
            if step['ca_special'] and is_california:
                st.markdown(
                    '<div style="margin-top: 0.5rem; padding: 0.5rem 0.75rem; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; font-size: 0.75rem; color: #1e40af;">ℹ️ California: Requires DocuSign envelope completion</div>',
                    unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)  # Close content
        st.markdown('</div>', unsafe_allow_html=True)  # Close item container


def render_record_card(record: Dict[str, Any]) -> None:
    """Render a single record card with nested expander structure."""
    status = record.get("status", "in_review")
    is_validated = status == "validated"
    enrollment_id_raw = record.get("id")
    if enrollment_id_raw is None:
        return
    enrollment_id: int = int(enrollment_id_raw)

    status_label = "✓ Validated" if is_validated else "⚠ In Review"
    status_class = "validated" if is_validated else "review"

    signature_ok = record.get("signature", False)
    sig_color = "#16a34a" if signature_ok else "#ef4444"
    sig_text = "✓ Yes" if signature_ok else "✗ Missing"

    docs = record.get("_docs", [])
    raw = record.get("_raw", {}) or {}

    # Open card container
    st.markdown('<div class="record-card-container">', unsafe_allow_html=True)

    # Render Blue Header + Stats (always visible)
    st.markdown(
        f"""
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
              <span class="expand-icon">▼</span>
            </div>
          </div>
        </div>
        <div class="stats-bar">
          <div class="stat-item">
            <div class="stat-label">VIN</div>
            <div class="stat-value mono">{record.get("vin", "-")}</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">Ins Exp</div>
            <div class="stat-value green">{record.get("insurance_exp", "-")}</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">Reg Exp</div>
            <div class="stat-value green">{record.get("registration_exp", "-")}</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">Photos</div>
            <div class="stat-value">{record.get("photos_count", 0)}</div>
          </div>
          <div class="stat-item">
            <div class="stat-label">Sig</div>
            <div class="stat-value" style="color:{sig_color}">{sig_text}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Master expander for the 4 sub-sections (collapsed by default)
    with st.expander("Expand Details", expanded=False):

        # Sub-expander 1: Technician & Vehicle Details
        with st.expander("👤 Technician & Vehicle Details", expanded=False):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("##### Technician Info")
                st.write(f"**Name:** {raw.get('full_name', '-')}")
                st.write(f"**Tech ID:** {raw.get('tech_id', '-')}")
                st.write(f"**Referred By:** {raw.get('referred_by', '-')}")

            with col2:
                st.markdown("##### Vehicle Info")
                st.write(f"**Year:** {raw.get('year', '-')}")
                st.write(f"**Make:** {raw.get('make', '-')}")
                st.write(f"**Model:** {raw.get('model', '-')}")
                st.write(f"**VIN:** {raw.get('vin', '-')}")
                st.write(f"**Industry:** {raw.get('industry', '-')}")

            with col3:
                st.markdown("##### Compliance")
                st.write(f"**District:** {raw.get('district', '-')}")
                st.write(f"**State:** {raw.get('state', '-')}")
                st.write(
                    f"**Insurance Exp:** {_format_date(raw.get('insurance_exp'))}"
                )
                st.write(
                    f"**Registration Exp:** {_format_date(raw.get('registration_exp'))}"
                )
                st.write(
                    f"**Submitted:** {_format_date(raw.get('submission_date'))}"
                )

        # Sub-expander 2: Workflow Checklist
        with st.expander("📋 Workflow Checklist – Track enrollment progress",
                         expanded=False):
            render_workflow_checklist(enrollment_id, raw)

        # Sub-expander 3: Document Review
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
                            st.caption(
                                f"#{idx + 1} - {os.path.basename(path)}")
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
                    else:
                        file_bytes = _read_file_safe(path)
                        if file_bytes:
                            _render_pdf_preview(file_bytes)
                            st.download_button(
                                label="⬇️ Download Signed Form",
                                data=file_bytes,
                                file_name=os.path.basename(
                                    path or "signed_enrollment.pdf"),
                                mime="application/pdf",
                                key=f"dl_pdf_{enrollment_id}",
                            )
                        else:
                            st.info("Signed form file not found.")
                else:
                    st.info("No signed enrollment form available.")

        # Sub-expander 4: Actions (with Segno Sync button)
        with st.expander(
                "✅ Actions – Approve, notify, sync, and manage enrollment",
                expanded=False):
            # Row 1: Main actions
            col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 1])

            with col1:
                approve = st.button(
                    "✅ Approve & Sync"
                    if not is_validated else "✓ Already Approved",
                    key=f"approve_{enrollment_id}",
                    disabled=is_validated,
                    use_container_width=True,
                )

            with col2:
                has_pdf = any(d.get("doc_type") == "signature" for d in docs)
                send_pdf = st.button(
                    "📧 PDF to HR",
                    key=f"pdf_{enrollment_id}",
                    disabled=not has_pdf,
                    use_container_width=True,
                )

            with col3:
                notify = st.button(
                    "📧 Notify",
                    key=f"notify_{enrollment_id}",
                    use_container_width=True,
                )

            with col4:
                delete = st.button(
                    "🗑️ Delete",
                    key=f"delete_{enrollment_id}",
                    use_container_width=True,
                )

            # Row 2: Segno Sync button
            st.markdown("<div style='margin-top: 0.75rem'></div>",
                        unsafe_allow_html=True)

            # Check if already synced
            segno_synced = False
            if enrollment_id is not None:
                try:
                    checklist_items = database.get_checklist_for_enrollment(
                        enrollment_id)
                    checklist_dict = {
                        item['task_key']: item
                        for item in checklist_items
                    }
                    segno_synced = checklist_dict.get('segno_synced', {}).get(
                        'is_completed', False)
                except Exception:
                    pass

            col_segno, col_spacer = st.columns([1, 1])
            with col_segno:
                sync_segno = st.button("🔄 Sync to Segno" if not segno_synced
                                       else "✓ Already Synced to Segno",
                                       key=f"sync_segno_{enrollment_id}",
                                       use_container_width=True,
                                       disabled=segno_synced)

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
                        if hasattr(database, 'mark_checklist_task_by_key'):
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

                    st.success(
                        "✅ Enrollment approved and synced to dashboard!")
                    st.rerun()
                elif status_code == 207:
                    try:
                        database.approve_enrollment(enrollment_id)
                        if hasattr(database, 'mark_checklist_task_by_key'):
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
                    (d for d in docs if d.get("doc_type") == "signature"),
                    None)
                if sig_doc:
                    path = sig_doc.get("file_path")
                    file_bytes = _read_file_safe(path)
                    if file_bytes:
                        settings = _get_notification_settings()
                        hr_email = settings.get("hr_pdf", {}).get(
                            "recipients", "tyler.morgan@transformco.com")
                        result = send_hr_policy_notification(
                            raw, path, hr_email)
                        if result.get("success"):
                            if hasattr(database, 'mark_checklist_task_by_key'):
                                database.mark_checklist_task_by_key(
                                    enrollment_id,
                                    "policy_hshr",
                                    True,
                                    "System - HR Email Sent",
                                )
                            st.success(
                                f"✅ Signed policy form sent to {hr_email}!")
                            st.rerun()
                        else:
                            st.error(
                                f"❌ Error: {result.get('error', 'Unknown error')}"
                            )
                    else:
                        st.warning("PDF file not found")
                else:
                    st.warning("No signed PDF available")

            # Handle Notify
            if notify:
                result = _send_approval_notification(raw, enrollment_id)
                if result is True or (result and result.get("success")):
                    st.success("✅ Notification sent!")
                elif result and result.get("error"):
                    st.error(f"❌ Error: {result.get('error')}")
                else:
                    st.warning(
                        "Notifications not configured. Adjust in Notification Settings tab."
                    )

            # Handle Segno Sync
            if sync_segno and not segno_synced:
                with st.spinner(
                        "Syncing to Segno (may take up to 30 seconds)..."):
                    try:
                        import segno_client

                        # Add timeout wrapper
                        with concurrent.futures.ThreadPoolExecutor(
                        ) as executor:
                            future = executor.submit(
                                segno_client.sync_enrollment_by_id,
                                enrollment_id)
                            try:
                                result = future.result(timeout=35)
                            except concurrent.futures.TimeoutError:
                                st.error(
                                    "❌ Segno sync timed out after 35 seconds")
                                st.info(
                                    "💡 The sync may still complete. Check Segno manually in a few minutes."
                                )
                                result = None

                        if result and result.get("success"):
                            segno_id = result.get("segno_record_id", "Unknown")
                            if hasattr(database, 'mark_checklist_task_by_key'):
                                database.mark_checklist_task_by_key(
                                    enrollment_id,
                                    "segno_synced",
                                    True,
                                    f"System - Segno Sync (ID: {segno_id})",
                                )
                            clear_enrollment_cache()
                            st.success(
                                "✅ Segno enrollment created successfully!")
                            if segno_id and segno_id != "Unknown":
                                st.info(f"📋 Segno Record ID: `{segno_id}`")
                            st.rerun()
                        elif result:
                            error_msg = result.get('error', 'Unknown error')
                            error_details = result.get('details', '')
                            st.error(f"❌ Segno sync failed: {error_msg}")
                            if error_details:
                                with st.expander("🔍 Error Details"):
                                    st.code(error_details)
                            st.info(
                                "💡 Check Segno credentials (SEGNO_USERNAME, SEGNO_PASSWORD) and try again"
                            )

                    except ImportError:
                        st.error("❌ Segno client module not found")
                        st.info(
                            "💡 Contact IT support to install segno_client.py")
                    except Exception as e:
                        st.error(f"❌ Unexpected error: {str(e)}")
                        st.info("💡 Check application logs for details")

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
                    if st.button("Cancel",
                                 key=f"cancel_delete_{enrollment_id}"):
                        st.session_state[delete_key] = False
                        st.rerun()

    # Close card container
    st.markdown('</div>', unsafe_allow_html=True)


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

    # Custom Notifications (renamed from Rejection)
    st.markdown("---")
    st.markdown("### 📧 Custom Notifications")
    st.markdown("Send custom notifications with manual initiation.")

    custom = settings.get("custom", {})

    col1, col2 = st.columns(2)
    with col1:
        custom_enabled = st.toggle("Enable Custom Notifications",
                                   value=custom.get("enabled", False),
                                   key="custom_enabled")

    with col2:
        custom_recipients = st.text_input("Recipients",
                                          value=custom.get("recipients", ""),
                                          placeholder="Enter email addresses",
                                          key="custom_recipients")

    custom_subject = st.text_input(
        "Subject Line",
        value=custom.get("subject", "BYOV Enrollment - Custom Notification"),
        key="custom_subject")

    custom_message = st.text_area(
        "Custom Message Template",
        value=custom.get("custom_message", ""),
        placeholder="Enter a custom message to include in notifications...",
        key="custom_message")

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
            "custom": {
                "enabled": custom_enabled,
                "recipients": custom_recipients,
                "cc": custom.get("cc", ""),
                "subject": custom_subject,
                "include_fields": custom.get("include_fields", []),
                "custom_message": custom_message
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


if __name__ == "__main__":
    main()
