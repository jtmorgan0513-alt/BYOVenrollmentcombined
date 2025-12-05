import os
import streamlit as st
from datetime import datetime
import database
from notifications import send_email_notification, send_pdf_to_hr, get_email_config_status, send_custom_notification
import shutil
import file_storage
import base64

try:
    import sqlite3
except Exception:
    sqlite3 = None


ENROLLMENT_FIELDS = [
    {'key': 'full_name', 'label': 'Full Name', 'group': 'Technician'},
    {'key': 'tech_id', 'label': 'Tech ID', 'group': 'Technician'},
    {'key': 'district', 'label': 'District', 'group': 'Technician'},
    {'key': 'state', 'label': 'State', 'group': 'Technician'},
    {'key': 'referred_by', 'label': 'Referred By', 'group': 'Technician'},
    {'key': 'year', 'label': 'Year', 'group': 'Vehicle'},
    {'key': 'make', 'label': 'Make', 'group': 'Vehicle'},
    {'key': 'model', 'label': 'Model', 'group': 'Vehicle'},
    {'key': 'vin', 'label': 'VIN', 'group': 'Vehicle'},
    {'key': 'industry', 'label': 'Industry', 'group': 'Vehicle'},
    {'key': 'insurance_exp', 'label': 'Insurance Exp', 'group': 'Compliance'},
    {'key': 'registration_exp', 'label': 'Registration Exp', 'group': 'Compliance'},
    {'key': 'submission_date', 'label': 'Submitted', 'group': 'Status'},
    {'key': 'approved', 'label': 'Approved', 'group': 'Status'},
]

DOCUMENT_TYPES = [
    {'key': 'signature', 'label': 'Signed PDF'},
    {'key': 'vehicle', 'label': 'Vehicle Photos'},
    {'key': 'registration', 'label': 'Registration'},
    {'key': 'insurance', 'label': 'Insurance Card'},
]

ALL_FIELD_KEYS = [f['key'] for f in ENROLLMENT_FIELDS]
ALL_DOC_KEYS = [d['key'] for d in DOCUMENT_TYPES]


def _get_all_enrollments():
    return database.get_all_enrollments()


def _get_notification_settings():
    """Get the notification settings from the database with all 4 email types."""
    try:
        settings = database.get_notification_settings()
        if settings:
            return _ensure_default_settings(settings)
    except Exception:
        pass
    return _get_default_settings()


def _get_default_settings():
    """Return default notification settings with all boxes checked."""
    return {
        'submission': {
            'enabled': True,
            'recipients': 'tyler.morgan@transformco.com, carl.oneill@transformco.com',
            'subject_template': 'New BYOV Enrollment: {full_name} (Tech ID: {tech_id})',
        },
        'approval': {
            'enabled': True,
            'recipients': '',
            'subject_template': 'BYOV Enrollment Approved: {full_name} (Tech ID: {tech_id})',
            'selected_fields': ALL_FIELD_KEYS.copy(),
            'selected_docs': ALL_DOC_KEYS.copy(),
        },
        'hr_pdf': {
            'enabled': True,
            'recipients': 'tyler.morgan@transformco.com',
            'subject_template': 'BYOV Signed Policy Form - {full_name} (Tech ID: {tech_id})',
        },
        'custom': {
            'enabled': False,
            'recipients': '',
            'subject_template': 'BYOV Enrollment: {full_name} (Tech ID: {tech_id})',
            'selected_fields': ALL_FIELD_KEYS.copy(),
            'selected_docs': ALL_DOC_KEYS.copy(),
        },
    }


def _ensure_default_settings(settings):
    """Ensure all required keys exist with defaults."""
    defaults = _get_default_settings()
    
    for key in defaults:
        if key not in settings:
            settings[key] = defaults[key]
        else:
            for subkey in defaults[key]:
                if subkey not in settings[key]:
                    settings[key][subkey] = defaults[key][subkey]
    
    return settings


def _save_notification_settings(settings):
    """Save notification settings to database."""
    try:
        database.save_notification_settings(settings)
        return True
    except Exception as e:
        st.error(f"Error saving settings: {e}")
        return False


