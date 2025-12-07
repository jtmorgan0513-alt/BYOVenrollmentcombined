"""
BYOV Enrollment Application

This is the technician enrollment wizard for the BYOV (Bring Your Own Vehicle) program.
It runs on port 8000 and handles the multi-step enrollment process.

Routes:
- /enroll - Main enrollment wizard
- /?mode=confirm_docusign - DocuSign confirmation page
"""
import streamlit as st
st.set_page_config(
    page_title="Sears BYOV Enrollment",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="collapsed"
)

import os
import re
import base64
from datetime import date, datetime
import io
import uuid
import certifi

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

import database_pg as database
from database_pg import get_enrollment_by_id, get_documents_for_enrollment
from notifications import send_email_notification, send_docusign_request_hr
import file_storage
from dashboard_sync import push_to_dashboard, push_to_dashboard_single_request


def validate_environment():
    """Validate required environment variables at startup."""
    warnings = []
    errors = []
    
    db_url = os.environ.get("DATABASE_URL")
    prod_db_url = os.environ.get("PRODUCTION_DATABASE_URL")
    is_production = os.environ.get("REPLIT_DEPLOYMENT")
    
    if is_production and not prod_db_url:
        warnings.append("PRODUCTION_DATABASE_URL not set - falling back to DATABASE_URL")
    if not db_url and not prod_db_url:
        errors.append("No database URL configured (DATABASE_URL or PRODUCTION_DATABASE_URL)")
    
    if not os.environ.get("REPLIT_DASHBOARD_URL"):
        warnings.append("REPLIT_DASHBOARD_URL not set - dashboard sync will be unavailable")
    
    if not os.environ.get("SENDGRID_API_KEY"):
        warnings.append("SENDGRID_API_KEY not set - email notifications disabled")
    if not os.environ.get("SENDGRID_FROM_EMAIL"):
        warnings.append("SENDGRID_FROM_EMAIL not set - using default sender")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


@st.cache_resource
def init_database():
    """Initialize database connection once and cache the result."""
    env_check = validate_environment()
    if env_check["warnings"]:
        for warning in env_check["warnings"]:
            logging.warning(f"Environment: {warning}")
    if env_check["errors"]:
        for error in env_check["errors"]:
            logging.error(f"Environment: {error}")
    
    database.init_db()
    return True


STATE_TEMPLATE_MAP = {
    "CA": "template_2.pdf",
    "WA": "template_2.pdf",
    "IL": "template_2.pdf",
}
DEFAULT_TEMPLATE = "template_1.pdf"

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

MAX_IMAGE_DIMENSION = 1600
IMAGE_QUALITY = 0.65


