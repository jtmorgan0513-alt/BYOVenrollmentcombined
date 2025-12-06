import os
import mimetypes
import json
import requests
import base64
from datetime import datetime

import streamlit as st
import file_storage

LOGO_PATH = os.path.join(os.path.dirname(__file__), "static", "sears_logo.png")

def get_logo_base64():
    """Get the Sears logo as a base64 data URI for embedding in emails."""
    try:
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, 'rb') as f:
                logo_data = f.read()
            return base64.b64encode(logo_data).decode()
    except Exception:
        pass
    return None


def get_sears_html_template(record, include_logo=True, use_cid_logo=False):
    """Generate a branded HTML email template with Sears styling.
    
    Args:
        record: Enrollment record dictionary
        include_logo: Whether to include the logo at all
        use_cid_logo: If True, use cid:sears_logo reference (for CID attachment)
    """
    
    industries_list = record.get('industry', record.get('industries', []))
    industries_str = ", ".join(industries_list) if industries_list else "None"
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y at %I:%M %p")
        except Exception:
            pass
    
    logo_section = ""
    if include_logo:
        if use_cid_logo:
            logo_section = """
        <div style="text-align: center; padding: 20px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
            <img src="cid:sears_logo" alt="Sears Home Services" style="max-width: 250px; height: auto; display: block; margin: 0 auto;">
        </div>
            """
        else:
            logo_b64 = get_logo_base64()
            if logo_b64:
                logo_section = f"""
        <div style="text-align: center; padding: 20px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
            <img src="data:image/png;base64,{logo_b64}" alt="Sears Home Services" style="max-width: 250px; height: auto; display: block; margin: 0 auto;">
        </div>
            """
            else:
                logo_section = """
        <div style="text-align: center; padding: 20px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
            <h2 style="color: #0066CC; margin: 0;">Sears Home Services</h2>
        </div>
            """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BYOV Enrollment Notification</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f7fa;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            {logo_section}
            
            <!-- Header Banner -->
            <div style="background-color: #e8f4fc; padding: 20px; text-align: center; border-bottom: 3px solid #0d6efd;">
                <h2 style="color: #0d6efd; margin: 0; font-size: 22px;">
                    New BYOV Enrollment Submitted
                </h2>
                <p style="color: #666; margin: 10px 0 0 0; font-size: 14px;">
                    Submitted on {submission_date}
                </p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                
                <!-- Technician Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #0d6efd; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #0d6efd; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        👤 Technician Information
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Name:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Tech ID:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('tech_id', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">District:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('district', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">State:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('state', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Referred By:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('referred_by', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Employment Status:</td>
                            <td style="padding: 8px 0; color: #333;">{('New Hire (less than 30 days)' if record.get('is_new_hire') else 'Existing Tech')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Truck Number:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('truck_number', 'N/A') or 'N/A'}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Industries:</td>
                            <td style="padding: 8px 0; color: #333;">{industries_str}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Vehicle Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #28a745; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #28a745; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        🚗 Vehicle Information
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Year:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('year', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Make:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('make', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Model:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('model', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">VIN:</td>
                            <td style="padding: 8px 0; color: #333; font-family: monospace;">{record.get('vin', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Documentation Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #ffc107; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #856404; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        📋 Documentation
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Insurance Exp:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('insurance_exp', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Registration Exp:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('registration_exp', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Template Used:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('template_used', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                    <p style="color: #666; margin: 0; font-size: 12px;">
                        This is an automated notification from the BYOV Enrollment System.
                        <br>Please review the enrollment details and take appropriate action.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def get_plain_text_body(record):
    """Generate a plain text version of the email for clients that don't support HTML."""
    hire_status = 'New Hire (less than 30 days)' if record.get('is_new_hire') else 'Existing Tech'
    text = f"""BYOV Enrollment Submitted

Technician Information:
- Name: {record.get('full_name', 'N/A')}
- Tech ID: {record.get('tech_id', 'N/A')}
- District: {record.get('district', 'N/A')}
- State: {record.get('state', 'N/A')}
- Referred By: {record.get('referred_by', 'N/A')}
- Employment Status: {hire_status}
- Truck Number: {record.get('truck_number', 'N/A') or 'N/A'}

Vehicle Information:
- Year: {record.get('year', 'N/A')}
- Make: {record.get('make', 'N/A')}
- Model: {record.get('model', 'N/A')}
- VIN: {record.get('vin', 'N/A')}

Documentation:
- Insurance Expires: {record.get('insurance_exp', 'N/A')}
- Registration Expires: {record.get('registration_exp', 'N/A')}

This is an automated message from the BYOV Enrollment System.
"""
    return text


def send_email_notification(record, recipients=None, subject=None, attach_pdf_only=False):
    """Send an email notification about an enrollment record via SendGrid.

    Args:
        record: Enrollment record dictionary
        recipients: Email recipient(s) - string or list
        subject: Custom subject line
        attach_pdf_only: If True, only attach the signed PDF (for HR emails)
    
    Returns True on success, False otherwise.
    """
    email_config = st.secrets.get("email", {})
    default_recipient = email_config.get("recipient")

    if recipients:
        if isinstance(recipients, str):
            recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
        elif isinstance(recipients, (list, tuple)):
            recipient_list = [r for r in recipients if r]
        else:
            recipient_list = [str(recipients)]
    else:
        recipient_list = [default_recipient] if default_recipient else []

    if not recipient_list:
        st.warning("No recipients specified for email notification.")
        return False

    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    
    if not sg_key:
        st.error("SendGrid is not configured. Please add SENDGRID_API_KEY to your secrets.")
        return False
    
    if not sg_from:
        st.error("SendGrid sender email not configured. Please add SENDGRID_FROM_EMAIL to your secrets.")
        return False

    subject = subject or f"New BYOV Enrollment: {record.get('full_name','Unknown')} (Tech {record.get('tech_id','N/A')})"
    html_body = get_sears_html_template(record, use_cid_logo=True)
    plain_body = get_plain_text_body(record)

    files = []
    if attach_pdf_only:
        pdf_path = record.get('signature_pdf_path')
        if pdf_path and file_storage.file_exists(pdf_path):
            files.append(pdf_path)
    else:
        file_keys = [
            'signature_pdf_path',
            'vehicle_photos_paths',
            'insurance_docs_paths',
            'registration_docs_paths'
        ]
        for k in file_keys:
            v = record.get(k)
            if not v:
                continue
            if isinstance(v, list):
                for p in v:
                    if p and file_storage.file_exists(p):
                        files.append(p)
            else:
                if isinstance(v, str) and file_storage.file_exists(v):
                    files.append(v)

    try:
        sg_payload = {
            "personalizations": [{"to": [{"email": r} for r in recipient_list]}],
            "from": {"email": sg_from},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": plain_body},
                {"type": "text/html", "value": html_body}
            ]
        }
        
        attachments = []
        
        if os.path.exists(LOGO_PATH):
            try:
                with open(LOGO_PATH, 'rb') as f:
                    logo_data = f.read()
                attachments.append({
                    "content": base64.b64encode(logo_data).decode(),
                    "type": "image/png",
                    "filename": "sears_logo.png",
                    "disposition": "inline",
                    "content_id": "sears_logo"
                })
            except Exception:
                pass
        
        for file_path in files:
            try:
                content = file_storage.read_file(file_path)
                if content:
                    filename = os.path.basename(file_path)
                    b64_content = base64.b64encode(content).decode() if isinstance(content, bytes) else base64.b64encode(content.encode()).decode()
                    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    attachments.append({
                        "content": b64_content,
                        "type": mime_type,
                        "filename": filename
                    })
            except Exception:
                pass
        
        if attachments:
            sg_payload["attachments"] = attachments
        
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {sg_key}",
                "Content-Type": "application/json"
            },
            data=json.dumps(sg_payload),
            timeout=30
        )
        
        if 200 <= resp.status_code < 300:
            return True
        else:
            st.error(f"SendGrid failed with status {resp.status_code}. Please check your SendGrid configuration.")
            return False
            
    except Exception as e:
        st.error(f"Email sending failed: {str(e)}")
        return False


def send_pdf_to_hr(record, hr_email, custom_subject=None):
    """Send the signed PDF to HR with a custom recipient.
    
    Args:
        record: Enrollment record dictionary (must include signature_pdf_path)
        hr_email: HR email address to send to
        custom_subject: Optional custom subject line
    
    Returns True on success, False otherwise.
    """
    if not hr_email:
        st.error("Please enter an HR email address.")
        return False
    
    subject = custom_subject or f"BYOV Signed Agreement - {record.get('full_name', 'Unknown')} (Tech ID: {record.get('tech_id', 'N/A')})"
    
    return send_email_notification(
        record,
        recipients=hr_email,
        subject=subject,
        attach_pdf_only=True
    )


def get_hr_notification_html(record, use_cid_logo=False):
    """Generate HTML email template for HR notification with signed PDF.
    Uses same styling as initial enrollment email but with limited fields.
    
    Args:
        record: Enrollment record dictionary
        use_cid_logo: If True, use cid:sears_logo reference (for CID attachment), 
                      otherwise use base64 data URI
    """
    submission_date = record.get('submission_date', '')
    formatted_date = submission_date
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            formatted_date = dt.strftime("%m/%d/%Y")
        except Exception:
            pass
    
    if use_cid_logo:
        logo_html = '<img src="cid:sears_logo" alt="Sears Home Services" style="max-width: 250px; height: auto; display: block; margin: 0 auto;">'
    else:
        logo_b64 = get_logo_base64()
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Sears Home Services" style="max-width: 250px; height: auto; display: block; margin: 0 auto;">' if logo_b64 else '<h2 style="color: #0066CC; margin: 0;">Sears Home Services</h2>'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>BYOV Signed Policy Form</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f7fa;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <div style="text-align: center; padding: 20px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
                {logo_html}
            </div>
            
            <!-- Header Banner -->
            <div style="background-color: #e8f4fc; padding: 20px; text-align: center; border-bottom: 3px solid #0d6efd;">
                <h2 style="color: #0d6efd; margin: 0; font-size: 22px;">
                    BYOV Signed Policy Form
                </h2>
                <p style="color: #666; margin: 10px 0 0 0; font-size: 14px;">
                    Please see attached signed policy form for the following technician
                </p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                
                <!-- Technician Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #0d6efd; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #0d6efd; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        Technician Details
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Name:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Tech ID:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('tech_id', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">District:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('district', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Date of Enrollment:</td>
                            <td style="padding: 8px 0; color: #333;">{formatted_date}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                    <p style="color: #666; margin: 0; font-size: 12px;">
                        This is an automated notification from the BYOV Enrollment System.
                        <br>The signed policy form is attached to this email.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def send_hr_policy_notification(record, pdf_path, hr_email="tyler.morgan@transformco.com"):
    """Send the signed policy PDF to HR with technician details via SendGrid.
    
    Args:
        record: Enrollment record dictionary
        pdf_path: Path to the signed PDF file
        hr_email: HR email address (defaults to tyler.morgan@transformco.com)
    
    Returns dict with 'success' or 'error' key.
    """
    if not hr_email:
        return {'error': 'No HR email address specified'}
    
    if not pdf_path or not file_storage.file_exists(pdf_path):
        return {'error': 'Signed PDF not found'}
    
    email_config = st.secrets.get("email", {})
    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    
    if not sg_key:
        return {'error': 'SendGrid is not configured. Please add SENDGRID_API_KEY to your secrets.'}
    
    if not sg_from:
        return {'error': 'SendGrid sender email not configured. Please add SENDGRID_FROM_EMAIL to your secrets.'}
    
    subject = f"BYOV Signed Policy Form - {record.get('full_name', 'Unknown')} (Tech ID: {record.get('tech_id', 'N/A')})"
    html_body = get_hr_notification_html(record, use_cid_logo=True)
    
    try:
        pdf_bytes = file_storage.read_file(pdf_path)
        pdf_filename = os.path.basename(pdf_path)
        
        attachments = [{
            "content": base64.b64encode(pdf_bytes).decode('utf-8'),
            "filename": pdf_filename,
            "type": "application/pdf",
            "disposition": "attachment"
        }]
        
        if os.path.exists(LOGO_PATH):
            with open(LOGO_PATH, 'rb') as f:
                logo_bytes = f.read()
            attachments.append({
                "content": base64.b64encode(logo_bytes).decode('utf-8'),
                "filename": "sears_logo.png",
                "type": "image/png",
                "disposition": "inline",
                "content_id": "sears_logo"
            })
        
        payload = {
            "personalizations": [{"to": [{"email": hr_email}]}],
            "from": {"email": sg_from},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}],
            "attachments": attachments
        }
        
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {sg_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        
        if 200 <= resp.status_code < 300:
            return {'success': True}
        else:
            return {'error': f'SendGrid error: {resp.status_code}'}
            
    except Exception as e:
        return {'error': str(e)}


def get_docusign_request_html(record, confirmation_url, use_cid_logo=False):
    """Generate HTML email template for DocuSign request to HR (California enrollments).
    
    Args:
        record: Enrollment record dictionary
        confirmation_url: Full URL for HR to confirm DocuSign completion
        use_cid_logo: If True, use cid:sears_logo reference for CID attachment
    """
    submission_date = record.get('submission_date', '')
    formatted_date = submission_date
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            formatted_date = dt.strftime("%m/%d/%Y at %I:%M %p")
        except Exception:
            pass
    
    if use_cid_logo:
        logo_html = '<img src="cid:sears_logo" alt="Sears Home Services" style="max-width: 250px; height: auto; display: block; margin: 0 auto;">'
    else:
        logo_b64 = get_logo_base64()
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Sears Home Services" style="max-width: 250px; height: auto; display: block; margin: 0 auto;">' if logo_b64 else '<h2 style="color: #0066CC; margin: 0;">Sears Home Services</h2>'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DocuSign Request - California BYOV Enrollment</title>
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f7fa;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <div style="text-align: center; padding: 20px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
                {logo_html}
            </div>
            
            <!-- Header Banner -->
            <div style="background-color: #fff3cd; padding: 20px; text-align: center; border-bottom: 3px solid #ffc107;">
                <h2 style="color: #856404; margin: 0; font-size: 22px;">
                    DocuSign Required - California Enrollment
                </h2>
                <p style="color: #856404; margin: 10px 0 0 0; font-size: 14px;">
                    Action Required: Please send DocuSign to technician's work phone
                </p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                
                <!-- Action Alert -->
                <div style="background: linear-gradient(to right, #fff3cd, #fff9e6); border-left: 4px solid #ffc107; border-radius: 8px; padding: 20px; margin-bottom: 20px;">
                    <p style="color: #856404; margin: 0; font-size: 14px;">
                        <strong>California state regulations require DocuSign for compliant electronic signatures.</strong>
                        <br><br>
                        Please text the DocuSign link to the technician's work phone to complete the BYOV Policy signature.
                    </p>
                </div>
                
                <!-- Technician Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #0d6efd; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #0d6efd; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        Technician Details
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Name:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Tech ID:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('tech_id', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">District:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('district', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">State:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('state', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Enrollment Date:</td>
                            <td style="padding: 8px 0; color: #333;">{formatted_date}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Vehicle Information Card -->
                <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid #28a745; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                    <h3 style="color: #28a745; margin: 0 0 15px 0; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;">
                        Vehicle Information
                    </h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 140px;">Year/Make/Model:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('year', 'N/A')} {record.get('make', '')} {record.get('model', '')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">VIN:</td>
                            <td style="padding: 8px 0; color: #333; font-family: monospace;">{record.get('vin', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <!-- Confirmation Button -->
                <div style="text-align: center; margin: 30px 0;">
                    <p style="color: #666; margin-bottom: 15px; font-size: 14px;">
                        After the technician has completed their DocuSign signature, click the button below to confirm:
                    </p>
                    <a href="{confirmation_url}" style="display: inline-block; background-color: #28a745; color: white; text-decoration: none; padding: 15px 30px; border-radius: 8px; font-weight: 600; font-size: 16px;">
                        Confirm DocuSign Completed
                    </a>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                    <p style="color: #666; margin: 0; font-size: 12px;">
                        This is an automated notification from the BYOV Enrollment System.
                        <br>This confirmation link will expire in 7 days.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def send_docusign_request_hr(record, enrollment_id):
    """Send DocuSign request email to HR for California enrollments.
    
    This function:
    1. Gets the HR email address from admin settings
    2. Creates a unique confirmation token in the database
    3. Sends an email to HR with technician details and a confirmation link
    
    Args:
        record: Enrollment record dictionary
        enrollment_id: Database ID of the enrollment
    
    Returns True on success, False otherwise.
    """
    import database
    
    email_config = st.secrets.get("email", {})
    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    
    if not sg_key or not sg_from:
        st.warning("SendGrid not configured. Cannot send DocuSign request.")
        return False
    
    hr_email = email_config.get("hr_email")
    if not hr_email:
        config = database.get_email_config()
        hr_email = config.get('hr_recipient') if config else None
    
    if not hr_email:
        st.warning("HR email not configured. Please set up HR email in Admin Settings.")
        return False
    
    try:
        token = database.create_docusign_token(enrollment_id)
        
        if not token:
            st.error("Failed to generate confirmation token.")
            return False
        
        base_url = os.getenv('REPLIT_DOMAINS', '').split(',')[0] if os.getenv('REPLIT_DOMAINS') else ''
        if base_url:
            base_url = f"https://{base_url}"
        else:
            base_url = os.getenv('REPLIT_DEV_DOMAIN', '')
            if base_url:
                base_url = f"https://{base_url}"
        
        confirmation_url = f"{base_url}/confirm-docusign/{token}"
        
        subject = f"DocuSign Required - {record.get('full_name', 'Unknown')} (Tech ID: {record.get('tech_id', 'N/A')}) - California"
        html_body = get_docusign_request_html(record, confirmation_url, use_cid_logo=True)
        
        attachments = []
        if os.path.exists(LOGO_PATH):
            try:
                with open(LOGO_PATH, 'rb') as f:
                    logo_bytes = f.read()
                attachments.append({
                    "content": base64.b64encode(logo_bytes).decode('utf-8'),
                    "filename": "sears_logo.png",
                    "type": "image/png",
                    "disposition": "inline",
                    "content_id": "sears_logo"
                })
            except Exception:
                pass
        
        payload = {
            "personalizations": [{"to": [{"email": hr_email}]}],
            "from": {"email": sg_from},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}]
        }
        
        if attachments:
            payload["attachments"] = attachments
        
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {sg_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
        
        if 200 <= resp.status_code < 300:
            return True
        else:
            st.error(f"Failed to send DocuSign request email: {resp.status_code}")
            return False
            
    except Exception as e:
        st.error(f"Error sending DocuSign request: {str(e)}")
        return False


def get_custom_html_template(record, selected_fields, field_metadata, use_cid_logo=False):
    """Generate HTML email with only the selected fields.
    
    Args:
        record: Enrollment record dictionary
        selected_fields: List of field keys to include
        field_metadata: List of field metadata dicts
        use_cid_logo: If True, use cid:sears_logo reference for CID attachment
    """
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y at %I:%M %p")
        except Exception:
            pass
    
    fields_by_group = {}
    for key in selected_fields:
        meta = next((f for f in field_metadata if f['key'] == key), None)
        if meta:
            group = meta.get('group', 'Other')
            if group not in fields_by_group:
                fields_by_group[group] = []
            
            value = record.get(key, 'N/A')
            if key in ('insurance_exp', 'registration_exp', 'submission_date') and value:
                try:
                    dt = datetime.fromisoformat(str(value))
                    value = dt.strftime("%m/%d/%Y")
                except Exception:
                    pass
            elif key == 'approved':
                value = 'Yes' if value == 1 else 'No'
            elif key == 'is_new_hire':
                value = 'New Hire (less than 30 days)' if value else 'Existing Tech'
            elif key == 'truck_number':
                value = value or 'N/A'
            elif key == 'industry':
                if isinstance(value, list):
                    value = ', '.join(value) if value else 'N/A'
            elif key == 'referred_by':
                value = value or record.get('referredBy') or 'N/A'
            
            fields_by_group[group].append({
                'label': meta['label'],
                'value': value if value else 'N/A'
            })
    
    group_colors = {
        'Technician': '#0d6efd',
        'Vehicle': '#28a745',
        'Compliance': '#ffc107',
        'Status': '#6c757d'
    }
    
    content_html = ""
    for group_name, fields in fields_by_group.items():
        color = group_colors.get(group_name, '#0d6efd')
        rows = "".join([
            f'<tr><td style="padding: 6px 0; color: #666; width: 140px;">{f["label"]}:</td>'
            f'<td style="padding: 6px 0; color: #333; font-weight: 500;">{f["value"]}</td></tr>'
            for f in fields
        ])
        content_html += f'''
        <div style="background: linear-gradient(to right, #f8f9fa, #ffffff); border-left: 4px solid {color}; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
            <h3 style="color: {color}; margin: 0 0 12px 0; font-size: 14px; text-transform: uppercase;">{group_name}</h3>
            <table style="width: 100%; border-collapse: collapse;">{rows}</table>
        </div>
        '''
    
    if use_cid_logo:
        logo_html = '<img src="cid:sears_logo" alt="Sears Home Services" style="max-width: 200px; height: auto;">'
    else:
        logo_b64 = get_logo_base64()
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" alt="Sears Home Services" style="max-width: 200px; height: auto;">' if logo_b64 else '<h2 style="color: #0066CC; margin: 0;">Sears Home Services</h2>'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f5f7fa;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="text-align: center; padding: 16px; background-color: #ffffff; border-bottom: 2px solid #0066CC;">
                {logo_html}
            </div>
            
            <div style="background-color: #e8f4fc; padding: 16px; text-align: center; border-bottom: 3px solid #0d6efd;">
                <h2 style="color: #0d6efd; margin: 0; font-size: 20px;">BYOV Enrollment Approved</h2>
                <p style="color: #666; margin: 8px 0 0 0; font-size: 13px;">{submission_date}</p>
            </div>
            
            <div style="padding: 24px;">
                {content_html if content_html else '<p style="color: #666;">No fields selected for this notification.</p>'}
                
                <div style="background-color: #f8f9fa; padding: 16px; border-radius: 8px; text-align: center; margin-top: 16px;">
                    <p style="color: #666; margin: 0; font-size: 11px;">
                        This is an automated notification from the BYOV Enrollment System.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def get_custom_plain_text(record, selected_fields, field_metadata):
    """Generate plain text email with only the selected fields."""
    lines = ["BYOV Enrollment Approved\n"]
    
    for key in selected_fields:
        meta = next((f for f in field_metadata if f['key'] == key), None)
        if meta:
            value = record.get(key, 'N/A')
            if key in ('insurance_exp', 'registration_exp', 'submission_date') and value:
                try:
                    dt = datetime.fromisoformat(str(value))
                    value = dt.strftime("%m/%d/%Y")
                except Exception:
                    pass
            elif key == 'approved':
                value = 'Yes' if value == 1 else 'No'
            elif key == 'is_new_hire':
                value = 'New Hire (less than 30 days)' if value else 'Existing Tech'
            elif key == 'truck_number':
                value = value or 'N/A'
            elif key == 'industry' and isinstance(value, list):
                value = ', '.join(value) if value else 'N/A'
            
            lines.append(f"- {meta['label']}: {value if value else 'N/A'}")
    
    lines.append("\nThis is an automated message from the BYOV Enrollment System.")
    return "\n".join(lines)


def send_custom_notification(record, recipients, subject, selected_fields, selected_docs, 
                             field_metadata, enrollment_id=None):
    """Send a custom email notification with selected fields and documents via SendGrid.
    
    Args:
        record: Enrollment record dictionary
        recipients: Email recipient(s) - string or list
        subject: Email subject line
        selected_fields: List of field keys to include in email body
        selected_docs: List of document types to attach ('signature', 'vehicle', 'registration', 'insurance')
        field_metadata: List of field metadata dicts with 'key', 'label', 'group'
        enrollment_id: Optional enrollment ID to fetch documents from database
    
    Returns True on success, dict with 'error' key on failure.
    """
    import database
    
    email_config = st.secrets.get("email", {})
    
    if isinstance(recipients, str):
        recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
    elif isinstance(recipients, (list, tuple)):
        recipient_list = [r for r in recipients if r]
    else:
        recipient_list = [str(recipients)] if recipients else []
    
    if not recipient_list:
        return {'error': 'No recipients specified'}
    
    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    
    if not sg_key:
        return {'error': 'SendGrid is not configured. Please add SENDGRID_API_KEY to your secrets.'}
    
    if not sg_from:
        return {'error': 'SendGrid sender email not configured. Please add SENDGRID_FROM_EMAIL to your secrets.'}
    
    html_body = get_custom_html_template(record, selected_fields, field_metadata, use_cid_logo=True) if selected_fields else "<p>Enrollment approved.</p>"
    plain_body = get_custom_plain_text(record, selected_fields, field_metadata) if selected_fields else "Enrollment approved."
    
    files = []
    if enrollment_id and selected_docs:
        try:
            docs = database.get_documents_for_enrollment(enrollment_id)
            for doc in docs:
                if doc['doc_type'] in selected_docs:
                    if file_storage.file_exists(doc['file_path']):
                        files.append(doc['file_path'])
        except Exception:
            pass
    
    try:
        attachments = []
        
        if os.path.exists(LOGO_PATH):
            try:
                with open(LOGO_PATH, 'rb') as f:
                    logo_data = f.read()
                attachments.append({
                    "content": base64.b64encode(logo_data).decode(),
                    "type": "image/png",
                    "filename": "sears_logo.png",
                    "disposition": "inline",
                    "content_id": "sears_logo"
                })
            except Exception:
                pass
        
        sg_payload = {
            "personalizations": [{"to": [{"email": r} for r in recipient_list]}],
            "from": {"email": sg_from},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": plain_body},
                {"type": "text/html", "value": html_body}
            ]
        }
        
        for file_path in files:
            try:
                content = file_storage.read_file(file_path)
                if content:
                    filename = os.path.basename(file_path)
                    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    b64_content = base64.b64encode(content).decode()
                    attachments.append({
                        "content": b64_content,
                        "type": mime_type,
                        "filename": filename
                    })
            except Exception:
                pass
        
        if attachments:
            sg_payload["attachments"] = attachments
        
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {sg_key}",
                "Content-Type": "application/json"
            },
            data=json.dumps(sg_payload),
            timeout=30
        )
        
        if 200 <= resp.status_code < 300:
            return True
        else:
            return {'error': f'SendGrid returned status {resp.status_code}'}
    except Exception as e:
        return {'error': str(e)}


def get_email_config_status():
    """Get the current email configuration status for display (SendGrid only)."""
    email_config = st.secrets.get("email", {})
    
    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    
    status = {
        "sendgrid_configured": bool(sg_key and sg_from),
        "sendgrid_from": sg_from or "Not configured",
        "sendgrid_api_key_set": bool(sg_key),
        "configured": bool(sg_key and sg_from)
    }
    
    return status


def send_docusign_request_to_hr(record, hr_email, confirmation_url, document_paths=None):
    """Send a DocuSign request email to HR for California enrollees.
    
    Args:
        record: Enrollment record dictionary
        hr_email: HR email address to send to
        confirmation_url: Unique URL for HR to click when DocuSign is completed
        document_paths: Optional list of document paths to attach
    
    Returns dict with 'success' or 'error' key.
    """
    if not hr_email:
        return {'error': 'No HR email address specified'}
    
    email_config = st.secrets.get("email", {})
    sg_key = email_config.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    sg_from = email_config.get("sendgrid_from_email") or os.getenv("SENDGRID_FROM_EMAIL")
    
    if not sg_key:
        return {'error': 'SendGrid is not configured. Please add SENDGRID_API_KEY to your secrets.'}
    
    if not sg_from:
        return {'error': 'SendGrid sender email not configured. Please add SENDGRID_FROM_EMAIL to your secrets.'}
    
    subject = f"DocuSign Request - BYOV Enrollment: {record.get('full_name', 'Unknown')} (Tech ID: {record.get('tech_id', 'N/A')})"
    
    submission_date = record.get('submission_date', '')
    if submission_date:
        try:
            dt = datetime.fromisoformat(submission_date)
            submission_date = dt.strftime("%m/%d/%Y at %I:%M %p")
        except Exception:
            submission_date = str(submission_date)
    
    logo_src = "cid:sears_logo"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); overflow: hidden;">
                <div style="background: linear-gradient(135deg, #1a365d 0%, #2c5282 100%); padding: 30px; text-align: center;">
                    <img src="{logo_src}" alt="Sears Home Services" style="max-width: 200px; height: auto;">
                </div>
                
                <div style="padding: 30px;">
                    <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px; border-radius: 4px;">
                        <h2 style="color: #856404; margin: 0 0 10px 0; font-size: 18px;">Action Required: DocuSign Signature</h2>
                        <p style="color: #856404; margin: 0;">Please send the BYOV enrollment form via DocuSign to this California technician.</p>
                    </div>
                    
                    <h3 style="color: #1a365d; margin-bottom: 15px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;">Technician Information</h3>
                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 40%;">Full Name:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('full_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Tech ID:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">{record.get('tech_id', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">District:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('district', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">State:</td>
                            <td style="padding: 8px 0; color: #333; font-weight: 600;">California (DocuSign Required)</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Enrollment Date:</td>
                            <td style="padding: 8px 0; color: #333;">{submission_date or 'N/A'}</td>
                        </tr>
                    </table>
                    
                    <h3 style="color: #1a365d; margin-bottom: 15px; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px;">Vehicle Information</h3>
                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                        <tr>
                            <td style="padding: 8px 0; color: #666; width: 40%;">Year:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('year', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Make:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('make', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">Model:</td>
                            <td style="padding: 8px 0; color: #333;">{record.get('model', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; color: #666;">VIN:</td>
                            <td style="padding: 8px 0; color: #333; font-family: monospace;">{record.get('vin', 'N/A')}</td>
                        </tr>
                    </table>
                    
                    <div style="background-color: #e8f5e9; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
                        <p style="color: #2e7d32; margin: 0 0 15px 0; font-weight: 600;">Once the technician has signed via DocuSign, click the button below:</p>
                        <a href="{confirmation_url}" style="display: inline-block; background-color: #2e7d32; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">Mark DocuSign Complete</a>
                    </div>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 20px;">
                        Note: Vehicle photos, registration, and insurance documents are attached to this email for your records.
                    </p>
                </div>
                
                <div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                    <p style="color: #666; margin: 0; font-size: 12px;">
                        This is an automated notification from the BYOV Enrollment System.
                        <br>California enrollments require DocuSign for compliance.
                    </p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    
    plain_body = f"""
DocuSign Request - BYOV Enrollment

ACTION REQUIRED: Please send the BYOV enrollment form via DocuSign to this California technician.

TECHNICIAN INFORMATION:
- Full Name: {record.get('full_name', 'N/A')}
- Tech ID: {record.get('tech_id', 'N/A')}
- District: {record.get('district', 'N/A')}
- State: California (DocuSign Required)
- Enrollment Date: {submission_date or 'N/A'}

VEHICLE INFORMATION:
- Year: {record.get('year', 'N/A')}
- Make: {record.get('make', 'N/A')}
- Model: {record.get('model', 'N/A')}
- VIN: {record.get('vin', 'N/A')}

Once the technician has signed via DocuSign, click this link to mark it complete:
{confirmation_url}

Vehicle photos, registration, and insurance documents are attached to this email.
    """
    
    try:
        attachments = []
        
        if os.path.exists(LOGO_PATH):
            try:
                with open(LOGO_PATH, 'rb') as f:
                    logo_data = f.read()
                attachments.append({
                    "content": base64.b64encode(logo_data).decode(),
                    "type": "image/png",
                    "filename": "sears_logo.png",
                    "disposition": "inline",
                    "content_id": "sears_logo"
                })
            except Exception:
                pass
        
        if document_paths:
            for file_path in document_paths:
                try:
                    content = file_storage.read_file(file_path)
                    if content:
                        filename = os.path.basename(file_path)
                        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                        b64_content = base64.b64encode(content).decode()
                        attachments.append({
                            "content": b64_content,
                            "type": mime_type,
                            "filename": filename
                        })
                except Exception:
                    pass
        
        sg_payload = {
            "personalizations": [{"to": [{"email": hr_email}]}],
            "from": {"email": sg_from},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": plain_body},
                {"type": "text/html", "value": html_body}
            ]
        }
        
        if attachments:
            sg_payload["attachments"] = attachments
        
        resp = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {sg_key}",
                "Content-Type": "application/json"
            },
            data=json.dumps(sg_payload),
            timeout=30
        )
        
        if 200 <= resp.status_code < 300:
            return {'success': True}
        else:
            return {'error': f'SendGrid error: {resp.status_code}'}
            
    except Exception as e:
        return {'error': str(e)}