def _format_date(date_str):
    """Format ISO date string to MM/DD/YYYY."""
    if not date_str:
        return 'N/A'
    try:
        dt = datetime.fromisoformat(str(date_str))
        return dt.strftime("%m/%d/%Y")
    except Exception:
        return str(date_str) if date_str else 'N/A'


def _format_field_value(row, key):
    """Format a field value for display."""
    value = row.get(key)
    
    if key in ('insurance_exp', 'registration_exp', 'submission_date'):
        return _format_date(value)
    elif key == 'approved':
        return '✅ Yes' if value == 1 else '⏳ No'
    elif key == 'industry':
        if isinstance(value, list):
            return ', '.join(value) if value else 'N/A'
        return str(value) if value else 'N/A'
    elif key == 'referred_by':
        return value or row.get('referredBy') or 'N/A'
    else:
        return str(value) if value else 'N/A'


def _get_checklist_progress(enrollment_id):
    """Get checklist completion progress, auto-creating if missing."""
    try:
        checklist = database.get_checklist_for_enrollment(enrollment_id)
        if not checklist:
            database.create_checklist_for_enrollment(enrollment_id)
            checklist = database.get_checklist_for_enrollment(enrollment_id)
        if not checklist:
            return 0, 6
        completed = sum(1 for t in checklist if t.get('completed'))
        return completed, len(checklist)
    except Exception:
        return 0, 6


def _render_selection_panel(enrollments):
    """Render a lightweight selection panel for enrollments."""
    st.markdown("""
    <style>
    .enrollment-card {
        padding: 12px 16px;
        margin: 4px 0;
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.2s ease;
        border: 1px solid #e0e0e0;
        background: white;
    }
    .enrollment-card:hover {
        background: #f0f7ff;
        border-color: #0d6efd;
    }
    .enrollment-card.selected {
        background: #e3f2fd;
        border-color: #0d6efd;
        border-width: 2px;
    }
    .tech-name {
        font-weight: 600;
        font-size: 15px;
        color: #333;
        margin: 0;
    }
    .tech-details {
        font-size: 13px;
        color: #666;
        margin: 4px 0 0 0;
    }
    .status-badges {
        display: flex;
        gap: 8px;
        margin-top: 6px;
    }
    .badge {
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
    }
    .badge-approved { background: #d4edda; color: #155724; }
    .badge-pending { background: #fff3cd; color: #856404; }
    .badge-checklist { background: #e2e3e5; color: #383d41; }
    .badge-complete { background: #cce5ff; color: #004085; }
    </style>
    """, unsafe_allow_html=True)
    
    selected_id = st.session_state.get('selected_enrollment_id')
    
    container = st.container(height=400)
    
    with container:
        for enrollment in enrollments:
            eid = enrollment.get('id')
            tech_name = enrollment.get('full_name', 'Unknown')
            district = enrollment.get('district', 'N/A')
            is_approved = enrollment.get('approved', 0) == 1
            completed, total = _get_checklist_progress(eid)
            
            is_selected = eid == selected_id
            
            col1, col2, col3, col4 = st.columns([3, 2, 1.5, 1.5])
            
            with col1:
                if st.button(
                    f"**{tech_name}**",
                    key=f"sel_{eid}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary"
                ):
                    st.session_state.selected_enrollment_id = eid
                    st.rerun()
            
            with col2:
                st.caption(f"📍 {district}")
            
            with col3:
                if is_approved:
                    st.success("Approved", icon="✅")
                else:
                    st.warning("Pending", icon="⏳")
            
            with col4:
                if completed == total:
                    st.info(f"{completed}/{total}", icon="✓")
                else:
                    st.caption(f"📋 {completed}/{total}")
    
    return selected_id