def inject_image_compression_script():
    """Inject JavaScript that compresses images client-side before upload."""
    script = f"""
    <script>
    (function() {{
        if (window.imageCompressionLoaded) return;
        window.imageCompressionLoaded = true;
        
        const MAX_DIMENSION = {MAX_IMAGE_DIMENSION};
        const QUALITY = {IMAGE_QUALITY};
        
        async function compressImage(file) {{
            if (!file.type.startsWith('image/') || file.type === 'application/pdf') {{
                return file;
            }}
            
            return new Promise((resolve) => {{
                const reader = new FileReader();
                reader.onload = (e) => {{
                    const img = new Image();
                    img.onload = () => {{
                        let width = img.width;
                        let height = img.height;
                        
                        if (width > MAX_DIMENSION || height > MAX_DIMENSION) {{
                            if (width > height) {{
                                height = Math.round(height * MAX_DIMENSION / width);
                                width = MAX_DIMENSION;
                            }} else {{
                                width = Math.round(width * MAX_DIMENSION / height);
                                height = MAX_DIMENSION;
                            }}
                        }}
                        
                        const canvas = document.createElement('canvas');
                        canvas.width = width;
                        canvas.height = height;
                        
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, width, height);
                        
                        canvas.toBlob((blob) => {{
                            if (blob) {{
                                const compressedFile = new File([blob], file.name.replace(/\\.[^.]+$/, '.jpg'), {{
                                    type: 'image/jpeg',
                                    lastModified: Date.now()
                                }});
                                console.log(`Compressed ${{file.name}}: ${{(file.size/1024/1024).toFixed(2)}}MB -> ${{(compressedFile.size/1024/1024).toFixed(2)}}MB`);
                                resolve(compressedFile);
                            }} else {{
                                resolve(file);
                            }}
                        }}, 'image/jpeg', QUALITY);
                    }};
                    img.onerror = () => resolve(file);
                    img.src = e.target.result;
                }};
                reader.onerror = () => resolve(file);
                reader.readAsDataURL(file);
            }});
        }}
        
        function setupFileInputInterception() {{
            document.addEventListener('change', async (event) => {{
                const input = event.target;
                
                if (input.tagName !== 'INPUT' || input.type !== 'file') return;
                
                if (input.dataset.compressed === 'true') {{
                    delete input.dataset.compressed;
                    return;
                }}
                
                if (!input.files || input.files.length === 0) return;
                
                const files = Array.from(input.files);
                const hasImages = files.some(f => f.type.startsWith('image/') && !f.type.includes('pdf'));
                
                if (!hasImages) return;
                
                event.stopPropagation();
                
                const parent = input.closest('[data-testid]') || input.parentElement;
                let indicator = document.createElement('div');
                indicator.innerHTML = '<span style="color: #003366; font-size: 12px;">Optimizing images...</span>';
                indicator.id = 'compression-indicator-' + Date.now();
                if (parent) parent.appendChild(indicator);
                
                try {{
                    const compressedFiles = await Promise.all(
                        files.map(file => compressImage(file))
                    );
                    
                    const dt = new DataTransfer();
                    compressedFiles.forEach(file => dt.items.add(file));
                    
                    input.dataset.compressed = 'true';
                    
                    input.files = dt.files;
                    
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }} finally {{
                    if (indicator.parentNode) indicator.remove();
                }}
            }}, true);
        }}
        
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', setupFileInputInterception);
        }} else {{
            setupFileInputInterception();
        }}
        
        console.log('Image compression script loaded');
    }})();
    </script>
    """
    st.markdown(script, unsafe_allow_html=True)


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
    """Generate a PDF with signature, date, name, and tech ID overlay on page 6 (index 5)."""
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
        
        preprinted_date_x = 325
        preprinted_date_y = 485
        can.setFillColorRGB(1, 1, 1)
        can.rect(preprinted_date_x, preprinted_date_y, 50, 14, fill=True, stroke=False)
        can.setFillColorRGB(0, 0, 0)
        can.drawString(preprinted_date_x + 2, preprinted_date_y + 2, current_date)
        
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

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
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
    """Render a falling money (dollar) animation using pure HTML/CSS."""
    try:
        bills = []
        for i in range(count):
            left = (i * 73) % 100
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
        try:
            st.balloons()
        except Exception:
            pass


def decode_vin(vin: str):
    """Decode VIN using NHTSA API."""
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


