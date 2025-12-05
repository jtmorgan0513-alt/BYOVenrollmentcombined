import json
import os
import re
import shutil
import base64
from datetime import date, datetime
import io

import streamlit as st
import uuid
import certifi

# Configure SSL certificates before importing requests
# Prefer system CA certificates for better compatibility with Replit deployments
SYSTEM_CA_BUNDLE = '/etc/ssl/certs/ca-certificates.crt'
if os.path.exists(SYSTEM_CA_BUNDLE):
    os.environ['SSL_CERT_FILE'] = SYSTEM_CA_BUNDLE
    os.environ['REQUESTS_CA_BUNDLE'] = SYSTEM_CA_BUNDLE
else:
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import requests
import time
import logging

from streamlit_drawable_canvas import st_canvas
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

import database
from database import get_enrollment_by_id, get_documents_for_enrollment
from notifications import send_email_notification, send_docusign_request_hr
from admin_dashboard import page_admin_control_center
import file_storage

@st.cache_resource
def init_database():
    """Initialize database connection once and cache the result."""
    database.init_db()
    return True

def clear_enrollment_cache():
    """Clear cached enrollment data when data changes."""
    load_enrollments_cached.clear()


DATA_FILE = "enrollments.json"

# State to template mapping
STATE_TEMPLATE_MAP = {
    "CA": "template_2.pdf",
    "WA": "template_2.pdf",
    "IL": "template_2.pdf",
}
DEFAULT_TEMPLATE = "template_1.pdf"

# US States list (used in admin forms)
US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming"
]

INDUSTRIES = ["Cook", "Dish", "Laundry", "Micro", "Ref", "HVAC", "L&G"]


@st.cache_data(ttl=30)
def load_enrollments_cached():
    """Cached enrollment loader with 30 second TTL for performance.
    
    Returns enriched enrollment records with document paths.
    Uses short TTL to balance performance with data freshness.
    """
    rows = database.get_all_enrollments()
    records = []
    for r in rows:
        rec = dict(r)
        docs = database.get_documents_for_enrollment(rec.get('id'))
        rec['vehicle_photos_paths'] = [d['file_path'] for d in docs if d['doc_type'] == 'vehicle']
        rec['insurance_docs_paths'] = [d['file_path'] for d in docs if d['doc_type'] == 'insurance']
        rec['registration_docs_paths'] = [d['file_path'] for d in docs if d['doc_type'] == 'registration']
        sigs = [d['file_path'] for d in docs if d['doc_type'] == 'signature']
        rec['signature_pdf_path'] = sigs[0] if sigs else None
        records.append(rec)
    return records


def load_enrollments():
    """Compatibility wrapper that uses cached version.
    
    The application previously used a JSON file structure. The new
    `database` module stores enrollments and documents separately; this
    function adapts DB rows to the legacy record shape expected by the
    rest of the app (including *_paths lists and `signature_pdf_path`).
    """
    return load_enrollments_cached()


def save_enrollments(records):
    """Legacy no-op: new DB is authoritative. Kept for compatibility."""
    return


def delete_enrollment(identifier: str) -> tuple[bool, str]:
    """Delete enrollment and associated files from DB and storage.

    `identifier` may be the numeric enrollment id or the technician id.
    """
    try:
        rows = database.get_all_enrollments()
        target = None
        for r in rows:
            if str(r.get('id')) == str(identifier) or str(r.get('tech_id', '')) == str(identifier):
                target = r
                break

        if not target:
            return False, f"Record not found for Tech ID or ID: {identifier}"

        enrollment_id = target.get('id')

        docs = database.get_documents_for_enrollment(enrollment_id)
        files_to_delete = [d['file_path'] for d in docs if d.get('file_path')]

        deleted_files = 0
        for p in files_to_delete:
            if file_storage.delete_file(p):
                deleted_files += 1

        if files_to_delete and not file_storage.USE_OBJECT_STORAGE:
            first_file = files_to_delete[0]
            if not file_storage.is_object_storage_path(first_file):
                upload_dir = os.path.dirname(os.path.dirname(first_file))
                if os.path.exists(upload_dir) and os.path.isdir(upload_dir):
                    try:
                        shutil.rmtree(upload_dir)
                    except Exception:
                        pass

        database.delete_enrollment(enrollment_id)
        clear_enrollment_cache()

        return True, f"✅ Successfully deleted enrollment ID {enrollment_id} and {deleted_files} associated files."
    except Exception as e:
        return False, f"❌ Error deleting enrollment: {e}"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name or 'unnamed'


def create_upload_folder(tech_id: str, record_id: str) -> str:
    """Create upload folder using file_storage module."""
    return file_storage.create_upload_folder(tech_id, record_id)


def save_uploaded_files(uploaded_files, folder_path: str, prefix: str) -> list:
    """Save uploaded files using file_storage module."""
    return file_storage.save_uploaded_files(uploaded_files, folder_path, prefix)


def generate_signed_pdf(template_path: str, signature_image, output_path: str,
                        sig_x: int = 73, sig_y: int = 442, date_x: int = 320, date_y: int = 442,
                        employee_name: str = None, tech_id: str = None,
                        name_x: int = 260, name_y: int = 547, tech_id_x: int = 261, tech_id_y: int = 533,
                        sig_width: int = 160, sig_height: int = 28) -> bool:
    """Generate a PDF with signature, date, name, and tech ID overlay on page 6 (index 5).
    Returns True on success, False on failure.
    
    Args:
        template_path: Path to the PDF template
        signature_image: PIL Image of the signature
        output_path: Where to save the signed PDF
        sig_x, sig_y: Signature position
        date_x, date_y: Date position
        employee_name: Employee's full name to include
        tech_id: Employee's tech ID to include
        name_x, name_y: Name field position
        tech_id_x, tech_id_y: Tech ID field position
    """
    try:
        reader = PdfReader(template_path)
        writer = PdfWriter()

        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=letter)

        if signature_image is not None:
            temp_sig_path = "temp_signature.png"
            signature_image.save(temp_sig_path, format='PNG')
            can.drawImage(temp_sig_path, sig_x, sig_y, width=sig_width, height=sig_height,
                          preserveAspectRatio=True, mask='auto')
            try:
                os.remove(temp_sig_path)
            except Exception:
                pass

        can.setFont("Helvetica", 10)
        current_date = datetime.now().strftime("%m/%d/%Y")
        can.drawString(date_x, date_y, current_date)

        if employee_name:
            can.setFont("Helvetica", 10)
            can.drawString(name_x, name_y, employee_name)
        
        if tech_id:
            can.setFont("Helvetica", 10)
            can.drawString(tech_id_x, tech_id_y, str(tech_id))

        can.save()
        packet.seek(0)

        overlay_pdf = PdfReader(packet)

        for i in range(len(reader.pages)):
            page = reader.pages[i]
            if i == 5 and len(overlay_pdf.pages) > 0:
                page.merge_page(overlay_pdf.pages[0])
            writer.add_page(page)

        with open(output_path, "wb") as f:
            writer.write(f)

        return True
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        try:
            st.error(f"PDF generation error: {str(e)}")
            st.error(f"Details: {error_details}")
        except Exception:
            pass
        return False