def _render_overview_tab(row, enrollment_id):
    """Render the Overview tab with record details and approve button."""
    is_approved = row.get('approved', 0) == 1
    
    vehicle_info = f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}".strip()
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #0d6efd 0%, #0b5ed7 100%);
        padding: 16px 20px;
        border-radius: 10px;
        margin-bottom: 16px;
    ">
        <h3 style="color: white; margin: 0 0 6px 0; font-size: 20px;">
            {row.get('full_name', 'N/A')}
        </h3>
        <p style="color: rgba(255,255,255,0.9); margin: 0; font-size: 13px;">
            Tech ID: <strong>{row.get('tech_id', 'N/A')}</strong> | 
            District: <strong>{row.get('district', 'N/A')}</strong> | 
            State: <strong>{row.get('state', 'N/A')}</strong> |
            Vehicle: <strong>{vehicle_info}</strong>
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Technician**")
        st.write(f"Name: {row.get('full_name', 'N/A')}")
        st.write(f"Tech ID: {row.get('tech_id', 'N/A')}")
        st.write(f"District: {row.get('district', 'N/A')}")
        st.write(f"State: {row.get('state', 'N/A')}")
        referred_by = row.get('referred_by') or row.get('referredBy') or 'N/A'
        st.write(f"Referred By: {referred_by}")
    
    with col2:
        st.markdown("**Vehicle**")
        st.write(f"Year: {row.get('year', 'N/A')}")
        st.write(f"Make: {row.get('make', 'N/A')}")
        st.write(f"Model: {row.get('model', 'N/A')}")
        st.write(f"VIN: {row.get('vin', 'N/A')}")
        industry = row.get('industry') or row.get('industries', [])
        if isinstance(industry, list):
            industry = ', '.join(industry) if industry else 'N/A'
        st.write(f"Industry: {industry}")
    
    with col3:
        st.markdown("**Compliance**")
        st.write(f"Insurance Exp: {_format_date(row.get('insurance_exp'))}")
        st.write(f"Registration Exp: {_format_date(row.get('registration_exp'))}")
        st.write(f"Submitted: {_format_date(row.get('submission_date'))}")
        if is_approved:
            st.success("Status: Approved")
        else:
            st.warning("Status: Pending")
        
        checklist = database.get_checklist_for_enrollment(enrollment_id)
        if checklist:
            completed_count = sum(1 for task in checklist if task.get('completed'))
            total_count = len(checklist)
            if completed_count == total_count:
                st.success(f"Checklist: {completed_count}/{total_count} ✓")
            elif completed_count > 0:
                st.info(f"Checklist: {completed_count}/{total_count}")
            else:
                st.caption(f"Checklist: {completed_count}/{total_count}")
    
    st.markdown("---")
    
    action_cols = st.columns([2, 2, 2, 1])
    
    with action_cols[0]:
        if is_approved:
            st.markdown(
                '<div style="background: #10b981; color: white; padding: 10px 12px; '
                'border-radius: 8px; text-align: center; font-weight: 600;">Already Approved</div>',
                unsafe_allow_html=True
            )
        else:
            if st.button("✅ Approve & Sync to Dashboard", key=f"approve_{enrollment_id}", type="primary", use_container_width=True):
                _handle_approval(row, enrollment_id)
    
    with action_cols[1]:
        docs = database.get_documents_for_enrollment(enrollment_id)
        signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]
        
        if signature_pdf and file_storage.file_exists(signature_pdf[0]):
            if st.button("📧 Send PDF to HR", key=f"send_hr_{enrollment_id}", use_container_width=True):
                from notifications import send_hr_policy_notification
                settings = _get_notification_settings()
                hr_email = settings.get('hr_pdf', {}).get('recipients', 'tyler.morgan@transformco.com')
                result = send_hr_policy_notification(row, signature_pdf[0], hr_email)
                if result.get('success'):
                    database.mark_checklist_task_by_key(enrollment_id, 'policy_hshr', True, 'System - HR Email Sent')
                    st.success(f"Signed policy form sent to {hr_email}!")
                    st.rerun()
                else:
                    st.error(f"Error: {result.get('error', 'Unknown error')}")
        else:
            st.button("No PDF", disabled=True, use_container_width=True)
    
    with action_cols[2]:
        if st.button("📧 Send Notification", key=f"send_notif_{enrollment_id}", use_container_width=True):
            result = _send_approval_notification(row, enrollment_id)
            if result is True:
                st.success("Email sent!")
            elif result and result.get('error'):
                st.error(f"Error: {result.get('error')}")
            else:
                st.warning("Notifications not configured. Go to Notification Settings tab.")
    
    with action_cols[3]:
        st.session_state.setdefault("delete_confirm", {})
        is_confirming = st.session_state.delete_confirm.get(enrollment_id, False)
        
        if st.button("🗑️" if not is_confirming else "⚠️ Confirm", key=f"del_{enrollment_id}", use_container_width=True):
            if is_confirming:
                _handle_delete(row, enrollment_id)
            else:
                st.session_state.delete_confirm[enrollment_id] = True
                st.rerun()