def wizard_step_1():
    """Step 1: Technician Info & Industry Selection"""
    st.subheader("Technician Information")
    
    if 'wizard_data' not in st.session_state:
        st.session_state.wizard_data = {}
    
    data = st.session_state.wizard_data
    
    col1, col2 = st.columns(2)
    with col1:
        first_name = st.text_input(
            "First Name", 
            value=data.get('first_name', ''),
            key="wiz_first_name",
            autocomplete="given-name"
        )
    with col2:
        last_name = st.text_input(
            "Last Name", 
            value=data.get('last_name', ''),
            key="wiz_last_name",
            autocomplete="family-name"
        )
    
    full_name = f"{first_name} {last_name}".strip()
    
    tech_id = st.text_input(
        "Enterprise ID", 
        value=data.get('tech_id', ''),
        key="wiz_tech_id",
        autocomplete="off"
    )
    
    district = st.text_input(
        "District", 
        value=data.get('district', ''),
        key="wiz_district",
        autocomplete="off"
    )

    referred_by = st.text_input(
        "Referred By",
        value=data.get('referred_by', ''),
        key="wiz_referred_by",
        autocomplete="off"
    )
    
    state = st.selectbox(
        "State", 
        [""] + US_STATES,
        index=(US_STATES.index(data.get('state')) + 1) if data.get('state') in US_STATES else 0,
        key="wiz_state"
    )
    
    employment_options = ["New Hire (less than 30 days)", "Existing Tech"]
    employment_status = st.selectbox(
        "Employment Status",
        employment_options,
        index=employment_options.index(data.get('employment_status', 'Existing Tech')) if data.get('employment_status') in employment_options else 1,
        key="wiz_employment_status"
    )
    
    is_new_hire = employment_status == "New Hire (less than 30 days)"
    
    if is_new_hire:
        skip_truck = st.checkbox(
            "I don't have a truck number yet (new hire)",
            value=data.get('skip_truck_number', True),
            key="wiz_skip_truck"
        )
        if skip_truck:
            truck_number = ""
        else:
            truck_number = st.text_input(
                "Truck Number",
                value=data.get('truck_number', ''),
                key="wiz_truck_number",
                autocomplete="off"
            )
    else:
        truck_number = st.text_input(
            "Truck Number",
            value=data.get('truck_number', ''),
            key="wiz_truck_number_existing",
            autocomplete="off"
        )
    
    st.subheader("Industries")
    st.caption("Select all industries you are certified in:")
    
    selected_industries = []
    industry_cols = st.columns(4)
    for idx, ind in enumerate(INDUSTRIES):
        with industry_cols[idx % 4]:
            if st.checkbox(ind, value=ind in data.get('industries', []), key=f"wiz_ind_{ind}"):
                selected_industries.append(ind)
    
    st.markdown("---")
    
    col_prev, col_spacer, col_next = st.columns([1, 2, 1])
    with col_next:
        if st.button("Next →", use_container_width=True, type="primary"):
            errors = []
            if not first_name.strip():
                errors.append("First Name is required")
            if not last_name.strip():
                errors.append("Last Name is required")
            if not tech_id.strip():
                errors.append("Enterprise ID is required")
            if not state:
                errors.append("State is required")
            if not is_new_hire and not truck_number.strip():
                errors.append("Truck Number is required for existing technicians")
            if not selected_industries:
                errors.append("Select at least one industry")
            
            if errors:
                for e in errors:
                    st.error(e)
            else:
                st.session_state.wizard_data.update({
                    'first_name': first_name.strip(),
                    'last_name': last_name.strip(),
                    'full_name': full_name,
                    'tech_id': tech_id.strip().upper(),
                    'district': district.strip(),
                    'referred_by': referred_by.strip(),
                    'state': state,
                    'employment_status': employment_status,
                    'is_new_hire': is_new_hire,
                    'truck_number': truck_number.strip() if truck_number else '',
                    'industries': selected_industries
                })
                st.session_state.wizard_step = 2
                st.rerun()


