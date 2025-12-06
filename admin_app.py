"""
BYOV Admin Dashboard Application

This is the admin control center for the BYOV (Bring Your Own Vehicle) program.
It runs on port 8001 and handles admin login, enrollment management, and settings.

Routes:
- /admin - Admin login and dashboard
"""
import streamlit as st
st.set_page_config(
    page_title="BYOV Admin Dashboard",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

import os
import time
import logging

import database
from admin_dashboard import page_admin_control_center
from dashboard_sync import push_to_dashboard_single_request, pull_dashboard_data, push_dashboard_update


def inject_admin_theme_css():
    """Inject the BYOV admin theme CSS for a polished dashboard look."""
    css = """
    <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body, [data-testid="stAppViewContainer"] {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f9fafb;
      color: #1e293b;
    }

    .site-header {
      background: white;
      border-bottom: 1px solid #e5e7eb;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    .header-inner {
      max-width: 1280px;
      margin: 0 auto;
      padding: 1rem 1.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .pending-badge {
      background: #dbeafe;
      color: #1e40af;
      padding: 0.375rem 0.875rem;
      border-radius: 9999px;
      font-size: 0.875rem;
      font-weight: 600;
    }

    .record-card {
      background: white;
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      border: 1px solid #e5e7eb;
      overflow: hidden;
      margin-bottom: 1rem;
    }

    .card-header {
      background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #1e40af 100%);
      padding: 1.25rem 1.5rem;
      color: white;
    }

    .card-header h2 {
      font-size: 1.5rem;
      font-weight: 700;
      margin-bottom: 0.5rem;
    }

    .status-badge {
      display: inline-block;
      padding: 0.375rem 0.75rem;
      border-radius: 8px;
      font-size: 0.875rem;
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
      color: #1e293b;
    }

    .section-tab {
      background: #f3f4f6;
      border: none;
      padding: 0.625rem 1rem;
      cursor: pointer;
      font-size: 0.8rem;
      font-weight: 500;
      color: #6b7280;
      border-bottom: 2px solid transparent;
      transition: all 0.15s ease;
    }

    .section-tab:hover { color: #1e293b; }
    .section-tab.active {
      color: #2563eb;
      border-bottom-color: #2563eb;
      background: white;
    }

    .info-row {
      display: flex;
      justify-content: space-between;
      padding: 0.625rem 0;
      border-bottom: 1px solid #f3f4f6;
    }

    .info-row:last-child { border-bottom: none; }

    .info-label {
      font-size: 0.8rem;
      color: #6b7280;
    }

    .info-value {
      font-size: 0.8rem;
      font-weight: 600;
      color: #1e293b;
    }

    .check-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0;
    }

    .action-btn {
      padding: 0.625rem 1.25rem;
      border-radius: 8px;
      font-size: 0.875rem;
      font-weight: 600;
      cursor: pointer;
      border: none;
      transition: all 0.15s ease;
    }

    .action-btn.primary {
      background: #2563eb;
      color: white;
    }

    .action-btn.primary:hover { background: #1d4ed8; }

    .action-btn.success {
      background: #22c55e;
      color: white;
    }

    .action-btn.success:hover { background: #16a34a; }

    .action-btn.danger {
      background: #ef4444;
      color: white;
    }

    .action-btn.danger:hover { background: #dc2626; }

    [data-testid="stMainBlockContainer"] {
      max-width: 1280px;
      margin: 0 auto;
      padding: 1.5rem;
    }

    [data-testid="stSidebar"] {
      background: #f9fafb;
    }

    .stButton > button {
      border-radius: 8px;
      font-weight: 600;
    }

    .stButton > button:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


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


def render_admin_login():
    """Render the admin login page."""
    logo_path = "static/sears_logo_brand.png"
    
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        if os.path.exists(logo_path):
            st.image(logo_path, width=200)
        
        st.markdown("### Admin Login")
        st.markdown("Please enter your credentials to access the Admin Control Center.")
        
        username = st.text_input("Username", key="login_username", autocomplete="username")
        password = st.text_input("Password", type="password", key="login_password", autocomplete="current-password")
        
        if st.button("Login", use_container_width=True, type="primary"):
            admin_user = os.environ.get("ADMIN_USERNAME", "admin")
            admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
            
            if username == admin_user and password == admin_pass:
                st.session_state.admin_authenticated = True
                if 'login_username' in st.session_state:
                    del st.session_state.login_username
                if 'login_password' in st.session_state:
                    del st.session_state.login_password
                st.rerun()
            else:
                st.error("Invalid username or password")


def render_admin_dashboard():
    """Render the admin control center dashboard."""
    inject_admin_theme_css()
    
    logo_path = "static/sears_logo_brand.png"
    header_col1, header_col2 = st.columns([9, 1])
    with header_col1:
        if os.path.exists(logo_path):
            st.image(logo_path, width=200)
    with header_col2:
        if st.button("Logout", key="logout_button", help="Logout"):
            st.session_state.admin_authenticated = False
            ts = int(time.time() * 1000)
            st.markdown(f"""
                <script>
                    window.location.href = window.location.pathname + '?_ts={ts}';
                </script>
            """, unsafe_allow_html=True)
            st.rerun()
    
    page_admin_control_center()


def main():
    """Main function for admin application."""
    init_database()
    
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False
    
    if st.session_state.admin_authenticated:
        render_admin_dashboard()
    else:
        render_admin_login()


if __name__ == "__main__":
    main()