def _handle_approval(row, enrollment_id):
    """Handle the approval workflow."""
    from byov_app import post_to_dashboard_single_request, clear_enrollment_cache
    
    record = dict(row)
    single_result = post_to_dashboard_single_request(record, enrollment_id=enrollment_id)
    
    if single_result.get('error'):
        st.error(f"Error: {single_result.get('error')}")
    else:
        status_code = single_result.get('status_code', 0)
        
        if status_code in (201,) or (200 <= status_code < 300 and status_code != 207):
            try:
                database.approve_enrollment(enrollment_id)
                database.mark_checklist_task_by_key(enrollment_id, 'approved_synced', True, 'System - Dashboard Sync')
                clear_enrollment_cache()
            except Exception:
                pass
            
            settings = _get_notification_settings()
            if settings.get('approval', {}).get('enabled'):
                _send_approval_notification(row, enrollment_id)
            
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


def _handle_delete(row, enrollment_id):
    """Handle enrollment deletion."""
    from byov_app import clear_enrollment_cache
    try:
        tech_id = row.get('tech_id', 'unknown')
        docs = database.get_documents_for_enrollment(enrollment_id)
        
        for doc in docs:
            file_path = doc.get('file_path')
            if file_path:
                file_storage.delete_file(file_path)
        
        if not file_storage.USE_OBJECT_STORAGE:
            if os.path.exists('uploads'):
                for folder in os.listdir('uploads'):
                    if folder.startswith(f"{tech_id}_"):
                        folder_path = os.path.join('uploads', folder)
                        if os.path.isdir(folder_path):
                            shutil.rmtree(folder_path, ignore_errors=True)
            
            if os.path.exists('pdfs'):
                for pdf_file in os.listdir('pdfs'):
                    if pdf_file.startswith(f"{tech_id}_") and pdf_file.endswith('.pdf'):
                        os.remove(os.path.join('pdfs', pdf_file))
        
        database.delete_enrollment(enrollment_id)
        clear_enrollment_cache()
        st.session_state.delete_confirm.pop(enrollment_id, None)
        st.session_state.selected_enrollment_id = None
        st.success("Deleted")
        st.rerun()
    except Exception as e:
        st.error(f"Error: {e}")


def _render_documents_tab(row, enrollment_id):
    """Render the Documents tab with inline PDF preview and photos."""
    docs = database.get_documents_for_enrollment(enrollment_id)
    
    vehicle = [d["file_path"] for d in docs if d["doc_type"] == "vehicle"]
    registration = [d["file_path"] for d in docs if d["doc_type"] == "registration"]
    insurance = [d["file_path"] for d in docs if d["doc_type"] == "insurance"]
    signature_pdf = [d["file_path"] for d in docs if d["doc_type"] == "signature"]
    
    st.markdown("#### Signed PDF")
    
    if signature_pdf and file_storage.file_exists(signature_pdf[0]):
        pdf_bytes = file_storage.read_file(signature_pdf[0])
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        
        col1, col2 = st.columns([4, 1])
        with col1:
            st.caption(f"📄 {os.path.basename(signature_pdf[0])}")
        with col2:
            st.download_button(
                label="⬇️ Download",
                data=pdf_bytes,
                file_name=os.path.basename(signature_pdf[0]),
                mime="application/pdf",
                key=f"dl_pdf_docs_{enrollment_id}"
            )
        
        pdf_viewer_html = f'''
        <div style="width: 100%; height: 500px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; margin-bottom: 16px;">
            <iframe src="data:application/pdf;base64,{base64_pdf}" 
                    width="100%" height="100%" style="border: none;">
            </iframe>
        </div>
        '''
        st.markdown(pdf_viewer_html, unsafe_allow_html=True)
    else:
        st.info("No signed PDF found.")
    
    st.markdown("#### Photos")
    
    photo_tabs = st.tabs(["🚗 Vehicle", "📋 Registration", "🛡️ Insurance"])
    
    photo_groups = [
        (photo_tabs[0], vehicle, "vehicle"),
        (photo_tabs[1], registration, "registration"),
        (photo_tabs[2], insurance, "insurance"),
    ]
    
    for tab, paths, label in photo_groups:
        with tab:
            if paths:
                cols = st.columns(3)
                for idx, p in enumerate(paths):
                    if file_storage.file_exists(p):
                        with cols[idx % 3]:
                            try:
                                img_bytes = file_storage.read_file(p)
                                st.image(img_bytes, width=200)
                                filename = os.path.basename(p)
                                st.caption(filename)
                                with st.expander("🔍 View Full Size"):
                                    st.image(img_bytes, use_container_width=True)
                                    st.download_button(
                                        label="⬇️ Download",
                                        data=img_bytes,
                                        file_name=filename,
                                        mime="image/jpeg",
                                        key=f"dl_{label}_{idx}_{enrollment_id}"
                                    )
                            except Exception as e:
                                st.error(f"Error: {e}")
            else:
                st.info(f"No {label} photos.")