def wizard_step_2():
    """Step 2: Vehicle Info & Document Uploads"""
    inject_image_compression_script()
    
    if 'wizard_data' not in st.session_state:
        st.session_state.wizard_data = {}
    
    data = st.session_state.wizard_data
    
    st.subheader("Vehicle Information")
    
    vin = st.text_input(
        "VIN (Vehicle Identification Number)",
        value=data.get('vin', ''),
        key="wiz_vin"
    )
    
    col_decode, col_spacer = st.columns([1, 3])
    with col_decode:
        if st.button("Decode VIN", use_container_width=True):
            if vin.strip():
                decoded = decode_vin(vin.strip())
                if decoded:
                    st.session_state.wizard_data['year'] = decoded.get('year', '')
                    st.session_state.wizard_data['make'] = decoded.get('make', '')
                    st.session_state.wizard_data['model'] = decoded.get('model', '')
                    st.success(f"Decoded: {decoded.get('year', '?')} {decoded.get('make', '?')} {decoded.get('model', '?')}")
                    st.rerun()
                else:
                    st.warning("Could not decode VIN. Please enter vehicle details manually.")
            else:
                st.warning("Enter a VIN first")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        year = st.text_input("Year", value=data.get('year', ''), key="wiz_year")
    with col2:
        make = st.text_input("Make", value=data.get('make', ''), key="wiz_make")
    with col3:
        model = st.text_input("Model", value=data.get('model', ''), key="wiz_model")
    
    st.markdown("---")
    st.subheader("Document Uploads")
    
    st.markdown("**Vehicle Photos** (front, back, sides)")
    vehicle_photos = st.file_uploader(
        "Upload vehicle photos",
        type=['jpg', 'jpeg', 'png', 'heic'],
        accept_multiple_files=True,
        key="wiz_vehicle_photos"
    )
    
    st.markdown("**Insurance Documents**")
    insurance_docs = st.file_uploader(
        "Upload insurance documents",
        type=['jpg', 'jpeg', 'png', 'pdf', 'heic'],
        accept_multiple_files=True,
        key="wiz_insurance_docs"
    )
    
    col_ins1, col_ins2 = st.columns(2)
    with col_ins1:
        insurance_exp = st.date_input(
            "Insurance Expiration Date",
            value=datetime.strptime(data.get('insurance_exp'), '%Y-%m-%d').date() if data.get('insurance_exp') else None,
            min_value=date.today(),
            key="wiz_insurance_exp"
        )
    
    st.markdown("**Registration Documents**")
    registration_docs = st.file_uploader(
        "Upload registration documents",
        type=['jpg', 'jpeg', 'png', 'pdf', 'heic'],
        accept_multiple_files=True,
        key="wiz_registration_docs"
    )
    
    col_reg1, col_reg2 = st.columns(2)
    with col_reg1:
        registration_exp = st.date_input(
            "Registration Expiration Date",
            value=datetime.strptime(data.get('registration_exp'), '%Y-%m-%d').date() if data.get('registration_exp') else None,
            min_value=date.today(),
            key="wiz_registration_exp"
        )
    
    st.markdown("---")
    
    col_prev, col_spacer, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← Back", use_container_width=True):
            st.session_state.wizard_step = 1
            st.rerun()
    
    with col_next:
        if st.button("Next →", use_container_width=True, type="primary"):
            errors = []
            if not vin.strip():
                errors.append("VIN is required")
            if not year.strip():
                errors.append("Vehicle Year is required")
            if not make.strip():
                errors.append("Vehicle Make is required")
            if not model.strip():
                errors.append("Vehicle Model is required")
            if not vehicle_photos:
                errors.append("At least one vehicle photo is required")
            if not insurance_docs:
                errors.append("Insurance document is required")
            if not insurance_exp:
                errors.append("Insurance expiration date is required")
            if not registration_docs:
                errors.append("Registration document is required")
            if not registration_exp:
                errors.append("Registration expiration date is required")
            
            if errors:
                for e in errors:
                    st.error(e)
            else:
                st.session_state.wizard_data.update({
                    'vin': vin.strip().upper(),
                    'year': year.strip(),
                    'make': make.strip(),
                    'model': model.strip(),
                    'insurance_exp': insurance_exp.strftime('%Y-%m-%d') if insurance_exp else '',
                    'registration_exp': registration_exp.strftime('%Y-%m-%d') if registration_exp else '',
                    'vehicle_photos': vehicle_photos,
                    'insurance_docs': insurance_docs,
                    'registration_docs': registration_docs
                })
                st.session_state.wizard_step = 3
                st.rerun()