def show_money_rain(count: int = 30, duration_ms: int = 5000):
    """Render a falling money (dollar) animation using pure HTML/CSS.

    Uses CSS keyframes only (no <script>) so it works reliably on
    Streamlit Cloud and newer Streamlit versions with stricter JS policies.
    The overlay fades out automatically after the given duration.
    """
    try:
        # Build bill divs with slight randomization for left position and delay
        bills = []
        for i in range(count):
            left = (i * 73) % 100  # spread across width
            delay = (i % 7) * 0.15
            dur = 3 + (i % 5) * 0.4
            rotate = (i * 37) % 360
            scale = 0.8 + (i % 3) * 0.15
            bills.append(
                f'<div class="bill" style="left:{left}%; animation-delay:{delay}s; animation-duration:{dur}s; transform: rotate({rotate}deg) scale({scale});">💵</div>'
            )

        fade_delay_s = max(0, duration_ms) / 1000.0

        html = f"""
        <style>
        .money-rain-wrapper {{
            pointer-events: none;
            position: fixed;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            z-index: 99999;
            opacity: 1;
            animation: fadeOut 0.6s ease-out forwards;
            animation-delay: {fade_delay_s}s;
        }}
        .money-rain-wrapper .bill {{
            position: absolute;
            top: -10%;
            font-size: 28px;
            will-change: transform, opacity;
            opacity: 0.95;
            text-shadow: 0 1px 0 rgba(0,0,0,0.12);
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.12));
            animation-name: fallAndRotate;
            animation-timing-function: linear;
            animation-iteration-count: 1;
        }}

        @keyframes fallAndRotate {{
            0% {{ transform: translateY(-10vh) rotate(0deg); opacity: 1; }}
            70% {{ opacity: 1; }}
            100% {{ transform: translateY(110vh) rotate(360deg); opacity: 0; }}
        }}

        @keyframes fadeOut {{
            to {{ opacity: 0; visibility: hidden; }}
        }}
        </style>

        <div class="money-rain-wrapper">
            {''.join(bills)}
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
    except Exception:
        # Silent fallback to built-in balloons if HTML injection is blocked
        try:
            st.balloons()
        except Exception:
            pass

# send_email_notification was moved to `notifications.py` to allow reuse by the
# admin control center without importing the whole Streamlit app.

def decode_vin(vin: str):
    vin = vin.strip().upper()
    if len(vin) < 11:
        return {}

    try:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevinvaluesextended/{vin}?format=json"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("Results", [])
        if not results:
            return {}

        result = results[0]

        year = result.get("ModelYear") or ""
        make = result.get("Make") or ""
        model = result.get("Model") or ""

        if not (year or make or model):
            return {}

        return {
            "year": year,
            "make": make,
            "model": model,
        }

    except Exception:
        return {}


def _get_dashboard_credentials():
    """Get dashboard credentials from environment variables.
    
    Returns tuple of (dashboard_url, username, password).
    Ensures dashboard_url has a proper https:// scheme.
    """
    dashboard_url = os.getenv("REPLIT_DASHBOARD_URL", "https://byovdashboard.replit.app")
    username = os.getenv("REPLIT_DASHBOARD_USERNAME", "admin")
    password = os.getenv("REPLIT_DASHBOARD_PASSWORD", "")
    
    if dashboard_url and not dashboard_url.startswith(("http://", "https://")):
        dashboard_url = f"https://{dashboard_url}"
    
    return dashboard_url, username, password


def _create_dashboard_session():
    """Create a requests session configured with SSL certificate verification.
    
    Uses system CA certificates for the verify parameter when available,
    with fallback to certifi's certificate bundle.
    Returns a tuple of (session, ca_bundle_path) where ca_bundle_path should
    be passed to verify= parameter in all requests.
    """
    session = requests.Session()
    if os.path.exists(SYSTEM_CA_BUNDLE):
        ca_bundle = SYSTEM_CA_BUNDLE
    else:
        ca_bundle = certifi.where()
    return session, ca_bundle


def post_to_dashboard(record: dict, enrollment_id: int) -> dict:
    """Create technician in Replit dashboard with complete data and photo uploads.
    
    Authentication Flow:
    1. POST /api/login with username/password to get session cookie
    2. POST /api/technicians with complete enrollment data using session
    3. Upload photos using GCS flow (get URL → PUT file → save photo record)
    
    Returns status dict with photo_count for UI messaging.
    """
    dashboard_url, username, password = _get_dashboard_credentials()
    
    try:
        from datetime import datetime
        
        # Step 1: Create session and login
        session, ca_bundle = _create_dashboard_session()
        
        login_payload = {
            "username": username,
            "password": password
        }
        
        login_resp = session.post(
            f"{dashboard_url}/api/login",
            json=login_payload,
            timeout=10,
            verify=ca_bundle
        )
        
        if not login_resp.ok:
            return {
                "error": f"Login failed with status {login_resp.status_code}",
                "body": login_resp.text[:200]
            }
        
        # Step 2: Format dates for dashboard (ISO to YYYY-MM-DD)
        def format_date(date_str):
            if not date_str:
                return None
            try:
                dt = datetime.fromisoformat(date_str)
                return dt.strftime("%Y-%m-%d")
            except Exception:
                return None
        
        submission_date = record.get("submission_date", "")
        date_started = format_date(submission_date) or datetime.now().strftime("%Y-%m-%d")
        # Accept multiple possible field names coming from DB or legacy code
        insurance_exp = format_date(
            record.get("insurance_exp") or record.get("insurance_expiration") or record.get("insuranceExpiration")
        )
        registration_exp = format_date(
            record.get("registration_exp") or record.get("registration_expiration") or record.get("registrationExpiration")
        )
        
        # Step 3: Check if technician already exists
        tech_id = record.get("tech_id", "").upper()  # MUST BE UPPERCASE
        if not tech_id:
            return {"error": "record missing tech_id"}
        
        check_resp = session.get(
            f"{dashboard_url}/api/technicians",
            params={"techId": tech_id},
            timeout=10,
            verify=ca_bundle
        )
        
        if check_resp.ok:
            try:
                existing = check_resp.json()
                if isinstance(existing, list) and existing:
                    return {"status": "exists", "photo_count": 0}
            except Exception:
                pass
        
        # Step 4: Format industry as comma-separated string (accept 'industry' or 'industries')
        industry_raw = record.get('industry')
        if industry_raw is None:
            industry_raw = record.get('industries', [])
        if isinstance(industry_raw, list):
            industry = ", ".join(industry_raw) if industry_raw else ""
        else:
            industry = str(industry_raw) if industry_raw else ""

        # Referred by (accept either 'referred_by' or 'referredBy')
        referred_by_val = record.get('referred_by') or record.get('referredBy') or ""

        # Step 5: Create technician payload with complete field mapping
        payload = {
            "name": record.get("full_name"),
            "techId": tech_id,  # UPPERCASE
            "region": record.get("state"),
            "district": record.get("district"),
            "referredBy": referred_by_val,
            "enrollmentStatus": "Enrolled",  # Always "Enrolled" on approval
            "dateStartedByov": date_started,
            "vinNumber": record.get("vin"),
            "vehicleMake": record.get("make"),
            "vehicleModel": record.get("model"),
            "vehicleYear": record.get("year"),
            "industry": industry,  # Comma-separated
            "insuranceExpiration": insurance_exp,  # YYYY-MM-DD
            "registrationExpiration": registration_exp  # YYYY-MM-DD
        }
        
        # Step 6: POST to create technician
        create_resp = session.post(
            f"{dashboard_url}/api/technicians",
            json=payload,
            timeout=15,
            verify=ca_bundle
        )
        
        if not (200 <= create_resp.status_code < 300):
            return {
                "error": f"dashboard responded {create_resp.status_code}",
                "body": create_resp.text[:200]
            }
        
        # Get created technician ID from response
        try:
            tech_data = create_resp.json()
            dashboard_tech_id = tech_data.get("id")
        except Exception:
            return {"error": "Failed to parse technician response"}
        
        if not dashboard_tech_id:
            return {"error": "No technician ID in response"}
        
        # Step 7: Upload photos using GCS flow
        photo_count = 0
        failed_uploads = []

        # Simple logging helper for diagnosing dashboard sync issues
        def dashboard_log(message: str):
            try:
                os.makedirs('logs', exist_ok=True)
                with open(os.path.join('logs', 'dashboard_sync.log'), 'a', encoding='utf-8') as lf:
                    lf.write(f"{datetime.now().isoformat()} {message}\n")
            except Exception:
                pass

        # Generic retry wrapper for operations that return a requests.Response
        def retry_request(func, attempts=3, backoff_base=0.5):
            last_exc = None
            for attempt in range(1, attempts + 1):
                try:
                    resp = func()
                    # If callable returned a Response-like object, check .ok
                    if hasattr(resp, 'ok'):
                        if resp.ok:
                            return resp
                        else:
                            raise RuntimeError(f"status_{resp.status_code}")
                    # Otherwise return value directly
                    return resp
                except Exception as e:
                    last_exc = e
                    dashboard_log(f"Retry attempt {attempt} failed: {e}")
                    if attempt < attempts:
                        time.sleep(backoff_base * (2 ** (attempt - 1)))
            raise last_exc

        # If record doesn't include file paths, try to load from local DB using enrollment_id
        vehicle_paths = []
        insurance_paths = []
        registration_paths = []
        try:
            if record.get("vehicle_photos_paths"):
                vehicle_paths = list(record.get("vehicle_photos_paths") or [])
            if record.get("insurance_docs_paths"):
                insurance_paths = list(record.get("insurance_docs_paths") or [])
            if record.get("registration_docs_paths"):
                registration_paths = list(record.get("registration_docs_paths") or [])

            # Fallback: fetch from database documents if enrollment_id provided
            if enrollment_id and not (vehicle_paths or insurance_paths or registration_paths):
                docs = database.get_documents_for_enrollment(enrollment_id)
                for d in docs:
                    p = d.get('file_path')
                    if not p:
                        continue
                    if d.get('doc_type') == 'vehicle':
                        vehicle_paths.append(p)
                    elif d.get('doc_type') == 'insurance':
                        insurance_paths.append(p)
                    elif d.get('doc_type') == 'registration':
                        registration_paths.append(p)
        except Exception:
            # If DB access fails, continue and attempt uploads for any paths present
            pass

        from mimetypes import guess_type

        category_to_paths = {
            'vehicle': vehicle_paths,
            'insurance': insurance_paths,
            'registration': registration_paths
        }

        # Upload files to GCS and collect registration entries. We'll attempt a
        # batch register endpoint on the dashboard first (/photos/batch). If that
        # endpoint isn't supported or fails, we fall back to per-photo POSTs.
        uploaded_entries = []  # each: {uploadURL, category, mimeType, path}

        for category, paths in category_to_paths.items():
            for photo_path in (paths or []):
                if not photo_path or not os.path.exists(photo_path):
                    failed_uploads.append({'path': photo_path, 'reason': 'missing'})
                    continue

                try:
                    # Get upload URL from dashboard (with retries)
                    try:
                        upload_req = retry_request(lambda: session.post(
                            f"{dashboard_url}/api/objects/upload",
                            json={"category": category},
                            timeout=10,
                            verify=ca_bundle
                        ), attempts=3, backoff_base=0.6)
                    except Exception as e:
                        dashboard_log(f"Failed to get upload URL for {photo_path}: {e}")
                        failed_uploads.append({'path': photo_path, 'reason': str(e)})
                        continue

                    upload_data = upload_req.json()
                    gcs_url = upload_data.get("uploadURL")
                    if not gcs_url:
                        dashboard_log(f"No uploadURL returned for {photo_path}: {upload_data}")
                        failed_uploads.append({'path': photo_path, 'reason': 'no_upload_url'})
                        continue

                    # Upload file to GCS (with retries)
                    mime_type, _ = guess_type(photo_path)
                    if not mime_type:
                        mime_type = 'application/octet-stream'

                    try:
                        def do_put():
                            with open(photo_path, 'rb') as f:
                                r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60)
                                return r
                        gcs_resp = retry_request(do_put, attempts=3, backoff_base=0.6)
                    except Exception as e:
                        dashboard_log(f"GCS PUT failed for {photo_path}: {e}")
                        failed_uploads.append({'path': photo_path, 'reason': str(e)})
                        continue

                    dashboard_log(f"Uploaded {photo_path} to GCS: {gcs_url}")

                    # Append to batch registration list
                    uploaded_entries.append({
                        'uploadURL': gcs_url,
                        'category': category,
                        'mimeType': mime_type,
                        'path': photo_path
                    })

                except Exception as exc:
                    dashboard_log(f"Unexpected error handling {photo_path}: {exc}")
                    failed_uploads.append({'path': photo_path, 'reason': str(exc)})
                    continue

        # Attempt batch registration if we have entries
        if uploaded_entries:
            try:
                batch_payload = {'photos': [
                    { 'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType'] }
                    for e in uploaded_entries
                ]}

                batch_resp = session.post(
                    f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos/batch",
                    json=batch_payload,
                    timeout=20,
                    verify=ca_bundle
                )

                if batch_resp.ok:
                    # Assume batch returns list of registered photos or a success status
                    try:
                        resp_data = batch_resp.json()
                        registered = len(resp_data) if isinstance(resp_data, list) else len(uploaded_entries)
                    except Exception:
                        registered = len(uploaded_entries)
                    photo_count += registered
                    dashboard_log(f"Batch registered {registered} photos for technician {dashboard_tech_id}")
                else:
                    dashboard_log(f"Batch registration failed with status {batch_resp.status_code}; falling back to per-photo registration")
                    # Batch not supported or failed: fall back to per-photo registration
                    for e in uploaded_entries:
                        try:
                            photo_payload = {
                                'uploadURL': e['uploadURL'],
                                'category': e['category'],
                                'mimeType': e['mimeType']
                            }
                            try:
                                photo_resp = retry_request(lambda: session.post(
                                    f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos",
                                    json=photo_payload,
                                    timeout=10,
                                    verify=ca_bundle
                                ), attempts=3, backoff_base=0.6)
                                photo_count += 1
                                dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id}")
                            except Exception as reg_exc:
                                dashboard_log(f"Photo registration failed for {e.get('path')}: {reg_exc}")
                                failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                        except Exception as exc:
                            dashboard_log(f"Per-photo registration unexpected error: {exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(exc)})
            except Exception as exc:
                # If batch attempt itself errored, attempt per-photo registration
                for e in uploaded_entries:
                    try:
                        photo_payload = {
                            'uploadURL': e['uploadURL'],
                            'category': e['category'],
                            'mimeType': e['mimeType']
                        }
                        try:
                            photo_resp = retry_request(lambda: session.post(
                                f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos",
                                json=photo_payload,
                                timeout=10,
                                verify=ca_bundle
                            ), attempts=3, backoff_base=0.6)
                            photo_count += 1
                            dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id} after batch error")
                        except Exception as reg_exc:
                            dashboard_log(f"Per-photo registration failed for {e.get('path')} after batch error: {reg_exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                    except Exception as exc2:
                        failed_uploads.append({'path': e.get('path'), 'reason': str(exc2)})

        result = {"status": "created", "photo_count": photo_count}
        if failed_uploads:
            result['failed_uploads'] = failed_uploads
        return result
            
    except Exception as e:
        return {"error": str(e)}


def post_to_dashboard_single_request(record: dict, enrollment_id: int = None, endpoint_path="/api/external/technicians") -> dict:
    """
    Create technician and attach photos in a single request using the external
    API that accepts base64-embedded photos.

    Payload shape follows the external API specification. Photos are
    included as objects with `category` and `base64` (either data URL or raw
    base64). Enforces 10MB per photo limit.
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    if not dashboard_url:
        return {"error": "dashboard url not configured"}

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Helper to format dates to YYYY-MM-DD
    from datetime import datetime
    def format_date(date_str):
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None

    # Tech id
    tech_id = (record.get('tech_id') or record.get('techId') or '').upper()
    if not tech_id:
        return {"error": "missing tech_id"}

    # Build payload mapping according to external API
    # Use empty strings for missing optional string fields to avoid null validation errors
    payload = {
        "name": record.get("full_name") or record.get("name") or "",
        "techId": tech_id,
        "region": record.get("region") or record.get("state") or "",
        "district": record.get("district") or "",
        "enrollmentStatus": record.get("enrollmentStatus", "Enrolled"),
        "truckId": record.get("truckId") or record.get("truck_id") or "",
        "mobilePhoneNumber": record.get("mobilePhoneNumber") or record.get("mobile") or record.get("phone") or "",
        "techEmail": record.get("techEmail") or record.get("email") or "",
        "cityState": record.get("cityState") or "",
        "vinNumber": record.get("vin") or record.get("vinNumber") or "",
        "insuranceExpiration": format_date(record.get("insurance_exp") or record.get("insuranceExpiration")) or "",
        "registrationExpiration": format_date(record.get("registration_exp") or record.get("registrationExpiration")) or "",
    }

    # Optional fields: vehicleMake/Model/Year/industry/dateStartedByov
    if record.get('make'):
        payload['vehicleMake'] = record.get('make')
    if record.get('model'):
        payload['vehicleModel'] = record.get('model')
    if record.get('year'):
        payload['vehicleYear'] = record.get('year')
    industry_raw = record.get('industry') if record.get('industry') is not None else record.get('industries', [])
    if isinstance(industry_raw, (list, tuple)):
        payload['industry'] = ", ".join(industry_raw)
    elif industry_raw:
        payload['industry'] = str(industry_raw)
    date_started = format_date(record.get('submission_date') or record.get('dateStartedByov'))
    if date_started:
        payload['dateStartedByov'] = date_started
    
    # Referred by field
    referred_by = record.get('referred_by') or record.get('referredBy') or ""
    if referred_by:
        payload['referredBy'] = referred_by

    # Collect documents (file paths) to include as base64 photos
    docs = []
    try:
        if enrollment_id:
            docs = database.get_documents_for_enrollment(enrollment_id) or []
        else:
            docs = record.get('documents') or []
    except Exception:
        docs = record.get('documents') or []

    photos = []
    failed_photos = []
    import base64 as _b64, mimetypes as _mimetypes
    MAX_BYTES = 10 * 1024 * 1024  # 10MB

    for d in docs:
        path = d.get('file_path') if isinstance(d, dict) else None
        category = d.get('doc_type') or d.get('category') or 'vehicle'
        if not path or not os.path.exists(path):
            failed_photos.append({'path': path, 'error': 'missing'})
            continue
        try:
            size = os.path.getsize(path)
            if size > MAX_BYTES:
                failed_photos.append({'path': path, 'error': 'size_exceeded', 'size': size})
                continue
            with open(path, 'rb') as fh:
                b = fh.read()
            
            # Debug logging
            import hashlib
            file_hash = hashlib.md5(b).hexdigest()[:8]
            print(f"[DEBUG] Encoding photo: {os.path.basename(path)} | Category: {category} | Size: {size} | Hash: {file_hash}")
            
            raw_b64 = _b64.b64encode(b).decode('ascii')
            mime = _mimetypes.guess_type(path)[0] or 'application/octet-stream'
            # Prefer data URL when we have a known mime (matches example)
            if mime.startswith('image/') or mime == 'application/pdf':
                data_url = f"data:{mime};base64,{raw_b64}"
                photos.append({'category': category, 'base64': data_url})
            else:
                photos.append({'category': category, 'base64': raw_b64})
        except Exception as e:
            failed_photos.append({'path': path, 'error': str(e)})

    if photos:
        payload['photos'] = photos

    # POST to external endpoint
    url = dashboard_url.rstrip('/') + endpoint_path
    try:
        resp = session.post(url, json=payload, timeout=30, verify=ca_bundle)
    except Exception as e:
        return {"error": f"request failed: {e}", "failed_photos": failed_photos}

    # Interpret response
    result = {"status_code": resp.status_code}
    try:
        resp_json = resp.json()
    except Exception:
        resp_json = {"raw_text": resp.text}
    result['response'] = resp_json
    result['photo_count'] = len(photos)
    if failed_photos:
        result['failed_photos'] = failed_photos

    # On success/partial, persist dashboard id if present
    tech_id_returned = None
    if isinstance(resp_json, dict):
        # Response may include technician obj or id
        tech = resp_json.get('technician') or resp_json.get('technicianCreated') or resp_json
        if isinstance(tech, dict):
            tech_id_returned = tech.get('id') or tech.get('techId')
        else:
            tech_id_returned = resp_json.get('id') or resp_json.get('technicianId')

    if enrollment_id and tech_id_returned:
        try:
            report = {"photo_count": len(photos)}
            if failed_photos:
                report['failed_uploads'] = failed_photos
            report['response'] = resp_json
            database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=str(tech_id_returned), report=report)
        except Exception:
            pass

    # Interpret status codes: 201 -> success, 207 -> partial
    if resp.status_code in (201, 207) or (200 <= resp.status_code < 300):
        return result
    else:
        return result