def _send_approval_notification(record, enrollment_id):
    """Send approval notification based on saved settings using selected fields and documents."""
    settings = _get_notification_settings()
    approval_settings = settings.get('approval', {})
    
    if not approval_settings.get('enabled'):
        return None
    
    recipients = approval_settings.get('recipients', '')
    if not recipients:
        return None
    
    subject_template = approval_settings.get('subject_template', 'BYOV Enrollment Approved: {full_name}')
    subject = subject_template.format(
        full_name=record.get('full_name', 'Unknown'),
        tech_id=record.get('tech_id', 'N/A'),
        district=record.get('district', 'N/A'),
        state=record.get('state', 'N/A'),
        year=record.get('year', ''),
        make=record.get('make', ''),
        model=record.get('model', '')
    )
    
    selected_fields = approval_settings.get('selected_fields', ALL_FIELD_KEYS)
    selected_docs = approval_settings.get('selected_docs', ALL_DOC_KEYS)
    
    try:
        result = send_custom_notification(
            record=record,
            recipients=recipients,
            subject=subject,
            selected_fields=selected_fields,
            selected_docs=selected_docs,
            field_metadata=ENROLLMENT_FIELDS,
            enrollment_id=enrollment_id
        )
        return result
    except Exception as e:
        return {'error': str(e)}


def _render_checklist_tab(row, enrollment_id):
    """Render the Checklist tab with task checkboxes."""
    checklist = database.get_checklist_for_enrollment(enrollment_id)
    
    if not checklist:
        database.create_checklist_for_enrollment(enrollment_id)
        checklist = database.get_checklist_for_enrollment(enrollment_id)
    
    tech_name = row.get('full_name', 'Technician')
    
    st.markdown("#### Enrollment Checklist")
    st.caption(f"Track completion of required tasks for {tech_name}")
    
    completed_count = sum(1 for task in checklist if task.get('completed'))
    total_count = len(checklist)
    progress = completed_count / total_count if total_count > 0 else 0
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.progress(progress, text=f"{completed_count} of {total_count} tasks completed")
    with col2:
        if completed_count == total_count:
            st.success("All Done!")
    
    st.markdown("---")
    
    for task in checklist:
        task_id = task['id']
        task_name = task['task_name']
        is_completed = task.get('completed', False)
        
        col1, col2 = st.columns([0.5, 5])
        
        with col1:
            new_status = st.checkbox(
                "",
                value=is_completed,
                key=f"check_{task_id}_{enrollment_id}",
                label_visibility="collapsed"
            )
            if new_status != is_completed:
                database.update_checklist_task(task_id, new_status)
                st.rerun()
        
        with col2:
            if is_completed:
                st.markdown(f"~~{task_name}~~")
                if task.get('completed_at'):
                    st.caption(f"Completed {task['completed_at'][:10]}")
            else:
                st.markdown(f"**{task_name}**")