def wizard_step_3():
    """Step 3: Policy Review & Signature"""
    if 'wizard_data' not in st.session_state:
        st.session_state.wizard_data = {}
    
    data = st.session_state.wizard_data
    state = data.get('state', '')
    
    state_abbr = ""
    state_to_abbr = {
        "California": "CA", "Washington": "WA", "Illinois": "IL",
        "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
        "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL",
        "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Indiana": "IN",
        "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
        "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI",
        "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
        "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
        "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND",
        "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
        "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
        "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
        "Virginia": "VA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"
    }
    state_abbr = state_to_abbr.get(state, "")
    
    is_docusign_state = state_abbr in ["CA"]
    
    template_file = STATE_TEMPLATE_MAP.get(state_abbr, DEFAULT_TEMPLATE)
    
    st.subheader("BYOV Policy Agreement")
    
    if os.path.exists(template_file):
        with open(template_file, "rb") as f:
            pdf_bytes = f.read()
        
        b64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        pdf_display = f'''
        <iframe src="data:application/pdf;base64,{b64_pdf}" 
                width="100%" height="500px" type="application/pdf">
        </iframe>
        '''
        st.markdown(pdf_display, unsafe_allow_html=True)
        
        st.download_button(
            label="📥 Download Policy PDF",
            data=pdf_bytes,
            file_name=f"BYOV_Policy_{state_abbr}.pdf",
            mime="application/pdf"
        )
    else:
        st.warning(f"Policy document not found: {template_file}")
    
    st.markdown("---")
    
    if is_docusign_state:
        st.info("""
        **California Enrollees:** Due to state regulations, you will receive a DocuSign 
        email to sign the policy electronically. Please check your email after submitting 
        your enrollment.
        """)
        
        policy_acknowledged = st.checkbox(
            "I have read and agree to the BYOV Policy terms. I understand I will receive a DocuSign email to complete my signature.",
            key="wiz_policy_ack"
        )
        
        signature_data = None
    else:
        st.subheader("Electronic Signature")
        st.caption("Please sign in the box below using your mouse or finger.")
        
        canvas_result = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=3,
            stroke_color="#000000",
            background_color="#ffffff",
            height=150,
            width=400,
            drawing_mode="freedraw",
            key="signature_canvas"
        )
        
        signature_data = canvas_result.image_data if canvas_result.image_data is not None else None
        
        has_signature = False
        if signature_data is not None:
            if signature_data.sum() > 0:
                has_signature = True
        
        policy_acknowledged = st.checkbox(
            "I have read and agree to the BYOV Policy terms",
            key="wiz_policy_ack"
        )
    
    st.markdown("---")
    
    col_prev, col_spacer, col_next = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← Back", use_container_width=True):
            st.session_state.wizard_step = 2
            st.rerun()
    
    with col_next:
        if st.button("Next →", use_container_width=True, type="primary"):
            errors = []
            
            if not policy_acknowledged:
                errors.append("You must acknowledge the policy to continue")
            
            if not is_docusign_state:
                if signature_data is None or not has_signature:
                    errors.append("Please sign the policy above")
            
            if errors:
                for e in errors:
                    st.error(e)
            else:
                st.session_state.wizard_data['policy_acknowledged'] = True
                st.session_state.wizard_data['is_docusign_state'] = is_docusign_state
                st.session_state.wizard_data['state_abbr'] = state_abbr
                
                if not is_docusign_state and signature_data is not None:
                    sig_img = Image.fromarray(signature_data.astype('uint8'), 'RGBA')
                    st.session_state.wizard_data['signature_image'] = sig_img
                
                st.session_state.wizard_step = 4
                st.rerun()


