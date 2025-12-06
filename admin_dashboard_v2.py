"""
BYOV Admin Dashboard V2 - Card-based UI matching the new design.

This module provides the new admin dashboard layout with:
- Blue gradient card headers for each enrollment
- Stats bar with VIN, Insurance, Registration, Photos, Signature
- Document Review expander with tabs
- Actions expander with styled buttons
"""
import streamlit as st
import os
import base64
from typing import List, Dict, Any
from datetime import datetime

import database
import file_storage
from dashboard_sync import push_to_dashboard_single_request, clear_enrollment_cache
from admin_dashboard import (
    _get_notification_settings,
    _send_approval_notification,
    ENROLLMENT_FIELDS,
)
from notifications import send_hr_policy_notification


def inject_admin_theme_css() -> None:
    """Injects the BYOV admin CSS so Streamlit matches the new card design."""
    st.markdown(
        """
        <style>
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def _format_date(date_str) -> str:
    """Format ISO date string to MM/DD/YYYY."""
    if not date_str:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(str(date_str))
        return dt.strftime("%m/%d/%Y")
    except Exception:
        return str(date_str) if date_str else 'N/A'


def get_admin_records() -> List[Dict[str, Any]]:
    """Fetch records for the admin dashboard from the real database."""
    enrollments = database.get_all_enrollments()
    records = []
    
    for e in enrollments:
        enrollment_id = e.get('id')
        docs = database.get_documents_for_enrollment(enrollment_id)
        
        signature_docs = [d for d in docs if d.get('doc_type') == 'signature']
        signature_exists = False
        for sig_doc in signature_docs:
            path = sig_doc.get('file_path')
            if path and file_storage.file_exists(path):
                signature_exists = True
                break
        
        photos_count = sum(1 for d in docs if d.get('doc_type') in ('vehicle', 'registration', 'insurance'))
        
        vin = e.get('vin', '')
        vin_tail = vin[-6:] if vin and len(vin) >= 6 else vin or '-'
        
        vehicle = f"{e.get('year', '')} {e.get('make', '')} {e.get('model', '')}".strip()
        
        records.append({
            "id": enrollment_id,
            "tech_name": e.get('full_name', 'Unknown'),
            "vehicle": vehicle or 'N/A',
            "tech_id": e.get('tech_id', ''),
            "district": e.get('district', ''),
            "state": e.get('state', ''),
            "status": "validated" if e.get('approved') == 1 else "in_review",
            "submitted_date": _format_date(e.get('submission_date')),
            "vin_tail": vin_tail,
            "insurance_exp": _format_date(e.get('insurance_exp')),
            "registration_exp": _format_date(e.get('registration_exp')),
            "photos_count": photos_count,
            "signature": signature_exists,
            "_raw": e,
            "_docs": docs,
        })
    
    return records


def render_header(pending_count: int) -> None:
    """Render the admin header with logo and pending badge."""
    st.markdown(
        f"""
        <div class="site-header">
          <div class="header-inner">
            <div class="header-left">
              <div class="logo">Sears BYOV Admin</div>
              <span class="pending-badge">{pending_count} Pending Review{'s' if pending_count != 1 else ''}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_record_card(record: Dict[str, Any]) -> None:
    """Render a single record card with layout matching the design."""
    status = record.get("status", "in_review")
    is_validated = status == "validated"
    enrollment_id = record.get("id")

    status_label = "✓ Validated" if is_validated else "⚠ In Review"
    status_class = "validated" if is_validated else "review"

    signature_ok = record.get("signature", False)
    sig_color = "#16a34a" if signature_ok else "#ef4444"
    sig_text = "✓ Yes" if signature_ok else "✗ Missing"

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
              <div class="stat-value mono">{record.get("vin_tail", "-")}</div>
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
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    docs = record.get("_docs", [])
    
    with st.expander("📁 Document Review – Photos, registration, insurance, signed form", expanded=False):
        tabs = st.tabs(["🚗 Vehicle", "📋 Registration", "🛡️ Insurance", "📄 Form"])
        
        vehicle_docs = [d for d in docs if d.get('doc_type') == 'vehicle']
        reg_docs = [d for d in docs if d.get('doc_type') == 'registration']
        ins_docs = [d for d in docs if d.get('doc_type') == 'insurance']
        sig_docs = [d for d in docs if d.get('doc_type') == 'signature']

        with tabs[0]:
            if vehicle_docs:
                cols = st.columns(3)
                for idx, doc in enumerate(vehicle_docs):
                    path = doc.get('file_path')
                    if path and file_storage.file_exists(path):
                        with cols[idx % 3]:
                            try:
                                img_bytes = file_storage.read_file(path)
                                st.image(img_bytes, width=200)
                                st.caption(os.path.basename(path))
                            except Exception as e:
                                st.error(f"Error loading: {e}")
            else:
                st.info("No vehicle photos uploaded.")

        with tabs[1]:
            if reg_docs:
                cols = st.columns(3)
                for idx, doc in enumerate(reg_docs):
                    path = doc.get('file_path')
                    if path and file_storage.file_exists(path):
                        with cols[idx % 3]:
                            try:
                                img_bytes = file_storage.read_file(path)
                                st.image(img_bytes, width=200)
                                st.caption(os.path.basename(path))
                            except Exception as e:
                                st.error(f"Error loading: {e}")
            else:
                st.info("No registration documents uploaded.")

        with tabs[2]:
            if ins_docs:
                cols = st.columns(3)
                for idx, doc in enumerate(ins_docs):
                    path = doc.get('file_path')
                    if path and file_storage.file_exists(path):
                        with cols[idx % 3]:
                            try:
                                img_bytes = file_storage.read_file(path)
                                st.image(img_bytes, width=200)
                                st.caption(os.path.basename(path))
                            except Exception as e:
                                st.error(f"Error loading: {e}")
            else:
                st.info("No insurance documents uploaded.")

        with tabs[3]:
            if sig_docs:
                path = sig_docs[0].get('file_path')
                if path and file_storage.file_exists(path):
                    try:
                        pdf_bytes = file_storage.read_file(path)
                        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                        
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.caption(f"📄 {os.path.basename(path)}")
                        with col2:
                            st.download_button(
                                label="⬇️ Download",
                                data=pdf_bytes,
                                file_name=os.path.basename(path),
                                mime="application/pdf",
                                key=f"dl_pdf_{enrollment_id}"
                            )
                        
                        st.markdown(
                            f'''
                            <div style="width: 100%; height: 400px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                                <iframe src="data:application/pdf;base64,{base64_pdf}" 
                                        width="100%" height="100%" style="border: none;">
                                </iframe>
                            </div>
                            ''',
                            unsafe_allow_html=True
                        )
                    except Exception as e:
                        st.error(f"Error loading PDF: {e}")
                else:
                    st.info("Signed form file not found.")
            else:
                st.info("No signed enrollment form available.")

    with st.expander("✅ Actions – Approve enrollment and send notifications", expanded=False):
        col1, col2, col3 = st.columns([2, 1.5, 1.5])
        
        with col1:
            st.markdown('<div class="approve-btn">', unsafe_allow_html=True)
            approve = st.button(
                "✅ Approve & Sync" if not is_validated else "✓ Already Approved",
                key=f"approve_{enrollment_id}",
                disabled=is_validated,
                use_container_width=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        with col2:
            has_pdf = any(d.get('doc_type') == 'signature' for d in docs)
            st.markdown('<div class="pdf-btn">', unsafe_allow_html=True)
            send_pdf = st.button(
                "📧 PDF to HR",
                key=f"pdf_{enrollment_id}",
                disabled=not has_pdf,
                use_container_width=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        with col3:
            st.markdown('<div class="notify-btn">', unsafe_allow_html=True)
            notify = st.button(
                "📧 Notify",
                key=f"notify_{enrollment_id}",
                use_container_width=True
            )
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(
            """
            <div class="warning-box">
              ⚠️ Complete all validation checks before approving
            </div>
            """,
            unsafe_allow_html=True,
        )

        if approve and not is_validated:
            raw_record = record.get('_raw', {})
            result = push_to_dashboard_single_request(raw_record, enrollment_id=enrollment_id)
            
            status_code = result.get('status_code', 0)
            if result.get('error'):
                st.error(f"Error: {result.get('error')}")
            elif status_code in (200, 201) or (200 <= status_code < 300 and status_code != 207):
                try:
                    database.approve_enrollment(enrollment_id)
                    database.mark_checklist_task_by_key(enrollment_id, 'approved_synced', True, 'System - Dashboard Sync')
                    clear_enrollment_cache()
                except Exception:
                    pass
                
                settings = _get_notification_settings()
                if settings.get('approval', {}).get('enabled'):
                    _send_approval_notification(raw_record, enrollment_id)
                
                st.success("Enrollment approved and synced to dashboard!")
                st.rerun()
            elif status_code == 207:
                try:
                    database.approve_enrollment(enrollment_id)
                    database.mark_checklist_task_by_key(enrollment_id, 'approved_synced', True, 'System - Dashboard Sync')
                    clear_enrollment_cache()
                except Exception:
                    pass
                st.warning("Approved with warnings (some photos may have failed)")
                st.rerun()
            else:
                st.error(f"Dashboard error: status {status_code}")

        if send_pdf:
            sig_doc = next((d for d in docs if d.get('doc_type') == 'signature'), None)
            if sig_doc:
                path = sig_doc.get('file_path')
                if path and file_storage.file_exists(path):
                    settings = _get_notification_settings()
                    hr_email = settings.get('hr_pdf', {}).get('recipients', 'tyler.morgan@transformco.com')
                    raw_record = record.get('_raw', {})
                    result = send_hr_policy_notification(raw_record, path, hr_email)
                    if result.get('success'):
                        database.mark_checklist_task_by_key(enrollment_id, 'policy_hshr', True, 'System - HR Email Sent')
                        st.success(f"Signed policy form sent to {hr_email}!")
                        st.rerun()
                    else:
                        st.error(f"Error: {result.get('error', 'Unknown error')}")
                else:
                    st.warning("PDF file not found")
            else:
                st.warning("No signed PDF available")

        if notify:
            raw_record = record.get('_raw', {})
            result = _send_approval_notification(raw_record, enrollment_id)
            if result is True:
                st.success("Notification sent!")
            elif result and result.get('error'):
                st.error(f"Error: {result.get('error')}")
            else:
                st.warning("Notifications not configured. Configure in notification settings.")


def main() -> None:
    """Main entry point for the new admin dashboard."""
    inject_admin_theme_css()

    records = get_admin_records()
    pending_count = sum(1 for r in records if r.get("status") == "in_review")

    render_header(pending_count)

    if not records:
        st.info("No enrollments found. Technicians will appear here after submitting enrollment forms.")
        return

    for rec in records:
        render_record_card(rec)


if __name__ == "__main__":
    main()
