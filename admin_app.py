"""
BYOV Admin Dashboard Application

This is the admin control center for the BYOV (Bring Your Own Vehicle) program.
It runs on port 8080 and handles admin login, enrollment management, and settings.
"""
import streamlit as st

st.set_page_config(page_title="BYOV Admin Dashboard",
                   page_icon="🔧",
                   layout="wide",
                   initial_sidebar_state="collapsed")

import os
import base64
import logging

import database_pg as database


def validate_environment():
    """Validate required environment variables at startup."""
    warnings = []
    errors = []

    db_url = os.environ.get("DATABASE_URL")
    prod_db_url = os.environ.get("PRODUCTION_DATABASE_URL")
    is_production = os.environ.get("REPLIT_DEPLOYMENT")

    if is_production and not prod_db_url:
        warnings.append(
            "PRODUCTION_DATABASE_URL not set - falling back to DATABASE_URL")
    if not db_url and not prod_db_url:
        errors.append(
            "No database URL configured (DATABASE_URL or PRODUCTION_DATABASE_URL)"
        )

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


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
    """Render the admin login page with single-click form submission."""
    st.markdown("""
    <style>
    .site-header, .record-card-container, .stats-bar, .card-header, 
    .pending-badge, [data-testid="stExpander"] {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("## Admin Login")
    st.markdown("Please enter your credentials to access the Admin Control Center.")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password",
                                 type="password",
                                 autocomplete="current-password")
        submitted = st.form_submit_button("Login",
                                          use_container_width=True,
                                          type="primary")

        if submitted:
            admin_user = os.environ.get("ADMIN_USERNAME", "admin")
            admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")

            if username == admin_user and password == admin_pass:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Invalid username or password")


def render_admin_dashboard():
    """Render the admin control center dashboard with new card-based UI."""
    from admin_dashboard_v2 import main as render_new_admin_dashboard
    
    col1, col2 = st.columns([9, 1])
    with col2:
        if st.button("Logout", key="logout_button", help="Logout"):
            st.session_state.admin_authenticated = False
            st.rerun()

    render_new_admin_dashboard()


def main():
    """Main function for admin application."""
    init_database()

    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False

    is_authenticated = st.session_state.admin_authenticated
    
    logging.info(f"Admin authentication state: {is_authenticated}")
    
    if is_authenticated:
        render_admin_dashboard()
    else:
        render_admin_login()


if __name__ == "__main__":
    main()