def wizard_step_4():
    """Step 4: Review & Submit"""
    if 'wizard_data' not in st.session_state:
        st.session_state.wizard_data = {}
    
    data = st.session_state.wizard_data
    
    st.subheader("Review Your Enrollment")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Technician Information**")
        st.write(f"**Name:** {data.get('full_name', 'N/A')}")
        st.write(f"**Enterprise ID:** {data.get('tech_id', 'N/A')}")
        st.write(f"**District:** {data.get('district', 'N/A')}")
        st.write(f"**State:** {data.get('state', 'N/A')}")
        st.write(f"**Employment Status:** {data.get('employment_status', 'N/A')}")
        if data.get('truck_number'):
            st.write(f"**Truck Number:** {data.get('truck_number')}")
        st.write(f"**Industries:** {', '.join(data.get('industries', []))}")
        if data.get('referred_by'):
            st.write(f"**Referred By:** {data.get('referred_by')}")
    
    with col2:
        st.markdown("**Vehicle Information**")
        st.write(f"**VIN:** {data.get('vin', 'N/A')}")
        st.write(f"**Year:** {data.get('year', 'N/A')}")
        st.write(f"**Make:** {data.get('make', 'N/A')}")
        st.write(f"**Model:** {data.get('model', 'N/A')}")
        st.write(f"**Insurance Expires:** {data.get('insurance_exp', 'N/A')}")
        st.write(f"**Registration Expires:** {data.get('registration_exp', 'N/A')}")
    
    st.markdown("---")
    
    st.markdown("**Uploaded Documents**")
    vehicle_photos = data.get('vehicle_photos', [])
    insurance_docs = data.get('insurance_docs', [])
    registration_docs = data.get('registration_docs', [])
    
    st.write(f"- Vehicle Photos: {len(vehicle_photos)} file(s)")
    st.write(f"- Insurance Documents: {len(insurance_docs)} file(s)")
    st.write(f"- Registration Documents: {len(registration_docs)} file(s)")
    
    if data.get('is_docusign_state'):
        st.info("📧 DocuSign will be sent after submission for electronic signature.")
    else:
        st.success("✅ Policy signed electronically")
    
    st.markdown("---")
    
    col_prev, col_spacer, col_submit = st.columns([1, 2, 1])
    with col_prev:
        if st.button("← Back", use_container_width=True):
            st.session_state.wizard_step = 3
            st.rerun()
    
    with col_submit:
        if st.button("Submit Enrollment", use_container_width=True, type="primary"):
            with st.spinner("Submitting enrollment..."):
                try:
                    record_id = str(uuid.uuid4())[:8]
                    tech_id = data.get('tech_id', '')
                    
                    folder_path = create_upload_folder(tech_id, record_id)
                    
                    vehicle_paths = save_uploaded_files(vehicle_photos, folder_path, "vehicle")
                    insurance_paths = save_uploaded_files(insurance_docs, folder_path, "insurance")
                    registration_paths = save_uploaded_files(registration_docs, folder_path, "registration")
                    
                    signature_pdf_path = None
                    if not data.get('is_docusign_state') and data.get('signature_image'):
                        state_abbr = data.get('state_abbr', '')
                        template_file = STATE_TEMPLATE_MAP.get(state_abbr, DEFAULT_TEMPLATE)
                        
                        pdf_filename = f"signed_policy_{tech_id}_{record_id}.pdf"
                        signature_pdf_path = os.path.join("pdfs", pdf_filename)
                        
                        success = generate_signed_pdf(
                            template_file,
                            data.get('signature_image'),
                            signature_pdf_path,
                            employee_name=data.get('full_name'),
                            tech_id=tech_id
                        )
                        
                        if not success:
                            st.error("Failed to generate signed PDF. Please try again.")
                            return
                    
                    enrollment_record = {
                        'first_name': data.get('first_name', ''),
                        'last_name': data.get('last_name', ''),
                        'full_name': data.get('full_name', ''),
                        'tech_id': tech_id,
                        'district': data.get('district', ''),
                        'referred_by': data.get('referred_by', ''),
                        'state': data.get('state', ''),
                        'is_new_hire': data.get('is_new_hire', False),
                        'truck_number': data.get('truck_number', ''),
                        'industries': data.get('industries', []),
                        'vin': data.get('vin', ''),
                        'year': data.get('year', ''),
                        'make': data.get('make', ''),
                        'model': data.get('model', ''),
                        'insurance_exp': data.get('insurance_exp', ''),
                        'registration_exp': data.get('registration_exp', ''),
                        'submission_date': datetime.now().isoformat(),
                        'status': 'pending'
                    }
                    
                    enrollment_id = database.insert_enrollment(enrollment_record)
                    
                    for path in vehicle_paths:
                        database.add_document(enrollment_id, 'vehicle', path)
                    for path in insurance_paths:
                        database.add_document(enrollment_id, 'insurance', path)
                    for path in registration_paths:
                        database.add_document(enrollment_id, 'registration', path)
                    if signature_pdf_path:
                        database.add_document(enrollment_id, 'signature', signature_pdf_path)
                    
                    if data.get('is_docusign_state'):
                        try:
                            send_docusign_request_hr(enrollment_record, enrollment_id)
                        except Exception as e:
                            logging.error(f"DocuSign request failed: {e}")
                    
                    try:
                        send_email_notification(enrollment_record)
                    except Exception as e:
                        logging.error(f"Email notification failed: {e}")
                    
                    st.session_state.wizard_data = {}
                    st.session_state.wizard_step = 1
                    
                    show_money_rain()
                    
                    st.success("🎉 Enrollment submitted successfully!")
                    st.balloons()
                    
                    if data.get('is_docusign_state'):
                        st.info("""
                        **Next Steps:**
                        1. Check your email for a DocuSign request
                        2. Sign the policy document electronically
                        3. Wait for admin approval
                        """)
                    else:
                        st.info("""
                        **Next Steps:**
                        Your enrollment is now pending review. You will receive an email 
                        once your enrollment has been approved.
                        """)
                    
                except Exception as e:
                    st.error(f"Error submitting enrollment: {str(e)}")
                    import traceback
                    logging.error(f"Enrollment submission error: {traceback.format_exc()}")