def create_technician_on_dashboard(record: dict) -> dict:
    """Create a technician on the external dashboard using admin credentials.

    Returns: {status: 'created'|'exists', dashboard_tech_id: str, error: str}
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Format minimal fields same as post_to_dashboard
    from datetime import datetime
    def format_date(date_str):
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None

    submission_date = record.get("submission_date", "")
    date_started = format_date(submission_date) or datetime.now().strftime("%Y-%m-%d")

    tech_id = (record.get('tech_id') or '').upper()
    if not tech_id:
        return {"error": "missing tech_id"}

    # Format industry
    industry_raw = record.get('industry') if record.get('industry') is not None else record.get('industries', [])
    if isinstance(industry_raw, list):
        industry = ", ".join(industry_raw) if industry_raw else ""
    else:
        industry = str(industry_raw) if industry_raw else ""

    referred_by_val = record.get('referred_by') or record.get('referredBy') or ""

    payload = {
        "name": record.get("full_name"),
        "techId": tech_id,
        "region": record.get("state"),
        "district": record.get("district"),
        "referredBy": referred_by_val,
        "enrollmentStatus": "Enrolled",
        "dateStartedByov": date_started,
        "vinNumber": record.get("vin"),
        "vehicleMake": record.get("make"),
        "vehicleModel": record.get("model"),
        "vehicleYear": record.get("year"),
        "industry": industry,
        "insuranceExpiration": format_date(record.get("insurance_exp")),
        "registrationExpiration": format_date(record.get("registration_exp"))
    }

    try:
        create_resp = session.post(f"{dashboard_url}/api/technicians", json=payload, timeout=15, verify=ca_bundle)
        if not (200 <= create_resp.status_code < 300):
            return {"error": f"create responded {create_resp.status_code}", "body": create_resp.text[:200]}
        try:
            data = create_resp.json()
            dashboard_tech_id = data.get('id')
        except Exception:
            return {"error": "failed to parse create response"}
        if not dashboard_tech_id:
            return {"error": "no id returned"}
        return {"status": "created", "dashboard_tech_id": dashboard_tech_id}
    except Exception as e:
        return {"error": str(e)}


def upload_photos_for_technician(enrollment_id: int, dashboard_tech_id: str = None) -> dict:
    """Upload photos for a given enrollment to the dashboard technician id.

    If `dashboard_tech_id` is not provided, attempts to look up by tech_id on the dashboard.
    Returns: {photo_count: int, failed_uploads: [...]}
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Load enrollment record and document paths
    try:
        record = database.get_enrollment_by_id(enrollment_id)
    except Exception:
        record = None

    if not record:
        return {"error": "enrollment not found"}

    tech_id = (record.get('tech_id') or '').upper()
    if not dashboard_tech_id:
        # Try to find technician by techId on dashboard
        try:
            check_resp = session.get(f"{dashboard_url}/api/technicians", params={"techId": tech_id}, timeout=10, verify=ca_bundle)
            if check_resp.ok:
                try:
                    existing = check_resp.json()
                    if isinstance(existing, list) and existing:
                        dashboard_tech_id = existing[0].get('id')
                except Exception:
                    pass
        except Exception:
            pass

    if not dashboard_tech_id:
        return {"error": "dashboard technician id not provided and lookup failed"}

    # Reuse upload logic from post_to_dashboard
    photo_count = 0
    failed_uploads = []

    def dashboard_log(message: str):
        try:
            os.makedirs('logs', exist_ok=True)
            with open(os.path.join('logs', 'dashboard_sync.log'), 'a', encoding='utf-8') as lf:
                lf.write(f"{datetime.now().isoformat()} {message}\n")
        except Exception:
            pass

    def retry_request(func, attempts=3, backoff_base=0.5):
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                resp = func()
                if hasattr(resp, 'ok'):
                    if resp.ok:
                        return resp
                    else:
                        raise RuntimeError(f"status_{resp.status_code}")
                return resp
            except Exception as e:
                last_exc = e
                dashboard_log(f"Retry attempt {attempt} failed: {e}")
                if attempt < attempts:
                    time.sleep(backoff_base * (2 ** (attempt - 1)))
        raise last_exc

    # Collect file paths
    try:
        docs = database.get_documents_for_enrollment(enrollment_id)
        vehicle_paths = [d['file_path'] for d in docs if d['doc_type'] == 'vehicle']
        insurance_paths = [d['file_path'] for d in docs if d['doc_type'] == 'insurance']
        registration_paths = [d['file_path'] for d in docs if d['doc_type'] == 'registration']
    except Exception:
        vehicle_paths = record.get('vehicle_photos_paths', []) or []
        insurance_paths = record.get('insurance_docs_paths', []) or []
        registration_paths = record.get('registration_docs_paths', []) or []

    from mimetypes import guess_type

    category_to_paths = {
        'vehicle': vehicle_paths,
        'insurance': insurance_paths,
        'registration': registration_paths
    }

    uploaded_entries = []
    for category, paths in category_to_paths.items():
        for photo_path in (paths or []):
            if not photo_path or not os.path.exists(photo_path):
                failed_uploads.append({'path': photo_path, 'reason': 'missing'})
                continue
            try:
                try:
                    upload_req = retry_request(lambda: session.post(
                        f"{dashboard_url}/api/objects/upload",
                        json={"category": category},
                        timeout=10,
                        verify=ca_bundle
                    ), attempts=3, backoff_base=0.6)
                except Exception as e:
                    dashboard_log(f"Failed to get upload URL for {photo_path}: {e}")
                    failed_uploads.append({'path': photo_path, 'reason': str(e)})
                    continue

                upload_data = upload_req.json()
                gcs_url = upload_data.get("uploadURL")
                if not gcs_url:
                    dashboard_log(f"No uploadURL returned for {photo_path}: {upload_data}")
                    failed_uploads.append({'path': photo_path, 'reason': 'no_upload_url'})
                    continue

                mime_type, _ = guess_type(photo_path)
                if not mime_type:
                    mime_type = 'application/octet-stream'

                try:
                    def do_put():
                        with open(photo_path, 'rb') as f:
                            r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60, verify=ca_bundle)
                            return r
                    gcs_resp = retry_request(do_put, attempts=3, backoff_base=0.6)
                except Exception as e:
                    dashboard_log(f"GCS PUT failed for {photo_path}: {e}")
                    failed_uploads.append({'path': photo_path, 'reason': str(e)})
                    continue

                dashboard_log(f"Uploaded {photo_path} to GCS: {gcs_url}")
                uploaded_entries.append({'uploadURL': gcs_url, 'category': category, 'mimeType': mime_type, 'path': photo_path})
            except Exception as exc:
                dashboard_log(f"Unexpected error handling {photo_path}: {exc}")
                failed_uploads.append({'path': photo_path, 'reason': str(exc)})
                continue

    # Register uploaded entries
    if uploaded_entries:
        try:
            batch_payload = {'photos': [ {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']} for e in uploaded_entries ]}
            batch_resp = session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos/batch", json=batch_payload, timeout=20, verify=ca_bundle)
            if batch_resp.ok:
                try:
                    resp_data = batch_resp.json()
                    registered = len(resp_data) if isinstance(resp_data, list) else len(uploaded_entries)
                except Exception:
                    registered = len(uploaded_entries)
                photo_count += registered
                dashboard_log(f"Batch registered {registered} photos for technician {dashboard_tech_id}")
            else:
                dashboard_log(f"Batch registration failed with status {batch_resp.status_code}; falling back to per-photo registration")
                for e in uploaded_entries:
                    try:
                        photo_payload = {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']}
                        try:
                            photo_resp = retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos", json=photo_payload, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
                            photo_count += 1
                            dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id}")
                        except Exception as reg_exc:
                            dashboard_log(f"Photo registration failed for {e.get('path')}: {reg_exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                    except Exception as exc:
                        dashboard_log(f"Per-photo registration unexpected error: {exc}")
                        failed_uploads.append({'path': e.get('path'), 'reason': str(exc)})
        except Exception as exc:
            for e in uploaded_entries:
                try:
                    photo_payload = {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']}
                    try:
                        photo_resp = retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos", json=photo_payload, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
                        photo_count += 1
                        dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id} after batch error")
                    except Exception as reg_exc:
                        dashboard_log(f"Per-photo registration failed for {e.get('path')} after batch error: {reg_exc}")
                        failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                except Exception as exc2:
                    failed_uploads.append({'path': e.get('path'), 'reason': str(exc2)})

    report = {"photo_count": photo_count}
    if failed_uploads:
        report['failed_uploads'] = failed_uploads

    # Persist report to DB for retries
    try:
        database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=dashboard_tech_id, report=report)
    except Exception:
        pass

    result = {"photo_count": photo_count}
    if failed_uploads:
        result['failed_uploads'] = failed_uploads
    return result


def retry_failed_uploads(enrollment_id: int) -> dict:
    """Retry previously failed photo uploads recorded in `last_upload_report`.

    Returns: {retried_count: int, remaining_failed: int, still_failed: [...]} 
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    # Load enrollment and report
    try:
        record = database.get_enrollment_by_id(enrollment_id)
    except Exception:
        record = None
    if not record:
        return {"error": "enrollment not found"}

    # Determine dashboard technician id
    dashboard_id = record.get('dashboard_tech_id')
    tech_id = (record.get('tech_id') or '').upper()
    if not dashboard_id:
        try:
            check_resp = session.get(f"{dashboard_url}/api/technicians", params={"techId": tech_id}, timeout=10, verify=ca_bundle)
            if check_resp.ok:
                try:
                    existing = check_resp.json()
                    if isinstance(existing, list) and existing:
                        dashboard_id = existing[0].get('id')
                except Exception:
                    pass
        except Exception:
            pass

    if not dashboard_id:
        return {"error": "dashboard technician id not found"}

    # Parse last_upload_report
    last_report = record.get('last_upload_report')
    if not last_report:
        return {"error": "no last_upload_report available"}
    try:
        if isinstance(last_report, str):
            report_obj = json.loads(last_report)
        else:
            report_obj = last_report
    except Exception:
        report_obj = last_report if isinstance(last_report, dict) else {}

    failed = report_obj.get('failed_uploads', []) if isinstance(report_obj, dict) else []
    if not failed:
        return {"retried_count": 0, "remaining_failed": 0}

    # Map file paths to document categories
    try:
        docs = database.get_documents_for_enrollment(enrollment_id)
        path_to_category = {d.get('file_path'): d.get('doc_type') for d in docs}
    except Exception:
        path_to_category = {}

    from mimetypes import guess_type

    retried = 0
    still_failed = []

    def dashboard_log(message: str):
        try:
            os.makedirs('logs', exist_ok=True)
            with open(os.path.join('logs', 'dashboard_sync.log'), 'a', encoding='utf-8') as lf:
                lf.write(f"{datetime.now().isoformat()} {message}\n")
        except Exception:
            pass

    def retry_request(func, attempts=3, backoff_base=0.5):
        last_exc = None
        for attempt in range(1, attempts + 1):
            try:
                resp = func()
                if hasattr(resp, 'ok'):
                    if resp.ok:
                        return resp
                    else:
                        raise RuntimeError(f"status_{resp.status_code}")
                return resp
            except Exception as e:
                last_exc = e
                dashboard_log(f"Retry attempt {attempt} failed: {e}")
                if attempt < attempts:
                    time.sleep(backoff_base * (2 ** (attempt - 1)))
        raise last_exc

    for entry in failed:
        path = entry.get('path') if isinstance(entry, dict) else None
        if not path or not os.path.exists(path):
            still_failed.append({'path': path, 'reason': 'missing'})
            continue

        category = path_to_category.get(path, 'vehicle')
        try:
            try:
                upload_req = retry_request(lambda: session.post(f"{dashboard_url}/api/objects/upload", json={"category": category}, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
            except Exception as e:
                dashboard_log(f"Failed to get upload URL for {path}: {e}")
                still_failed.append({'path': path, 'reason': str(e)})
                continue

            upload_data = upload_req.json()
            gcs_url = upload_data.get('uploadURL')
            if not gcs_url:
                dashboard_log(f"No uploadURL returned for {path}: {upload_data}")
                still_failed.append({'path': path, 'reason': 'no_upload_url'})
                continue

            mime_type, _ = guess_type(path)
            if not mime_type:
                mime_type = 'application/octet-stream'

            try:
                def do_put():
                    with open(path, 'rb') as f:
                        r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60, verify=ca_bundle)
                        return r
                gcs_resp = retry_request(do_put, attempts=3, backoff_base=0.6)
            except Exception as e:
                dashboard_log(f"GCS PUT failed for {path}: {e}")
                still_failed.append({'path': path, 'reason': str(e)})
                continue

            # Register photo for technician
            try:
                photo_payload = {'uploadURL': gcs_url, 'category': category, 'mimeType': mime_type}
                try:
                    reg_resp = retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_id}/photos", json=photo_payload, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
                    retried += 1
                    dashboard_log(f"Retried and registered photo {path} for tech {dashboard_id}")
                except Exception as reg_exc:
                    dashboard_log(f"Photo registration failed for {path}: {reg_exc}")
                    still_failed.append({'path': path, 'reason': str(reg_exc)})
            except Exception as exc:
                dashboard_log(f"Unexpected registration error for {path}: {exc}")
                still_failed.append({'path': path, 'reason': str(exc)})

        except Exception as exc:
            dashboard_log(f"Unexpected error retrying {path}: {exc}")
            still_failed.append({'path': path, 'reason': str(exc)})

    # Update report and persist
    new_photo_count = (report_obj.get('photo_count', 0) if isinstance(report_obj, dict) else 0) + retried
    new_report = {"photo_count": new_photo_count}
    if still_failed:
        new_report['failed_uploads'] = still_failed

    try:
        database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=dashboard_id, report=new_report)
    except Exception:
        pass

    return {"retried_count": retried, "remaining_failed": len(still_failed), "still_failed": still_failed}


# ------------------------
# WIZARD STEP FUNCTIONS
# ------------------------
def wizard_step_1():
    """Step 1: Technician Info & Industry Selection"""
    st.subheader("Technician Information")
    
    # Initialize wizard_data in session state if not exists
    if 'wizard_data' not in st.session_state:
        st.session_state.wizard_data = {}
    
    data = st.session_state.wizard_data
    
    # Technician fields
    full_name = st.text_input(
        "Full Name", 
        value=data.get('full_name', ''),
        key="wiz_full_name"
    )
    
    tech_id = st.text_input(
        "Tech ID", 
        value=data.get('tech_id', ''),
        key="wiz_tech_id"
    )
    
    district = st.text_input(
        "District", 
        value=data.get('district', ''),
        key="wiz_district"
    )

    referred_by = st.text_input(
        "Referred By",
        value=data.get('referred_by', ''),
        key="wiz_referred_by"
    )
    
    state_idx = 0
    saved_state = data.get('state')
    if saved_state and saved_state in US_STATES:
        state_idx = US_STATES.index(saved_state) + 1
    state = st.selectbox(
        "State", 
        [""] + US_STATES,
        index=state_idx,
        key="wiz_state"
    )
    
    # Industry selection
    st.subheader("Industry Selection")
    st.write("Select all industries that apply:")
    
    saved_industries = data.get('industry', data.get('industries', []))
    selected_industries = []
    
    cols = st.columns(4)
    for idx, industry in enumerate(INDUSTRIES):
        with cols[idx % 4]:
            checked = st.checkbox(
                industry, 
                value=industry in saved_industries,
                key=f"wiz_industry_{industry}"
            )
            if checked:
                selected_industries.append(industry)
    
    # Navigation
    st.markdown("---")
    
    # Validation
    errors = []
    if not full_name:
        errors.append("Full Name is required")
    if not tech_id:
        errors.append("Tech ID is required")
    if not district:
        errors.append("District is required")
    if not state:
        errors.append("State selection is required")
    
    if errors:
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in errors))
    
    if st.button("Next ➡", disabled=bool(errors), type="primary", width='stretch'):
        # Save to session state
        st.session_state.wizard_data.update({
            'full_name': full_name,
            'tech_id': tech_id,
            'district': district,
            'state': state,
            'referred_by': referred_by,
            'industry': selected_industries,
            'industries': selected_industries
        })
        st.session_state.wizard_step = 2
        st.rerun()


def wizard_step_2():
    """Step 2: Vehicle Info & Documents"""
    st.subheader("Vehicle Information & Documents")
    
    data = st.session_state.wizard_data
    
    # VIN Section
    st.markdown("### Vehicle Identification")
    
    vin = st.text_input(
        "VIN (Vehicle Identification Number)", 
        value=data.get('vin', ''),
        key="wiz_vin"
    )
    
    decode_clicked = st.button("Decode VIN (lookup year/make/model)")
    
    if decode_clicked:
        vin_value = st.session_state.get("wiz_vin", "").strip()
        if not vin_value:
            st.warning("Enter a VIN above before decoding.")
        else:
            with st.spinner("Decoding VIN..."):
                decoded = decode_vin(vin_value)
                if decoded:
                    st.session_state.wizard_data['year'] = decoded.get("year", "")
                    st.session_state.wizard_data['make'] = decoded.get("make", "")
                    st.session_state.wizard_data['model'] = decoded.get("model", "")
                    st.success(
                        f"Decoded VIN: {decoded.get('year', '?')} "
                        f"{decoded.get('make', '?')} "
                        f"{decoded.get('model', '?')}"
                    )
                    st.rerun()
                else:
                    st.error("Could not decode VIN from the NHTSA API. Check the VIN and try again.")
    
        # Sync decoded values to session state keys if they exist
    if 'year' in data and 'wiz_year' not in st.session_state:
        st.session_state.wiz_year = data['year']
    if 'make' in data and 'wiz_make' not in st.session_state:
        st.session_state.wiz_make = data['make']
    if 'model' in data and 'wiz_model' not in st.session_state:
        st.session_state.wiz_model = data['model']
    
    col1, col2, col3 = st.columns(3)
    with col1:
        year = st.text_input(
            "Vehicle Year", 
            key="wiz_year"
        )
    with col2:
        make = st.text_input(
            "Vehicle Make", 
            key="wiz_make"
        )
    with col3:
        model = st.text_input(
            "Vehicle Model", 
            key="wiz_model"
        )
    
    st.markdown("---")
    
    # Vehicle Photos
    st.markdown("### Vehicle Photos")
    st.caption("Upload 4 photos minimum: Front, Back, Left Side, Right Side")
    
    vehicle_photos = st.file_uploader(
        "Vehicle Photos",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="wiz_vehicle_photos",
        label_visibility="collapsed"
    )
    
    if vehicle_photos:
        if len(vehicle_photos) >= 4:
            st.success(f"✓ {len(vehicle_photos)} vehicle photos uploaded")
        else:
            st.warning(f"⚠ {len(vehicle_photos)} uploaded - need at least 4 vehicle photos")
    else:
        st.warning("⚠ No vehicle photos uploaded yet")
    
    st.markdown("---")
    
    # Registration
    st.markdown("### Registration")
    col1, col2 = st.columns(2)
    with col1:
        registration_exp_default = data.get('registration_exp')
        if isinstance(registration_exp_default, str):
            try:
                parsed_date = datetime.strptime(registration_exp_default, "%Y-%m-%d").date()
                registration_exp_default = parsed_date.strftime("%m/%d/%Y")
            except Exception:
                registration_exp_default = ""
        elif registration_exp_default:
            registration_exp_default = registration_exp_default.strftime("%m/%d/%Y")
        else:
            registration_exp_default = ""
        registration_exp_str = st.text_input(
            "Registration Expiration Date (MM/DD/YYYY)",
            value=registration_exp_default,
            placeholder="MM/DD/YYYY",
            key="wiz_registration_exp"
        )
        registration_exp = None
        if registration_exp_str:
            try:
                registration_exp = datetime.strptime(registration_exp_str, "%m/%d/%Y").date()
            except ValueError:
                st.error("Please enter date in MM/DD/YYYY format")
    
    with col2:
        registration_docs = st.file_uploader(
            "Registration Photo/Document",
            accept_multiple_files=True,
            type=["jpg", "jpeg", "png", "pdf"],
            key="wiz_registration_docs"
        )
        
        if registration_docs:
            st.success(f"✓ {len(registration_docs)} document(s) uploaded")
    
    st.markdown("---")
    
    # Insurance
    st.markdown("### Insurance")
    col1, col2 = st.columns(2)
    with col1:
        insurance_exp_default = data.get('insurance_exp')
        if isinstance(insurance_exp_default, str):
            try:
                parsed_date = datetime.strptime(insurance_exp_default, "%Y-%m-%d").date()
                insurance_exp_default = parsed_date.strftime("%m/%d/%Y")
            except Exception:
                insurance_exp_default = ""
        elif insurance_exp_default:
            insurance_exp_default = insurance_exp_default.strftime("%m/%d/%Y")
        else:
            insurance_exp_default = ""
        insurance_exp_str = st.text_input(
            "Insurance Expiration Date (MM/DD/YYYY)",
            value=insurance_exp_default,
            placeholder="MM/DD/YYYY",
            key="wiz_insurance_exp"
        )
        insurance_exp = None
        if insurance_exp_str:
            try:
                insurance_exp = datetime.strptime(insurance_exp_str, "%m/%d/%Y").date()
            except ValueError:
                st.error("Please enter date in MM/DD/YYYY format")
    
    with col2:
        insurance_docs = st.file_uploader(
            "Insurance Photo/Document",
            accept_multiple_files=True,
            type=["jpg", "jpeg", "png", "pdf"],
            key="wiz_insurance_docs"
        )
        
        if insurance_docs:
            st.success(f"✓ {len(insurance_docs)} document(s) uploaded")
    
    # Navigation
    st.markdown("---")
    
    # Validation
    errors = []
    if not vin:
        errors.append("VIN is required")
    if not year or not make or not model:
        errors.append("Vehicle Year, Make, and Model are required")
    if not vehicle_photos or len(vehicle_photos) < 4:
        errors.append("At least 4 vehicle photos are required")
    if not registration_docs:
        errors.append("Registration document is required")
    if not registration_exp:
        errors.append("Registration expiration date is required")
    if not insurance_docs:
        errors.append("Insurance document is required")
    if not insurance_exp:
        errors.append("Insurance expiration date is required")
    
    can_proceed = len(errors) == 0
    
    if errors:
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in errors))
    
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("⬅ Back", width='stretch'):
            st.session_state.wizard_step = 1
            st.rerun()
    
    with col_nav2:
        if st.button("Next ➡", disabled=not can_proceed, type="primary", width='stretch'):
            # Save to session state
            st.session_state.wizard_data.update({
                'vin': vin,
                'year': year,
                'make': make,
                'model': model,
                'vehicle_photos': vehicle_photos,
                'registration_exp': registration_exp,
                'registration_docs': registration_docs,
                'insurance_exp': insurance_exp,
                'insurance_docs': insurance_docs
            })
            st.session_state.wizard_step = 3
            st.rerun()


def wizard_step_3():
    """Step 3: BYOV Policy & Signature"""
    st.subheader("BYOV Policy Agreement")
    
    data = st.session_state.wizard_data
    
    # Determine template based on state
    state = data.get('state', '')
    state_abbrev = state[:2].upper() if len(state) > 2 else state.upper()
    template_file = STATE_TEMPLATE_MAP.get(state_abbrev, DEFAULT_TEMPLATE)
    
    # Check if California - requires DocuSign instead of in-app signature
    is_california = state_abbrev == "CA"
    
    if is_california:
        st.info(f"📄 BYOV Policy for {state}")
        st.markdown("""
        <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 15px 0; border-radius: 4px;">
            <h4 style="color: #856404; margin: 0 0 10px 0;">📝 California Signature Requirement</h4>
            <p style="color: #856404; margin: 0;">
                California state regulations require a compliant electronic signature via DocuSign. 
                After you submit your enrollment, HR will text a DocuSign link to your work phone 
                for you to complete the signature process.
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info(f"📄 BYOV Policy for {state}")
    
    # PDF Download Section
    if os.path.exists(template_file):
        with open(template_file, "rb") as f:
            template_bytes = f.read()
        
        st.download_button(
            label="📥 Download BYOV Policy (Required)",
            data=template_bytes,
            file_name="BYOV_Policy.pdf",
            mime="application/pdf",
            help="Download and review this document before signing below",
            width='stretch'
        )
    else:
        st.error(f"⚠ Template file '{template_file}' not found. Please contact administrator.")
        st.stop()
    
    st.markdown("---")
    
    # Policy Acknowledgement
    st.markdown("### Policy Acknowledgement")
    
    st.markdown("""
    I confirm that I have opened and fully reviewed the BYOV Policy, including the mileage 
    reimbursement rules and current reimbursement rates. I understand that the first 35 minutes 
    of my morning commute and the first 35 minutes of my afternoon commute are not eligible for 
    reimbursement and must not be included when entering mileage.
    """)
    
    acknowledged = st.checkbox(
        "I acknowledge and agree to the terms stated above",
        value=data.get('acknowledged', False),
        key="wiz_acknowledged"
    )
    
    # Signature section - different for California vs other states
    signature_drawn = False
    canvas_result_data = None
    
    if is_california:
        # California - DocuSign notice, no in-app signature required
        if acknowledged:
            st.markdown("---")
            st.markdown("### Signature via DocuSign")
            st.success("""
            ✓ **Your signature will be collected via DocuSign**
            
            After you submit your enrollment, you will receive a text message on your work phone 
            with a link to sign the BYOV Policy Form electronically via DocuSign.
            """)
            signature_drawn = True  # Allow proceeding without in-app signature
            st.session_state.wizard_data['is_california_docusign'] = True
    else:
        # Non-California - standard in-app signature
        if acknowledged:
            st.markdown("---")
            st.markdown("### Signature")
            
            st.write("Please sign below:")
            
            # Signature canvas
            canvas_result = st_canvas(
                fill_color="rgba(255, 255, 255, 0)",
                stroke_width=2,
                stroke_color="#000000",
                background_color="#FFFFFF",
                height=200,
                width=600,
                drawing_mode="freedraw",
                key="wiz_signature_canvas",
            )
            
            canvas_result_data = canvas_result
            
            # Check if signature is drawn
            if canvas_result_data and canvas_result_data.image_data is not None:
                import numpy as np
                img_array = np.array(canvas_result_data.image_data)
                if img_array[:, :, 3].max() > 0:
                    signature_drawn = True
                    st.success("✓ Signature captured")
                else:
                    st.info("Please sign in the box above")
        else:
            st.info("Please check the acknowledgement box above to reveal the signature box.")
    
    # Additional Comments
    st.markdown("---")
    comment = st.text_area(
        "Additional Comments (100 characters max)",
        value=data.get('comment', ''),
        max_chars=100,
        key="wiz_comment"
    )
    
    # Navigation
    st.markdown("---")
    
    # Validation
    can_proceed = acknowledged and signature_drawn
    
    if not can_proceed:
        errors = []
        if not acknowledged:
            errors.append("Please acknowledge the policy terms")
        if not signature_drawn and not is_california:
            errors.append("Please provide your signature")
        
        if errors:
            st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in errors))
    
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("⬅ Back", width='stretch'):
            st.session_state.wizard_step = 2
            st.rerun()
    
    with col_nav2:
        if st.button("Next ➡", disabled=not can_proceed, type="primary", width='stretch'):
            # Save signature and other data to session state
            st.session_state.wizard_data.update({
                'acknowledged': acknowledged,
                'template_file': template_file,
                'comment': comment,
                'is_california_docusign': is_california
            })
            
            if canvas_result_data and canvas_result_data.image_data is not None:
                st.session_state.wizard_data['signature_image'] = canvas_result_data.image_data
            
            st.session_state.wizard_step = 4
            st.rerun()


def wizard_step_4():
    """Step 4: Review & Submit"""
    st.subheader("Review Your Enrollment")
    
    data = st.session_state.wizard_data
    
    st.write("Please review all information before submitting. Use the Back button if you need to make changes.")
    
    # Technician Info
    st.markdown("---")
    with st.container():
        st.markdown("#### 👤 Technician Information")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Full Name:** {data.get('full_name', 'N/A')}")
            st.write(f"**Tech ID:** {data.get('tech_id', 'N/A')}")
        with col2:
            st.write(f"**District:** {data.get('district', 'N/A')}")
            st.write(f"**State:** {data.get('state', 'N/A')}")
            st.write(f"**Referred By:** {data.get('referred_by', 'N/A')}")
    
    # Industries
    st.markdown("---")
    with st.container():
        st.markdown("#### 🏭 Industries Selected")
        industries = data.get('industry', data.get('industries', []))
        if industries:
            st.write(", ".join(industries))
        else:
            st.write("None selected")
    
    # Vehicle Info
    st.markdown("---")
    with st.container():
        st.markdown("#### 🚗 Vehicle Information")
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**VIN:** {data.get('vin', 'N/A')}")
            st.write(f"**Year:** {data.get('year', 'N/A')}")
        with col2:
            st.write(f"**Make:** {data.get('make', 'N/A')}")
            st.write(f"**Model:** {data.get('model', 'N/A')}")
    
    # Documents
    st.markdown("---")
    with st.container():
        st.markdown("#### 📎 Documents Uploaded")
        col1, col2, col3 = st.columns(3)
        with col1:
            vehicle_count = len(data.get('vehicle_photos', []))
            st.success(f"✓ {vehicle_count} Vehicle Photos")
        with col2:
            insurance_count = len(data.get('insurance_docs', []))
            st.success(f"✓ {insurance_count} Insurance Doc(s)")
        with col3:
            registration_count = len(data.get('registration_docs', []))
            st.success(f"✓ {registration_count} Registration Doc(s)")
    
    # Expiration Dates
    st.markdown("---")
    with st.container():
        st.markdown("#### 📅 Expiration Dates")
        col1, col2 = st.columns(2)
        
        def format_date_display(date_str):
            """Convert YYYY-MM-DD to MM/DD/YYYY for display"""
            if not date_str or date_str == 'N/A':
                return 'N/A'
            try:
                from datetime import datetime
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.strftime("%m/%d/%Y")
            except:
                return date_str
        
        with col1:
            st.write(f"**Insurance Expires:** {format_date_display(data.get('insurance_exp', 'N/A'))}")
        with col2:
            st.write(f"**Registration Expires:** {format_date_display(data.get('registration_exp', 'N/A'))}")
    
    # Policy Status
    st.markdown("---")
    with st.container():
        st.markdown("#### 📝 BYOV Policy")
        if data.get('acknowledged'):
            st.success("✓ Policy Acknowledged")
        if data.get('is_california_docusign'):
            st.info("📱 Signature will be collected via DocuSign (California)")
        elif data.get('signature_image') is not None:
            st.success("✓ Signature Provided")
    
    # Comments
    if data.get('comment'):
        st.markdown("---")
        with st.container():
            st.markdown("#### 💬 Additional Comments")
            st.write(data.get('comment'))
    
    # Navigation & Submit
    st.markdown("---")
    
    col_nav1, col_nav2 = st.columns([1, 1])
    with col_nav1:
        if st.button("⬅ Go Back", width='stretch'):
            st.session_state.wizard_step = 3
            st.rerun()
    
    with col_nav2:
        submit_clicked = st.button("✅ Submit Enrollment", type="primary", width='stretch')
    
    if submit_clicked:
        with st.spinner("Processing enrollment..."):
            try:
                # Generate unique ID
                record_id = str(uuid.uuid4())
                
                # Determine if this is a California enrollment (DocuSign workflow)
                is_california_docusign = data.get('is_california_docusign', False)
                
                # Create upload folders
                upload_base = create_upload_folder(data['tech_id'], record_id)
                
                # Save vehicle photos
                vehicle_folder = os.path.join(upload_base, "vehicle")
                vehicle_paths = save_uploaded_files(data['vehicle_photos'], vehicle_folder, "vehicle")
                
                # Save insurance documents
                insurance_folder = os.path.join(upload_base, "insurance")
                insurance_paths = save_uploaded_files(data['insurance_docs'], insurance_folder, "insurance")
                
                # Save registration documents
                registration_folder = os.path.join(upload_base, "registration")
                registration_paths = save_uploaded_files(data['registration_docs'], registration_folder, "registration")
                
                # PDF Generation - differs for California vs other states
                pdf_output_path = None
                pdf_success = True
                
                if is_california_docusign:
                    # California - Skip PDF generation, DocuSign will be handled by HR
                    pdf_output_path = None
                else:
                    # Non-California - Generate signed PDF with in-app signature
                    signature_img = None
                    if data.get('signature_image') is not None:
                        signature_img = Image.fromarray(data['signature_image'].astype('uint8'), 'RGBA')
                    
                    pdf_filename = f"{sanitize_filename(data['tech_id'])}_{record_id}.pdf"
                    pdf_output_path = os.path.join("pdfs", pdf_filename)
                    
                    # Signature positions extracted from user's marked-up PDF
                    sig_x = 73
                    sig_y = 442
                    date_x = 320
                    date_y = 442
                    name_x = 261
                    name_y = 547
                    tech_id_x = 264
                    tech_id_y = 534
                    sig_width = 160
                    sig_height = 28
                    
                    pdf_success = generate_signed_pdf(
                        data['template_file'],
                        signature_img,
                        pdf_output_path,
                        sig_x=sig_x,
                        sig_y=sig_y,
                        date_x=date_x,
                        date_y=date_y,
                        employee_name=data.get('full_name', ''),
                        tech_id=data.get('tech_id', ''),
                        name_x=name_x,
                        name_y=name_y,
                        tech_id_x=tech_id_x,
                        tech_id_y=tech_id_y,
                        sig_width=sig_width,
                        sig_height=sig_height
                    )
                
                if not pdf_success and not is_california_docusign:
                    st.error("❌ PDF generation failed. Cannot submit enrollment. Please try again.")
                    return
                
                # Create enrollment record in the database
                db_record = {
                    "full_name": data['full_name'],
                    "tech_id": data['tech_id'],
                    "district": data['district'],
                    "state": data['state'],
                    "referred_by": data.get('referred_by', ''),
                    # Store both new 'industry' and legacy 'industries' for compatibility
                    "industry": data.get('industry', data.get('industries', [])),
                    "industries": data.get('industries', data.get('industry', [])),
                    "year": data['year'],
                    "make": data['make'],
                    "model": data['model'],
                    "vin": data['vin'],
                    "insurance_exp": str(data['insurance_exp']),
                    "registration_exp": str(data['registration_exp']),
                    "template_used": data['template_file'],
                    "comment": data.get('comment', ''),
                    "submission_date": datetime.now().isoformat()
                }

                # Check for existing enrollment by tech_id or VIN to avoid duplicates
                existing = None
                try:
                    for e in database.get_all_enrollments():
                        if str(e.get('tech_id', '')).strip() and e.get('tech_id') == db_record.get('tech_id'):
                            existing = e
                            break
                        if db_record.get('vin') and e.get('vin') and e.get('vin') == db_record.get('vin'):
                            existing = e
                            break
                except Exception:
                    existing = None

                if existing:
                    # Update the existing enrollment instead of inserting a duplicate
                    enrollment_db_id = existing.get('id')
                    try:
                        database.update_enrollment(enrollment_db_id, db_record)
                        clear_enrollment_cache()
                    except Exception:
                        # If update fails, fallback to insert
                        enrollment_db_id = database.insert_enrollment(db_record)
                        clear_enrollment_cache()

                    # Add documents but avoid duplicates by file path
                    try:
                        existing_docs = database.get_documents_for_enrollment(enrollment_db_id)
                        existing_paths = {d.get('file_path') for d in existing_docs}
                    except Exception:
                        existing_paths = set()

                    for p in vehicle_paths:
                        if p not in existing_paths:
                            database.add_document(enrollment_db_id, 'vehicle', p)
                    for p in insurance_paths:
                        if p not in existing_paths:
                            database.add_document(enrollment_db_id, 'insurance', p)
                    for p in registration_paths:
                        if p not in existing_paths:
                            database.add_document(enrollment_db_id, 'registration', p)
                    if pdf_output_path and pdf_output_path not in existing_paths:
                        database.add_document(enrollment_db_id, 'signature', pdf_output_path)

                    created_new = False
                else:
                    # No existing record — insert new enrollment
                    enrollment_db_id = database.insert_enrollment(db_record)
                    clear_enrollment_cache()

                    # Store documents in DB and keep the filepaths for notification
                    for p in vehicle_paths:
                        database.add_document(enrollment_db_id, 'vehicle', p)
                    for p in insurance_paths:
                        database.add_document(enrollment_db_id, 'insurance', p)
                    for p in registration_paths:
                        database.add_document(enrollment_db_id, 'registration', p)
                    # signed PDF (only for non-California enrollments)
                    if pdf_output_path:
                        database.add_document(enrollment_db_id, 'signature', pdf_output_path)

                    # Create checklist for new enrollment
                    try:
                        database.create_checklist_for_enrollment(enrollment_db_id)
                    except Exception as e:
                        logging.warning(f"Could not create checklist: {e}")

                    created_new = True

                # Build application-level record for notifications and UI
                record = {
                    "id": enrollment_db_id,
                    "tech_id": data['tech_id'],
                    "full_name": data['full_name'],
                    "referred_by": data.get('referred_by', ''),
                    "district": data['district'],
                    "state": data['state'],
                    "industry": data.get('industry', data.get('industries', [])),
                    "industries": data.get('industries', data.get('industry', [])),
                    "vin": data['vin'],
                    "year": data['year'],
                    "make": data['make'],
                    "model": data['model'],
                    "insurance_exp": str(data['insurance_exp']),
                    "registration_exp": str(data['registration_exp']),
                    "status": "Active" if not is_california_docusign else "Pending DocuSign",
                    "comment": data.get('comment', ''),
                    "template_used": data['template_file'],
                    "signature_pdf_path": pdf_output_path,
                    "vehicle_photos_paths": vehicle_paths,
                    "insurance_docs_paths": insurance_paths,
                    "registration_docs_paths": registration_paths,
                    "submission_date": datetime.now().isoformat(),
                    "is_california_docusign": is_california_docusign
                }

                # For California enrollments, send DocuSign request to HR
                docusign_email_sent = False
                if is_california_docusign:
                    try:
                        docusign_email_sent = send_docusign_request_hr(record, enrollment_db_id)
                    except Exception as e:
                        logging.warning(f"DocuSign HR email failed: {e}")
                        docusign_email_sent = False

                # Send submission notification using configured settings
                email_sent = False
                try:
                    notification_settings = database.get_notification_settings()
                    if notification_settings:
                        submission_cfg = notification_settings.get('submission', {})
                    else:
                        submission_cfg = {
                            'enabled': True,
                            'recipients': 'tyler.morgan@transformco.com, carl.oneill@transformco.com',
                            'subject_template': 'New BYOV Enrollment: {full_name} (Tech ID: {tech_id})'
                        }
                    
                    if submission_cfg.get('enabled') and submission_cfg.get('recipients'):
                        subject_template = submission_cfg.get('subject_template', 'New BYOV Enrollment: {full_name} (Tech ID: {tech_id})')
                        subject = subject_template.format(
                            full_name=record.get('full_name', 'Unknown'),
                            tech_id=record.get('tech_id', 'N/A'),
                            district=record.get('district', 'N/A'),
                            state=record.get('state', 'N/A'),
                            year=record.get('year', ''),
                            make=record.get('make', ''),
                            model=record.get('model', '')
                        )
                        email_sent = send_email_notification(record, recipients=submission_cfg['recipients'], subject=subject)
                except Exception as e:
                    logging.warning(f"Submission notification failed: {e}")
                    email_sent = False
                
                if is_california_docusign:
                    if docusign_email_sent:
                        banner_msg = "✅ Enrollment submitted! HR has been notified to send you the DocuSign link."
                    else:
                        banner_msg = "✅ Enrollment saved! HR will contact you for DocuSign signature."
                elif email_sent:
                    banner_msg = "✅ Enrollment submitted successfully and email notification sent!"
                else:
                    banner_msg = "✅ Enrollment saved, but email notification failed. Administrator has been notified."

                # NOTE: Dashboard sync is now handled by admin approval in admin_dashboard.py
                # No automatic sync on submission - admin must review and approve first
                
                # Clear wizard data
                st.session_state.wizard_data = {}
                st.session_state.wizard_step = 1

                show_money_rain()

                # Show success message and banner
                st.markdown("---")
                
                if is_california_docusign:
                    # California-specific success message with DocuSign instructions
                    st.markdown("""
                    <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 15px; margin: 20px 0;">
                        <h2 style="color: #2e7d32; margin-bottom: 15px;">🎉 Almost There!</h2>
                        <p style="font-size: 1.3em; color: #1b5e20; margin-bottom: 10px;">
                            <strong>Your enrollment has been submitted!</strong>
                        </p>
                        <p style="font-size: 1.1em; color: #388e3c; margin-top: 20px;">
                            📱 <strong>Next Step:</strong> You will receive a text message on your work phone 
                            with a DocuSign link to complete your signature electronically.
                        </p>
                        <p style="font-size: 1em; color: #666; margin-top: 15px;">
                            California state regulations require DocuSign for compliant electronic signatures.
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 15px; margin: 20px 0;">
                        <h2 style="color: #2e7d32; margin-bottom: 15px;">🎉 Awesome!</h2>
                        <p style="font-size: 1.3em; color: #1b5e20; margin-bottom: 10px;">
                            <strong>You are one step closer to transportation freedom!</strong>
                        </p>
                        <p style="font-size: 1.1em; color: #388e3c; margin-top: 20px;">
                            Keep an eye out for communication from one of our BYOV team members to confirm your enrollment.
                        </p>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    if st.button("🏠 Return to Home Page", type="primary", use_container_width=True):
                        st.markdown('<meta http-equiv="refresh" content="0; url=/">', unsafe_allow_html=True)
                
            except Exception as e:
                import traceback
                st.error(f"❌ Error processing enrollment: {str(e)}")
                st.error(f"Details: {traceback.format_exc()}")


# ------------------------
# DOCUSIGN CONFIRMATION PAGE
# ------------------------
def render_docusign_confirmation_page(token: str):
    """Render the DocuSign confirmation page for HR to mark signatures as complete."""
    st.set_page_config(page_title="DocuSign Confirmation", page_icon="✍️", layout="centered")
    
    # Center the content
    st.markdown("""
        <style>
        [data-testid="stMainBlockContainer"] {
            max-width: 600px;
            margin: 0 auto;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Logo
    logo_path = "static/sears_logo_brand.png"
    if os.path.exists(logo_path):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(logo_path, width=250)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    if not token:
        st.error("No confirmation token provided. This link may be invalid.")
        return
    
    # Try to confirm the token
    try:
        result = database.confirm_docusign_token(token)
        
        if result.get('success'):
            st.markdown("""
            <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 15px; margin: 20px 0;">
                <h2 style="color: #2e7d32; margin-bottom: 15px;">✅ DocuSign Confirmed!</h2>
                <p style="font-size: 1.2em; color: #1b5e20; margin-bottom: 10px;">
                    Thank you for confirming the DocuSign completion.
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            st.info(f"""
            **Technician:** {result.get('tech_name', 'N/A')}  
            **Tech ID:** {result.get('tech_id', 'N/A')}
            
            The enrollment checklist has been automatically updated to mark "Signed Policy Form Sent to HSHRpaperwork" as complete.
            """)
            
        elif result.get('already_confirmed'):
            st.warning("""
            This DocuSign has already been confirmed.
            
            No further action is needed.
            """)
        else:
            st.error(f"Error: {result.get('error', 'Unknown error occurred')}")
            
    except Exception as e:
        st.error(f"An error occurred while processing the confirmation: {str(e)}")
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: #666; font-size: 0.9em;'>BYOV Enrollment System - Sears Home Services</p>", unsafe_allow_html=True)


# ------------------------
# NEW ENROLLMENT PAGE
# ------------------------
def page_new_enrollment():
    """Main enrollment page with wizard navigation"""
    
    # Initialize wizard step if not exists
    if 'wizard_step' not in st.session_state:
        st.session_state.wizard_step = 1
    
    # Progress indicator
    current_step = st.session_state.wizard_step
    
    # Progress bar with styled pills
    progress_cols = st.columns(4)
    step_labels = [
        "Technician Info",
        "Vehicle & Docs",
        "Policy & Signature",
        "Review & Submit"
    ]
    
    for idx, (col, label) in enumerate(zip(progress_cols, step_labels), 1):
        with col:
            if idx < current_step:
                cls = "byov-progress-label completed"
                symbol = "✓"
            elif idx == current_step:
                cls = "byov-progress-label active"
                symbol = "●"
            else:
                cls = "byov-progress-label pending"
                symbol = "○"
            
            st.markdown(
                f"<div class='{cls}'>{symbol} {label}</div>",
                unsafe_allow_html=True
            )
    
    # Small spacer instead of a hard rule
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Step-specific header text (purely visual, does not affect logic)
    step_titles = {
        1: ("Technician Information", "Tell us who you are and where you work."),
        2: ("Vehicle & Documents", "Add your vehicle details and upload required docs."),
        3: ("Policy & Signature", "Review the BYOV policy and sign electronically."),
        4: ("Review & Submit", "Double-check everything before you submit.")
    }
    title, subtitle = step_titles.get(current_step, ("BYOV Enrollment", ""))
    
    # Render step header (shell styling applied via container)
    st.markdown(
        f"""
        <div class="byov-step-header">
            <div>
                <div class="byov-step-title">{title}</div>
                <div class="byov-step-sub">{subtitle}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Render step content inside a styled container
    with st.container():
        if current_step == 1:
            wizard_step_1()
        elif current_step == 2:
            wizard_step_2()
        elif current_step == 3:
            wizard_step_3()
        elif current_step == 4:
            wizard_step_4()
        else:
            st.error("Invalid wizard step")
            st.session_state.wizard_step = 1
            st.rerun()


# OLD PAGE - REMOVE EVERYTHING BELOW UNTIL ADMIN DASHBOARD
def page_new_enrollment_OLD():
    st.title("BYOV Vehicle Enrollment")
    st.caption("Submit your vehicle information for the Bring Your Own Vehicle program.")

    st.subheader("Technician & Vehicle Information")

    col1, col2 = st.columns(2)

    # Left column: tech info
    with col1:
        tech_id = st.text_input("Technician ID")
        full_name = st.text_input("Full Name")
        district = st.text_input("District Number")
        state = st.selectbox("State", [""] + US_STATES)

    # Right column: VIN + vehicle info
    with col2:
        vin = st.text_input("VIN (Vehicle Identification Number)", key="vin")

        decode_clicked = st.button("Decode VIN (lookup year/make/model)")

        if decode_clicked:
            vin_value = st.session_state.get("vin", "").strip()
            if not vin_value:
                st.warning("Enter a VIN above before decoding.")
            else:
                decoded = decode_vin(vin_value)
                if decoded:
                    # Pre-fill vehicle fields before they are instantiated
                    st.session_state["vehicle_year"] = decoded.get("year", "")
                    st.session_state["vehicle_make"] = decoded.get("make", "")
                    st.session_state["vehicle_model"] = decoded.get("model", "")
                    st.info(
                        f"Decoded VIN: {decoded.get('year', '?')} "
                        f"{decoded.get('make', '?')} "
                        f"{decoded.get('model', '?')}"
                    )
                else:
                    st.warning("Could not decode VIN from the NHTSA API. Check the VIN and try again.")

        year = st.text_input(
            "Vehicle Year",
            key="vehicle_year",
        )
        make = st.text_input(
            "Vehicle Make",
            key="vehicle_make",
        )
        model = st.text_input(
            "Vehicle Model",
            key="vehicle_model",
        )

    # Industry selection
    st.subheader("Industry Selection")
    st.write("Select all industries that apply:")
    
    industries = []
    cols = st.columns(4)
    for idx, industry in enumerate(INDUSTRIES):
        with cols[idx % 4]:
            if st.checkbox(industry, key=f"industry_{industry}"):
                industries.append(industry)

    st.subheader("Expiration Dates")
    col3, col4 = st.columns(2)
    with col3:
        insurance_exp_str = st.text_input(
            "Insurance Expiration Date (MM/DD/YYYY)",
            placeholder="MM/DD/YYYY",
            key="admin_insurance_exp"
        )
        insurance_exp = None
        if insurance_exp_str:
            try:
                insurance_exp = datetime.strptime(insurance_exp_str, "%m/%d/%Y").date()
            except ValueError:
                st.error("Please enter date in MM/DD/YYYY format")
    with col4:
        registration_exp_str = st.text_input(
            "Registration Expiration Date (MM/DD/YYYY)",
            placeholder="MM/DD/YYYY",
            key="admin_registration_exp"
        )
        registration_exp = None
        if registration_exp_str:
            try:
                registration_exp = datetime.strptime(registration_exp_str, "%m/%d/%Y").date()
            except ValueError:
                st.error("Please enter date in MM/DD/YYYY format")
    
    comment = st.text_area("Additional Comments (100 characters max)", max_chars=100)
    
    # PDF Template download and signature section (MOVED BEFORE FILE UPLOADS)
    st.markdown("---")
    st.subheader("BYOV Program Agreement")
    
    # Determine which template to use
    template_file = DEFAULT_TEMPLATE
    if state:
        # Get state abbreviation
        state_abbrev = state[:2].upper()
        template_file = STATE_TEMPLATE_MAP.get(state_abbrev, DEFAULT_TEMPLATE)
    
    st.info(f"📄 Template for your state: **{template_file}**")
    
    # Download template button
    if os.path.exists(template_file):
        with open(template_file, "rb") as f:
            template_bytes = f.read()
        
        st.download_button(
            label="📥 Download BYOV Agreement Template (Required)",
            data=template_bytes,
            file_name=template_file,
            mime="application/pdf",
            help="Download and review this document before signing below"
        )
        
        # Track if user downloaded template
        if 'template_downloaded' not in st.session_state:
            st.session_state.template_downloaded = False
        
        if st.button("I have reviewed the template"):
            st.session_state.template_downloaded = True
            st.rerun()
    else:
        st.error(f"⚠ Template file '{template_file}' not found. Please contact administrator.")
    
    # Show acknowledgement and signature section after template review
    signature_drawn = False
    canvas_result_data = None
    
    if st.session_state.get('template_downloaded', False):
        st.markdown("---")
        st.subheader("Acknowledgement")
        
        st.markdown("""
        **ACKNOWLEDGEMENT**
        
        I confirm that I have opened and fully reviewed the BYOV Policy, including the mileage 
        reimbursement rules and current reimbursement rates. I understand that the first 35 minutes 
        of my morning commute and the first 35 minutes of my afternoon commute are not eligible for 
        reimbursement and must not be included when entering mileage.
        """)
        
        # Checkbox to confirm acknowledgement
        acknowledged = st.checkbox(
            "I acknowledge and agree to the terms stated above",
            key="acknowledgement_checkbox"
        )
        
        # Show signature section only after acknowledgement is checked
        if acknowledged:
            st.markdown("---")
            st.subheader("Signature")
            
            st.write("Please sign below:")
            
            # Signature canvas
            canvas_result = st_canvas(
                fill_color="rgba(255, 255, 255, 0)",  # Transparent
                stroke_width=2,
                stroke_color="#000000",  # Black stroke color
                background_color="#FFFFFF",  # White background
                height=200,
                width=600,
                drawing_mode="freedraw",
                key="signature_canvas",
            )
            
            # Check if signature is drawn
            canvas_result_data = canvas_result
            if canvas_result_data.image_data is not None:
                # Check if there's any non-white pixel
                import numpy as np
                img_array = np.array(canvas_result_data.image_data)
                if img_array[:, :, 3].max() > 0:  # Check alpha channel
                    signature_drawn = True
            
            if signature_drawn:
                st.success("✓ Signature captured")
            else:
                st.info("Please sign in the box above")
        else:
            st.info("Please check the acknowledgement box above to proceed with signature.")
    
    # File uploads section (MOVED AFTER SIGNATURE)
    st.markdown("---")
    st.subheader("Document Uploads")
    
    st.info("📸 Please upload clear, legible photos/documents. Accepted formats: JPG, JPEG, PNG, PDF")
    
    # Vehicle photos
    vehicle_photos = st.file_uploader(
        "Vehicle Photos (Front, Back, Left Side, Right Side - minimum 4 required)",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="vehicle_photos"
    )
    
    if vehicle_photos:
        if len(vehicle_photos) >= 4:
            st.success(f"✓ {len(vehicle_photos)} vehicle photos uploaded")
        else:
            st.warning(f"⚠ {len(vehicle_photos)} uploaded - need at least 4 vehicle photos")
    else:
        st.warning("⚠ No vehicle photos uploaded yet")
    
    # Registration documents
    registration_docs = st.file_uploader(
        "Registration Document(s)",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="registration_docs"
    )
    
    if registration_docs:
        st.success(f"✓ {len(registration_docs)} registration document(s) uploaded")
    
    # Insurance documents
    insurance_docs = st.file_uploader(
        "Insurance Document(s)",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "pdf"],
        key="insurance_docs"
    )
    
    if insurance_docs:
        st.success(f"✓ {len(insurance_docs)} insurance document(s) uploaded")
    
    # Submit button
    st.markdown("---")
    
    # Validation checks
    can_submit = True
    validation_messages = []
    
    if not tech_id or not full_name or not vin:
        can_submit = False
        validation_messages.append("Technician ID, Full Name, and VIN are required")
    
    if not state:
        can_submit = False
        validation_messages.append("State selection is required")
    
    if not vehicle_photos or len(vehicle_photos) < 4:
        can_submit = False
        validation_messages.append("At least 4 vehicle photos are required")
    
    if not registration_docs:
        can_submit = False
        validation_messages.append("Registration document(s) required")
    if not registration_exp:
        can_submit = False
        validation_messages.append("Registration expiration date is required")
    
    if not insurance_docs:
        can_submit = False
        validation_messages.append("Insurance document(s) required")
    if not insurance_exp:
        can_submit = False
        validation_messages.append("Insurance expiration date is required")
    
    if not st.session_state.get('template_downloaded', False):
        can_submit = False
        validation_messages.append("Please download and review the BYOV agreement template")
    
    if not signature_drawn:
        can_submit = False
        validation_messages.append("Signature is required")
    
    # Show validation messages
    if validation_messages:
        st.warning("Please complete the following:\n" + "\n".join(f"• {msg}" for msg in validation_messages))
    
    submitted = st.button("Submit Enrollment", disabled=not can_submit, type="primary")

    if submitted:
        with st.spinner("Processing enrollment..."):
            try:
                # Generate unique ID
                record_id = str(uuid.uuid4())
                
                # Create upload folders
                upload_base = create_upload_folder(tech_id, record_id)
                
                # Save vehicle photos
                vehicle_folder = os.path.join(upload_base, "vehicle")
                vehicle_paths = save_uploaded_files(vehicle_photos, vehicle_folder, "vehicle")
                
                # Save registration documents
                registration_folder = os.path.join(upload_base, "registration")
                registration_paths = save_uploaded_files(registration_docs, registration_folder, "registration")
                
                # Save insurance documents
                insurance_folder = os.path.join(upload_base, "insurance")
                insurance_paths = save_uploaded_files(insurance_docs, insurance_folder, "insurance")
                
                # Generate signed PDF
                signature_img = None
                if canvas_result_data and canvas_result_data.image_data is not None:
                    signature_img = Image.fromarray(canvas_result_data.image_data.astype('uint8'), 'RGBA')
                
                pdf_filename = f"{sanitize_filename(tech_id)}_{record_id}.pdf"
                pdf_output_path = os.path.join("pdfs", pdf_filename)
                
                # Signature positions extracted from user's marked-up PDF
                sig_x = st.session_state.get('sig_x', 73)
                sig_y = st.session_state.get('sig_y', 442)
                date_x = st.session_state.get('date_x', 320)
                date_y = st.session_state.get('date_y', 442)
                name_x = st.session_state.get('name_x', 261)
                name_y = st.session_state.get('name_y', 547)
                tech_id_x = st.session_state.get('tech_id_x', 264)
                tech_id_y = st.session_state.get('tech_id_y', 534)
                sig_width = st.session_state.get('sig_width', 160)
                sig_height = st.session_state.get('sig_height', 28)
                
                pdf_success = generate_signed_pdf(
                    template_file, 
                    signature_img, 
                    pdf_output_path,
                    sig_x=sig_x,
                    sig_y=sig_y,
                    date_x=date_x,
                    date_y=date_y,
                    employee_name=full_name,
                    tech_id=tech_id,
                    name_x=name_x,
                    name_y=name_y,
                    tech_id_x=tech_id_x,
                    tech_id_y=tech_id_y,
                    sig_width=sig_width,
                    sig_height=sig_height
                )
                
                if not pdf_success:
                    st.error("❌ PDF generation failed. Cannot submit enrollment. Please try again.")
                    return
                
                # Create enrollment record
                records = load_enrollments()
                record = {
                    "id": record_id,
                    "tech_id": tech_id,
                    "full_name": full_name,
                    "district": district,
                    "state": state,
                    "industries": industries,
                    "vin": vin,
                    "year": year,
                    "make": make,
                    "model": model,
                    "insurance_exp": str(insurance_exp),
                    "registration_exp": str(registration_exp),
                    "status": "Active",
                    "comment": comment,
                    "template_used": template_file,
                    "signature_pdf_path": pdf_output_path,
                    "vehicle_photos_paths": vehicle_paths,
                    "insurance_docs_paths": insurance_paths,
                    "registration_docs_paths": registration_paths,
                    "submission_date": datetime.now().isoformat()
                }
                records.append(record)
                save_enrollments(records)
                
                # Send email notification
                ok = send_email_notification(record)
                
                if ok:
                    st.success("✅ Enrollment submitted successfully and email notification sent!")
                else:
                    st.warning("✅ Enrollment saved, but email notification failed. Administrator has been notified.")
                
                # Clear session state
                st.session_state.template_downloaded = False
                
                show_money_rain()
                
            except Exception as e:
                st.error(f"❌ Error processing enrollment: {str(e)}")
                st.exception(e)

# ------------------------
# FILE GALLERY MODAL
# ------------------------
def render_file_gallery_modal(original_row, selected_row, tech_id):
    """Render a modal-style file gallery with grid layout matching the screenshot"""
    
    # Modal styling CSS
    st.markdown("""
    <style>
    .file-gallery-modal {
        background: var(--background-color);
        border-radius: 8px;
        padding: 24px;
        margin-top: 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .file-gallery-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
        padding-bottom: 16px;
        border-bottom: 1px solid #e0e0e0;
    }
    .file-gallery-title {
        font-size: 20px;
        font-weight: 600;
        color: #1a1a1a;
    }
    .file-section {
        margin-bottom: 32px;
    }
    .file-section-title {
        font-size: 14px;
        font-weight: 600;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 16px;
    }
    .file-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin-bottom: 16px;
    }
    .file-card {
        background: #fafafa;
        border: 1px solid #e8e8e8;
        border-radius: 6px;
        padding: 12px;
        transition: all 0.2s ease;
        cursor: pointer;
        position: relative;
    }
    .file-card:hover {
        background: #f5f5f5;
        border-color: #d0d0d0;
        box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        transform: translateY(-1px);
    }
    .file-thumbnail {
        width: 100%;
        height: 120px;
        object-fit: cover;
        border-radius: 4px;
        margin-bottom: 8px;
        background: #e0e0e0;
    }
    .file-pdf-icon {
        width: 100%;
        height: 120px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 4px;
        margin-bottom: 8px;
        font-size: 48px;
        color: white;
    }
    .file-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
    }
    .file-name {
        font-size: 13px;
        font-weight: 500;
        color: #1a1a1a;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .file-meta {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .file-size {
        font-size: 12px;
        color: #666;
    }
    .file-tag {
        background: #e3f2fd;
        color: #1976d2;
        font-size: 11px;
        font-weight: 500;
        padding: 2px 8px;
        border-radius: 12px;
    }
    .action-buttons {
        display: flex;
        gap: 12px;
        margin-top: 24px;
        padding-top: 24px;
        border-top: 1px solid #e0e0e0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Modal container with close button
    col_header1, col_header2 = st.columns([4, 1])
    with col_header1:
        st.markdown(f"""
        <div class="file-gallery-modal">
            <div class="file-gallery-header">
                <div class="file-gallery-title">Files for {selected_row.get('Name', 'Unknown')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with col_header2:
        if st.button("✖ Close", key="close_modal_top", width='stretch'):
            if 'show_file_modal' in st.session_state:
                del st.session_state.show_file_modal
            st.rerun()
    
    # Collect all files with metadata
    def get_file_size(path):
        try:
            size_bytes = os.path.getsize(path)
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
        except:
            return "Unknown"
    
    def render_file_grid(files, category, icon="📎"):
        if not files:
            st.info(f"No {category.lower()} found")
            return
        
        st.markdown(f'<div class="file-section-title">{icon} {category}</div>', unsafe_allow_html=True)
        
        # Create grid layout using columns
        cols_per_row = 3
        for i in range(0, len(files), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, file_path in enumerate(files[i:i + cols_per_row]):
                if os.path.exists(file_path):
                    with cols[j]:
                        file_name = os.path.basename(file_path)
                        file_size = get_file_size(file_path)
                        file_ext = os.path.splitext(file_path)[1].lower()
                        
                        # Card container
                        with st.container():
                            st.markdown(f"""
                            <div class="file-card">
                            """, unsafe_allow_html=True)
                            
                            # Thumbnail or icon (optimized for small display)
                            if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                                try:
                                    # Load and create thumbnail to reduce memory usage
                                    img = Image.open(file_path)
                                    # Create thumbnail (max 300px wide to save memory)
                                    img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                                    st.image(img, width='stretch')
                                except Exception:
                                    st.markdown('<div class="file-thumbnail"></div>', unsafe_allow_html=True)
                            elif file_ext == '.pdf':
                                st.markdown('<div class="file-pdf-icon">📄</div>', unsafe_allow_html=True)
                            else:
                                st.markdown('<div class="file-pdf-icon">📎</div>', unsafe_allow_html=True)
                            
                            # File info
                            st.markdown(f"""
                            <div class="file-info">
                                <div class="file-name" title="{file_name}">{file_name}</div>
                                <div class="file-meta">
                                    <span class="file-size">{file_size}</span>
                                    <span class="file-tag">BYOV</span>
                                </div>
                            </div>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            # Download button (full width, compact)
                            with open(file_path, "rb") as f:
                                mime_type = "application/pdf" if file_ext == ".pdf" else "image/jpeg"
                                st.download_button(
                                    label="⬇ Download",
                                    data=f.read(),
                                    file_name=file_name,
                                    mime=mime_type,
                                    key=f"dl_{category}_{tech_id}_{i}_{j}",
                                    width='stretch'
                                )
    
    # Signed PDF section with inline viewer
    pdf_path = original_row.get('signature_pdf_path')
    if pdf_path and os.path.exists(pdf_path):
        st.markdown('<div class="file-section-title">📄 Signed Agreement</div>', unsafe_allow_html=True)
        
        # Toggle for expanded view
        viewer_key = f"pdf_expanded_{tech_id}"
        if viewer_key not in st.session_state:
            st.session_state[viewer_key] = False
        
        col_toggle, col_download = st.columns([3, 1])
        with col_toggle:
            if st.button(
                "🔍 Expand View" if not st.session_state[viewer_key] else "🔍 Collapse View",
                key=f"toggle_pdf_{tech_id}"
            ):
                st.session_state[viewer_key] = not st.session_state[viewer_key]
                st.rerun()
        
        with col_download:
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="⬇ Download",
                    data=f.read(),
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                    key=f"dl_signed_pdf_{tech_id}"
                )
        
        # Inline PDF viewer using base64 iframe
        try:
            with open(pdf_path, "rb") as pdf_file:
                pdf_data = pdf_file.read()
                base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
                
                # Set height based on expanded state
                pdf_height = 800 if st.session_state[viewer_key] else 500
                
                pdf_display = f'''
                <iframe 
                    src="data:application/pdf;base64,{base64_pdf}" 
                    width="100%" 
                    height="{pdf_height}px" 
                    style="border: 1px solid #ddd; border-radius: 8px;"
                    type="application/pdf">
                </iframe>
                '''
                st.markdown(pdf_display, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Could not load PDF preview: {e}")
        
        st.markdown("---")
    
    # Vehicle photos
    vehicle_paths = original_row.get('vehicle_photos_paths', [])
    if isinstance(vehicle_paths, list) and vehicle_paths:
        valid_paths = [p for p in vehicle_paths if os.path.exists(p)]
        if valid_paths:
            render_file_grid(valid_paths, "Vehicle Photos", "🚗")
            st.markdown("---")
    
    # Insurance documents
    insurance_paths = original_row.get('insurance_docs_paths', [])
    if isinstance(insurance_paths, list) and insurance_paths:
        valid_paths = [p for p in insurance_paths if os.path.exists(p)]
        if valid_paths:
            render_file_grid(valid_paths, "Insurance Documents", "🛡️")
            st.markdown("---")
    
    # Registration documents
    registration_paths = original_row.get('registration_docs_paths', [])
    if isinstance(registration_paths, list) and registration_paths:
        valid_paths = [p for p in registration_paths if os.path.exists(p)]
        if valid_paths:
            render_file_grid(valid_paths, "Registration Documents", "📋")
    
    # Bottom close button
    st.markdown("---")
    if st.button("✖ Close File Viewer", key="close_modal_bottom", width='stretch'):
        if 'show_file_modal' in st.session_state:
            del st.session_state.show_file_modal
        st.rerun()

# ------------------------
# ADMIN SETTINGS PAGE (Hidden)
# ------------------------
def page_admin_settings():
    st.title("🔧 Admin Settings")
    st.caption("Signature position calibration and system settings")
    
    st.warning("⚠ This page is for administrators only. Changes here affect PDF signature placement.")
    
    st.subheader("Signature Position Calibration")
    
    st.info("""
    **PDF Coordinate System:**
    - Standard letter size: 8.5" x 11" = 612 x 792 points
    - Origin (0,0) is at bottom-left corner
    - X increases to the right
    - Y increases upward
    """)
    
    # Initialize session state for coordinates
    if 'sig_x' not in st.session_state:
        st.session_state.sig_x = 90
    if 'sig_y' not in st.session_state:
        st.session_state.sig_y = 450
    if 'date_x' not in st.session_state:
        st.session_state.date_x = 320
    if 'date_y' not in st.session_state:
        st.session_state.date_y = 450
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Signature Position:**")
        sig_x = st.slider(
            "Signature X Position (left margin)",
            min_value=0,
            max_value=600,
            value=st.session_state.sig_x,
            step=5,
            help="Distance from left edge in points (72 points = 1 inch)"
        )
        st.session_state.sig_x = sig_x
        st.write(f"X = {sig_x} points ({sig_x/72:.2f} inches from left)")
        
        sig_y = st.slider(
            "Signature Y Position (from bottom)",
            min_value=0,
            max_value=800,
            value=st.session_state.sig_y,
            step=5,
            help="Distance from bottom edge in points (72 points = 1 inch)"
        )
        st.session_state.sig_y = sig_y
        st.write(f"Y = {sig_y} points ({sig_y/72:.2f} inches from bottom)")
    
    with col2:
        st.write("**Date Position:**")
        date_x = st.slider(
            "Date X Position (left margin)",
            min_value=0,
            max_value=600,
            value=st.session_state.date_x,
            step=5,
            help="Distance from left edge in points (72 points = 1 inch)"
        )
        st.session_state.date_x = date_x
        st.write(f"X = {date_x} points ({date_x/72:.2f} inches from left)")
        
        date_y = st.slider(
            "Date Y Position (from bottom)",
            min_value=0,
            max_value=800,
            value=st.session_state.date_y,
            step=5,
            help="Distance from bottom edge in points (72 points = 1 inch)"
        )
        st.session_state.date_y = date_y
        st.write(f"Y = {date_y} points ({date_y/72:.2f} inches from bottom)")
    
    st.markdown("---")
    
    st.subheader("Test Signature Preview")
    st.write("Draw a test signature to preview placement:")
    
    # Test signature canvas
    test_canvas = st_canvas(
        fill_color="rgba(255, 255, 255, 0)",
        stroke_width=2,
        stroke_color="#000000",
        background_color="rgba(255, 255, 255, 0)",
        height=150,
        width=400,
        drawing_mode="freedraw",
        key="test_signature_canvas",
    )
    
    if test_canvas.image_data is not None:
        import numpy as np
        img_array = np.array(test_canvas.image_data)
        if img_array[:, :, 3].max() > 0:
            st.success("Test signature captured")
            
            # Option to generate test PDF
            if st.button("Generate Test PDF with Current Settings"):
                try:
                    test_template = "template_1.pdf"
                    if os.path.exists(test_template):
                        test_sig_img = Image.fromarray(test_canvas.image_data.astype('uint8'), 'RGBA')
                        test_output = "test_signature_preview.pdf"
                        
                        success = generate_signed_pdf(
                            test_template,
                            test_sig_img,
                            test_output,
                            sig_x=sig_x,
                            sig_y=sig_y,
                            date_x=date_x,
                            date_y=date_y
                        )
                        
                        if success:
                            with open(test_output, "rb") as f:
                                st.download_button(
                                    label="📥 Download Test PDF",
                                    data=f.read(),
                                    file_name="test_signature_preview.pdf",
                                    mime="application/pdf"
                                )
                            st.success("Test PDF generated! Download to verify signature placement.")
                        else:
                            st.error("Failed to generate test PDF")
                    else:
                        st.error("Template file not found")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    st.markdown("---")
    st.subheader("Template Files")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Template 1 (Default):**")
        if os.path.exists(DEFAULT_TEMPLATE):
            st.success(f"✓ {DEFAULT_TEMPLATE} found")
        else:
            st.error(f"✗ {DEFAULT_TEMPLATE} not found")
    
    with col2:
        st.write("**Template 2 (CA, WA, IL):**")
        template_2 = "template_2.pdf"
        if os.path.exists(template_2):
            st.success(f"✓ {template_2} found")
        else:
            st.error(f"✗ {template_2} not found")


# ------------------------
# MAIN APP
# ------------------------
def main():
    st.set_page_config(
        page_title="BYOV Program",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    
    init_database()
    
    # Theme-aware styling with mobile optimization
    st.markdown("""
        <style>
        .stApp {
            background-color: var(--background-color);
        }
        .main {
            background-color: var(--background-color);
            padding: 1rem;
        }
        /* Enrollment form container - centered and constrained */
        .enrollment-form-container {
            max-width: 800px;
            margin: 0 auto;
        }
        /* Hide sidebar completely */
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            display: none !important;
        }
        section[data-testid="stSidebar"] {
            display: none !important;
        }
        button[kind="headerNoPadding"] {
            display: none !important;
        }
        
        /* Header icon buttons */
        .header-icon-button {
            font-size: 1.5rem !important;
            padding: 0.25rem 0.5rem !important;
            min-height: auto !important;
            height: auto !important;
        }
        
        /* Mobile responsive adjustments */
        @media (max-width: 768px) {
            .main {
                padding: 0.5rem;
                padding-top: 3.5rem;
            }
            .stButton>button, .stDownloadButton>button {
                font-size: 14px;
                padding: 0.5rem;
            }
            .header-icon-button {
                font-size: 1.25rem !important;
            }
            h1 {
                font-size: 1.5rem !important;
            }
            h2 {
                font-size: 1.25rem !important;
            }
            h3 {
                font-size: 1.1rem !important;
            }
            .stTextInput>div>div>input {
                font-size: 14px;
            }
        }
        /* Sears blue theme for buttons and checkboxes */
        :root, .stApp {
            --primaryColor: #0d6efd !important;
            --primary-color: #0d6efd !important;
            --accent-color: #0d6efd !important;
            --theme-primary: #0d6efd !important;
        }
        .stButton>button, .stDownloadButton>button, button {
            background-color: #0d6efd !important;
            color: #fff !important;
            border: 1px solid #0d6efd !important;
            box-shadow: none !important;
        }
        .stButton>button:hover, .stDownloadButton>button:hover, button:hover {
            background-color: #0b5ed7 !important;
        }
        .stButton>button:focus, button:focus {
            outline: 3px solid rgba(13,110,253,0.18) !important;
            box-shadow: 0 0 0 3px rgba(13,110,253,0.08) !important;
        }
        /* Accent color for native checkboxes and radios (modern browsers) */
        input[type="checkbox"], input[type="radio"] {
            accent-color: #0d6efd !important;
            -webkit-appearance: auto !important;
        }
        /* Force colored checkbox backgrounds where browsers use SVGs */
        input[type="checkbox"]:checked::before, input[type="checkbox"]:checked {
            background-color: #0d6efd !important;
            border-color: #0d6efd !important;
        }
        /* Fallback: style labels near checkboxes to look accented */
        .stCheckbox, .stRadio {
            color: inherit !important;
        }
        
        /* BYOV enrollment outer shell */
        .byov-shell {
            max-width: 900px;
            margin: 0 auto 1.5rem auto;
            padding: 1.5rem 1.75rem 2rem;
            border-radius: 18px;
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(246,248,252,0.98));
            box-shadow: 0 18px 45px rgba(15,23,42,0.14);
            border: 1px solid rgba(15,23,42,0.06);
        }

        .byov-step-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 1.25rem;
        }

        .byov-step-title {
            font-size: 1.2rem;
            font-weight: 600;
            color: #0f172a;
        }

        .byov-step-sub {
            font-size: 0.9rem;
            color: #6b7280;
        }

        .byov-progress-label {
            font-size: 0.8rem;
            font-weight: 500;
            text-align: center;
            padding: 0.25rem 0.5rem;
            border-radius: 999px;
            border: 1px solid transparent;
        }

        .byov-progress-label.completed {
            color: #16a34a;
            border-color: rgba(22,163,74,0.3);
            background: rgba(220,252,231,0.6);
        }

        .byov-progress-label.active {
            color: #0d6efd;
            border-color: rgba(13,110,253,0.4);
            background: rgba(219,234,254,0.7);
        }

        .byov-progress-label.pending {
            color: #6b7280;
            border-color: rgba(148,163,184,0.4);
            background: rgba(249,250,251,0.9);
        }
        </style>
        """, unsafe_allow_html=True)
    
    # Check for required PDF templates
    templates_ok = True
    if not os.path.exists(DEFAULT_TEMPLATE):
        st.error(f"⚠ Required template file '{DEFAULT_TEMPLATE}' not found!")
        templates_ok = False
    if not os.path.exists("template_2.pdf"):
        st.warning(f"⚠ Template file 'template_2.pdf' not found. CA, WA, IL states will use default template.")
    
    if not templates_ok:
        st.stop()

    # Initialize admin authentication state
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False
    
    # Check URL mode parameter to determine initial page
    mode = st.query_params.get("mode", "enroll")
    
    # Handle DocuSign confirmation mode - special standalone page
    if mode == "confirm_docusign":
        token = st.query_params.get("token", "")
        render_docusign_confirmation_page(token)
        return
    
    # Initialize session state for navigation based on URL mode
    if 'current_page' not in st.session_state:
        if mode == "admin":
            # Admin mode - go to login or dashboard
            if st.session_state.admin_authenticated:
                st.session_state.current_page = "Admin Control Center"
            else:
                st.session_state.current_page = "Admin Login"
        else:
            # Default to enrollment
            st.session_state.current_page = "New Enrollment"
    
    # Handle mode changes via URL (for direct navigation)
    if 'last_mode' not in st.session_state:
        st.session_state.last_mode = mode
    elif st.session_state.last_mode != mode:
        st.session_state.last_mode = mode
        if mode == "admin":
            if st.session_state.admin_authenticated:
                st.session_state.current_page = "Admin Control Center"
            else:
                st.session_state.current_page = "Admin Login"
        else:
            st.session_state.current_page = "New Enrollment"
        st.rerun()
    
    # Navigation callback functions
    def go_to_admin():
        if st.session_state.admin_authenticated:
            st.session_state.current_page = "Admin Control Center"
        else:
            st.session_state.current_page = "Admin Login"
    
    def go_to_enrollment():
        st.session_state.current_page = "New Enrollment"
    
    def go_to_settings():
        st.session_state.current_page = "Admin Settings"
    
    # Helper function to render pages inside an exclusive placeholder
    # This prevents phantom rendering during page transitions
    def render_current_page():
        """Render the current page content - all page rendering goes through this function"""
        current_page = st.session_state.current_page
        
        # DEBUG: Show which page is being rendered (remove after fixing)
        # st.sidebar.write(f"DEBUG: Rendering page: {current_page}")
        # st.sidebar.write(f"DEBUG: admin_authenticated: {st.session_state.admin_authenticated}")
        
        if current_page == "New Enrollment":
            # Center the enrollment form with max-width constraint
            st.markdown("""
                <style>
                [data-testid="stMainBlockContainer"] {
                    max-width: 800px;
                    margin: 0 auto;
                }
                </style>
            """, unsafe_allow_html=True)
            
            # Create centered header with clickable logo (hidden admin access)
            logo_path = "static/sears_logo_brand.png"
            
            # Center the logo and make it clickable for admin access
            col_left, col_center, col_right = st.columns([1, 2, 1])
            with col_center:
                if os.path.exists(logo_path):
                    # Display logo and title
                    st.markdown("""
                        <style>
                        .enrollment-header {
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                            margin-bottom: 10px;
                        }
                        .enrollment-header img {
                            max-width: 250px;
                        }
                        .enrollment-title {
                            color: #0d6efd;
                            font-size: 1.3rem;
                            font-weight: 600;
                            text-align: center;
                            margin-top: 10px;
                        }
                        </style>
                    """, unsafe_allow_html=True)
                    
                    # Display logo
                    with open(logo_path, "rb") as f:
                        logo_bytes = f.read()
                    import base64
                    logo_b64 = base64.b64encode(logo_bytes).decode()
                    
                    st.markdown(f"""
                        <div class="enrollment-header">
                            <img src="data:image/png;base64,{logo_b64}" alt="Sears Home Services">
                            <div class="enrollment-title">BYOV Technician Enrollment</div>
                        </div>
                    """, unsafe_allow_html=True)
            
            page_new_enrollment()
            return True
        
        elif current_page == "Admin Login":
            # CRITICAL: If already authenticated, redirect immediately without rendering anything
            if st.session_state.admin_authenticated:
                st.session_state.current_page = "Admin Control Center"
                st.rerun()
                st.stop()
            
            # Admin login page - use a keyed container to force clean rendering
            with st.container(key="admin_login_page"):
                logo_path = "static/sears_logo_brand.png"
                
                col_left, col_center, col_right = st.columns([1, 2, 1])
                with col_center:
                    if os.path.exists(logo_path):
                        st.image(logo_path, width=200)
                    
                    st.markdown("### Admin Login")
                    st.markdown("Please enter your credentials to access the Admin Control Center.")
                    
                    # Use session state to track form inputs
                    username = st.text_input("Username", key="login_username")
                    password = st.text_input("Password", type="password", key="login_password")
                    
                    if st.button("Login", use_container_width=True, type="primary"):
                        admin_user = os.environ.get("ADMIN_USERNAME", "admin")
                        admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
                        
                        if username == admin_user and password == admin_pass:
                            st.session_state.admin_authenticated = True
                            st.session_state.current_page = "Admin Control Center"
                            # Clear login inputs
                            if 'login_username' in st.session_state:
                                del st.session_state.login_username
                            if 'login_password' in st.session_state:
                                del st.session_state.login_password
                            # Force complete page reload via JavaScript with timestamp to bust cache
                            import time
                            ts = int(time.time() * 1000)
                            st.markdown(f"""
                                <script>
                                    window.location.href = window.location.pathname + '?mode=admin&_ts={ts}';
                                </script>
                            """, unsafe_allow_html=True)
                            st.stop()
                        else:
                            st.error("Invalid username or password")
            return True
        
        elif current_page == "Admin Control Center":
            # Verify authentication FIRST - before any widgets
            if not st.session_state.admin_authenticated:
                st.session_state.current_page = "Admin Login"
                st.rerun()
                st.stop()
            
            # Header with logo and logout button
            logo_path = "static/sears_logo_brand.png"
            header_col1, header_col2 = st.columns([9, 1])
            with header_col1:
                if os.path.exists(logo_path):
                    st.image(logo_path, width=200)
            with header_col2:
                if st.button("Logout", key="logout_button", help="Logout"):
                    st.session_state.admin_authenticated = False
                    st.session_state.current_page = "Admin Login"
                    # Force complete page reload via JavaScript
                    import time
                    ts = int(time.time() * 1000)
                    st.markdown(f"""
                        <script>
                            window.location.href = window.location.pathname + '?mode=admin&_ts={ts}';
                        </script>
                    """, unsafe_allow_html=True)
                    st.stop()
            
            page_admin_control_center()
            return True
        
        elif current_page == "Admin Settings":
            # Verify authentication
            if not st.session_state.admin_authenticated:
                st.session_state.current_page = "Admin Login"
                st.rerun()
                st.stop()
            
            page_admin_settings()
            return True
        
        return False
    
    # Add CSS to ensure clean page transitions
    st.markdown(f"""
        <style>
        /* Add a page identifier to help debug and hide orphaned elements */
        [data-testid="stMainBlockContainer"]::before {{
            content: "Page: {st.session_state.current_page}";
            display: none;
        }}
        </style>
    """, unsafe_allow_html=True)
    
    # Render the current page directly (no placeholder - cleaner for Streamlit)
    render_current_page()


if __name__ == "__main__":
    main()