def _render_action_panel(enrollment_id, enrollments):
    """Render the tabbed action panel for a selected enrollment."""
    row = None
    for e in enrollments:
        if e.get('id') == enrollment_id:
            row = e
            break
    
    if not row:
        st.warning("Selected enrollment not found.")
        st.session_state.selected_enrollment_id = None
        return
    
    st.markdown("---")
    
    tech_name = row.get('full_name', 'Selected Record')
    st.markdown(f"### {tech_name}")
    
    tabs = st.tabs(["📋 Overview", "✅ Checklist", "📄 Documents"])
    
    with tabs[0]:
        _render_overview_tab(row, enrollment_id)
    
    with tabs[1]:
        _render_checklist_tab(row, enrollment_id)
    
    with tabs[2]:
        _render_documents_tab(row, enrollment_id)


def _notification_config_page():
    """Global notification configuration page."""
    st.subheader("Email Configuration")
    
    email_status = get_email_config_status()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Current Status")
        if email_status['sendgrid_configured']:
            st.success(f"SendGrid: Configured ({email_status['sendgrid_from']})")
        elif email_status.get('sendgrid_api_key_set'):
            st.warning("SendGrid API key set, but sender email not configured. Add SENDGRID_FROM_EMAIL to Secrets.")
        else:
            st.error("SendGrid: Not configured")
            st.caption("Email notifications will not work until SendGrid is configured.")
    
    with col2:
        st.markdown("#### Setup Instructions")
        st.markdown("""
        **SendGrid Setup:**
        1. Create a SendGrid account at sendgrid.com
        2. Generate an API key with email sending permissions
        3. Add `SENDGRID_API_KEY` to your Secrets
        4. Add `SENDGRID_FROM_EMAIL` with a verified sender email
        """)