def render_docusign_confirmation_page(token: str):
    """Render the DocuSign confirmation page."""
    st.title("DocuSign Confirmation")
    
    if not token:
        st.error("Invalid confirmation link. No token provided.")
        return
    
    try:
        result = database.confirm_docusign_token(token)
        
        if result.get('success'):
            st.markdown("""
            <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); 
                        padding: 2rem; border-radius: 12px; text-align: center; margin-bottom: 1rem;">
                <h2 style="color: #155724; margin: 0;">✅ DocuSign Confirmed!</h2>
                <p style="color: #155724; margin-top: 0.5rem;">
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


def page_new_enrollment():
    """Main enrollment page with wizard navigation"""
    
    if 'wizard_step' not in st.session_state:
        st.session_state.wizard_step = 1
    
    current_step = st.session_state.wizard_step
    
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
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    step_titles = {
        1: ("Technician Information", "Tell us who you are and where you work."),
        2: ("Vehicle & Documents", "Add your vehicle details and upload required docs."),
        3: ("Policy & Signature", "Review the BYOV policy and sign electronically."),
        4: ("Review & Submit", "Double-check everything before you submit.")
    }
    title, subtitle = step_titles.get(current_step, ("BYOV Enrollment", ""))
    
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


def main():
    """Main function for enrollment application."""
    init_database()
    
    st.markdown("""
        <style>
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
        
        [data-testid="stMainBlockContainer"] {
            max-width: 800px;
            margin: 0 auto;
        }
        </style>
    """, unsafe_allow_html=True)
    
    if not os.path.exists(DEFAULT_TEMPLATE):
        st.error(f"Required template file '{DEFAULT_TEMPLATE}' not found!")
        st.stop()
    
    mode = st.query_params.get("mode", "enroll")
    
    if mode == "confirm_docusign":
        token = st.query_params.get("token", "")
        render_docusign_confirmation_page(token)
        return
    
    logo_path = "static/sears_logo_brand.png"
    
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        if os.path.exists(logo_path):
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
            
            with open(logo_path, "rb") as f:
                logo_bytes = f.read()
            logo_b64 = base64.b64encode(logo_bytes).decode()
            
            st.markdown(f"""
                <div class="enrollment-header">
                    <img src="data:image/png;base64,{logo_b64}" alt="Sears Home Services">
                    <div class="enrollment-title">BYOV Technician Enrollment</div>
                </div>
            """, unsafe_allow_html=True)
    
    page_new_enrollment()


if __name__ == "__main__":
    main()
