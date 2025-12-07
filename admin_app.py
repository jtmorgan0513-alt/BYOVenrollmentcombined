"""
BYOV Admin Dashboard Application

This is the admin control center for the BYOV (Bring Your Own Vehicle) program.
It runs on port 8001 and handles admin login, enrollment management, and settings.

Routes:
- /admin - Admin login and dashboard
"""
import streamlit as st  # noqa: E402
st.set_page_config(
    page_title="BYOV Admin Dashboard",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="collapsed"
)

import os  # noqa: E402
import time  # noqa: E402
import logging  # noqa: E402

import database_pg as database  # noqa: E402


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
    """Render the admin control center dashboard with new card-based UI."""
    col1, col2 = st.columns([9, 1])
    with col2:
        if st.button("Logout", key="logout_button", help="Logout"):
            st.session_state.admin_authenticated = False
            st.rerun()
    
    from admin_dashboard_v2 import main as render_new_admin_dashboard
    render_new_admin_dashboard()


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