def _render_notification_settings():
    """Render the 4-section notification settings panel."""
    st.subheader("Notification Settings")
    st.caption("Configure email notifications for different events. All settings are saved automatically.")
    
    settings = _get_notification_settings()
    updated = False
    
    email_status = get_email_config_status()
    if not email_status['sendgrid_configured']:
        st.warning("SendGrid is not configured. Email notifications will not be sent until configured.")
    
    st.markdown("---")
    
    st.markdown("### 1. New Enrollment Submissions")
    st.caption("Sent automatically when a technician submits a new enrollment. Always includes all photos and signed PDF.")
    
    sub_col1, sub_col2 = st.columns([1, 3])
    with sub_col1:
        sub_enabled = st.checkbox(
            "Enable",
            value=settings['submission'].get('enabled', True),
            key="sub_enabled"
        )
    with sub_col2:
        sub_recipients = st.text_input(
            "Recipients (comma-separated)",
            value=settings['submission'].get('recipients', 'tyler.morgan@transformco.com, carl.oneill@transformco.com'),
            key="sub_recipients",
            placeholder="email1@company.com, email2@company.com"
        )
    
    sub_subject = st.text_input(
        "Subject Template",
        value=settings['submission'].get('subject_template', 'New BYOV Enrollment: {full_name} (Tech ID: {tech_id})'),
        key="sub_subject",
        help="Placeholders: {full_name}, {tech_id}, {district}, {state}, {year}, {make}, {model}"
    )
    
    if (sub_enabled != settings['submission'].get('enabled') or
        sub_recipients != settings['submission'].get('recipients') or
        sub_subject != settings['submission'].get('subject_template')):
        settings['submission'] = {
            'enabled': sub_enabled,
            'recipients': sub_recipients,
            'subject_template': sub_subject,
        }
        updated = True
    
    st.markdown("---")
    
    st.markdown("### 2. Approval Notifications")
    st.caption("Sent when an admin clicks 'Approve & Sync to Dashboard'.")
    
    app_col1, app_col2 = st.columns([1, 3])
    with app_col1:
        app_enabled = st.checkbox(
            "Enable",
            value=settings['approval'].get('enabled', True),
            key="app_enabled"
        )
    with app_col2:
        app_recipients = st.text_input(
            "Recipients (comma-separated)",
            value=settings['approval'].get('recipients', ''),
            key="app_recipients",
            placeholder="fleet@company.com, manager@company.com"
        )
    
    app_subject = st.text_input(
        "Subject Template",
        value=settings['approval'].get('subject_template', 'BYOV Enrollment Approved: {full_name} (Tech ID: {tech_id})'),
        key="app_subject",
        help="Placeholders: {full_name}, {tech_id}, {district}, {state}, {year}, {make}, {model}"
    )
    
    st.markdown("**Fields to Include:**")
    app_fields = settings['approval'].get('selected_fields', ALL_FIELD_KEYS)
    new_app_fields = []
    
    groups = {}
    for field in ENROLLMENT_FIELDS:
        group = field['group']
        if group not in groups:
            groups[group] = []
        groups[group].append(field)
    
    group_cols = st.columns(len(groups))
    for idx, (group_name, fields) in enumerate(groups.items()):
        with group_cols[idx]:
            st.markdown(f"**{group_name}**")
            for field in fields:
                is_selected = field['key'] in app_fields
                if st.checkbox(
                    field['label'], 
                    value=is_selected, 
                    key=f"app_field_{field['key']}"
                ):
                    new_app_fields.append(field['key'])
    
    st.markdown("**Documents to Attach:**")
    app_docs = settings['approval'].get('selected_docs', ALL_DOC_KEYS)
    new_app_docs = []
    
    doc_cols = st.columns(len(DOCUMENT_TYPES))
    for idx, doc_type in enumerate(DOCUMENT_TYPES):
        with doc_cols[idx]:
            is_selected = doc_type['key'] in app_docs
            if st.checkbox(
                doc_type['label'], 
                value=is_selected, 
                key=f"app_doc_{doc_type['key']}"
            ):
                new_app_docs.append(doc_type['key'])
    
    if (app_enabled != settings['approval'].get('enabled') or
        app_recipients != settings['approval'].get('recipients') or
        app_subject != settings['approval'].get('subject_template') or
        set(new_app_fields) != set(app_fields) or
        set(new_app_docs) != set(app_docs)):
        settings['approval'] = {
            'enabled': app_enabled,
            'recipients': app_recipients,
            'subject_template': app_subject,
            'selected_fields': new_app_fields,
            'selected_docs': new_app_docs,
        }
        updated = True
    
    st.markdown("---")
    
    st.markdown("### 3. Send PDF to HR")
    st.caption("Sent when the 'Send PDF to HR' button is clicked. Attaches only the signed policy PDF.")
    
    hr_col1, hr_col2 = st.columns([1, 3])
    with hr_col1:
        hr_enabled = st.checkbox(
            "Enable",
            value=settings['hr_pdf'].get('enabled', True),
            key="hr_enabled"
        )
    with hr_col2:
        hr_recipients = st.text_input(
            "HR Email Recipient",
            value=settings['hr_pdf'].get('recipients', 'tyler.morgan@transformco.com'),
            key="hr_recipients",
            placeholder="hr@company.com"
        )
    
    hr_subject = st.text_input(
        "Subject Template",
        value=settings['hr_pdf'].get('subject_template', 'BYOV Signed Policy Form - {full_name} (Tech ID: {tech_id})'),
        key="hr_subject",
        help="Placeholders: {full_name}, {tech_id}, {district}, {state}"
    )
    
    if (hr_enabled != settings['hr_pdf'].get('enabled') or
        hr_recipients != settings['hr_pdf'].get('recipients') or
        hr_subject != settings['hr_pdf'].get('subject_template')):
        settings['hr_pdf'] = {
            'enabled': hr_enabled,
            'recipients': hr_recipients,
            'subject_template': hr_subject,
        }
        updated = True
    
    st.markdown("---")
    
    st.markdown("### 4. Custom Email (Manual)")
    st.caption("For one-off emails outside the normal automation workflow. Use the 'Send Notification' button on any enrollment.")
    
    cust_col1, cust_col2 = st.columns([1, 3])
    with cust_col1:
        cust_enabled = st.checkbox(
            "Enable",
            value=settings['custom'].get('enabled', False),
            key="cust_enabled"
        )
    with cust_col2:
        cust_recipients = st.text_input(
            "Default Recipients (comma-separated)",
            value=settings['custom'].get('recipients', ''),
            key="cust_recipients",
            placeholder="custom@company.com"
        )
    
    cust_subject = st.text_input(
        "Subject Template",
        value=settings['custom'].get('subject_template', 'BYOV Enrollment: {full_name} (Tech ID: {tech_id})'),
        key="cust_subject",
        help="Placeholders: {full_name}, {tech_id}, {district}, {state}, {year}, {make}, {model}"
    )
    
    st.markdown("**Fields to Include:**")
    cust_fields = settings['custom'].get('selected_fields', ALL_FIELD_KEYS)
    new_cust_fields = []
    
    cust_group_cols = st.columns(len(groups))
    for idx, (group_name, fields) in enumerate(groups.items()):
        with cust_group_cols[idx]:
            st.markdown(f"**{group_name}**")
            for field in fields:
                is_selected = field['key'] in cust_fields
                if st.checkbox(
                    field['label'], 
                    value=is_selected, 
                    key=f"cust_field_{field['key']}"
                ):
                    new_cust_fields.append(field['key'])
    
    st.markdown("**Documents to Attach:**")
    cust_docs = settings['custom'].get('selected_docs', ALL_DOC_KEYS)
    new_cust_docs = []
    
    cust_doc_cols = st.columns(len(DOCUMENT_TYPES))
    for idx, doc_type in enumerate(DOCUMENT_TYPES):
        with cust_doc_cols[idx]:
            is_selected = doc_type['key'] in cust_docs
            if st.checkbox(
                doc_type['label'], 
                value=is_selected, 
                key=f"cust_doc_{doc_type['key']}"
            ):
                new_cust_docs.append(doc_type['key'])
    
    if (cust_enabled != settings['custom'].get('enabled') or
        cust_recipients != settings['custom'].get('recipients') or
        cust_subject != settings['custom'].get('subject_template') or
        set(new_cust_fields) != set(cust_fields) or
        set(new_cust_docs) != set(cust_docs)):
        settings['custom'] = {
            'enabled': cust_enabled,
            'recipients': cust_recipients,
            'subject_template': cust_subject,
            'selected_fields': new_cust_fields,
            'selected_docs': new_cust_docs,
        }
        updated = True
    
    st.markdown("---")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 Save All Settings", type="primary"):
            if _save_notification_settings(settings):
                st.success("All notification settings saved!")
                st.rerun()
    
    if updated:
        st.caption("Changes detected. Click 'Save All Settings' to apply.")


def _overview_page(enrollments):
    """System overview page."""
    st.subheader("System Overview")
    
    total = len(enrollments)
    approved = sum(1 for e in enrollments if e.get('approved', 0) == 1)
    pending = total - approved
    
    if database.USE_POSTGRES if hasattr(database, 'USE_POSTGRES') else False:
        db_mode = "PostgreSQL"
    elif database.USE_SQLITE:
        db_mode = "SQLite"
    else:
        db_mode = "JSON"
    
    file_mode = file_storage.get_storage_mode().split(" ")[0]
    email_status = get_email_config_status()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Enrollments", total)
    c2.metric("Approved", approved)
    c3.metric("Pending", pending)
    c4.metric("Database", db_mode)
    
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("File Storage", file_mode)
    c6.metric("Email", email_status['primary_method'])
    
    if db_mode == "PostgreSQL":
        st.success("Database is persistent across deployments.")
    else:
        st.warning("Using local storage. Data may not persist across deployments.")


def page_admin_control_center():
    """Main admin control center page."""
    st.title("BYOV Admin Control Center")
    
    st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 8px 16px; font-size: 14px; }
    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)
    
    enrollments = _get_all_enrollments()
    
    st.session_state.setdefault("selected_enrollment_id", None)
    
    main_tabs = st.tabs(["📋 Enrollments", "🔔 Notification Settings", "⚙️ Email Config"])
    
    with main_tabs[0]:
        if not enrollments:
            st.info("No enrollments yet. Enrollments will appear here after technicians submit the form.")
        else:
            q = st.text_input("🔍 Search", placeholder="Search by name, tech ID, or VIN...")
            
            if q:
                filtered = [r for r in enrollments if q.lower() in " ".join([str(r.get(k, "")).lower() for k in ("full_name", "tech_id", "vin")])]
            else:
                filtered = enrollments
            
            st.caption(f"{len(filtered)} enrollment{'s' if len(filtered) != 1 else ''}")
            
            _render_selection_panel(filtered)
            
            if st.session_state.selected_enrollment_id:
                _render_action_panel(st.session_state.selected_enrollment_id, enrollments)
    
    with main_tabs[1]:
        _render_notification_settings()
    
    with main_tabs[2]:
        _notification_config_page()


if __name__ == '__main__':
    page_admin_control_center()
