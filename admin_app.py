"""
BYOV Admin Dashboard Application

This is the admin control center for the BYOV (Bring Your Own Vehicle) program.
It runs on port 8001 and handles admin login, enrollment management, and settings.

Routes:
- /admin - Admin login and dashboard

UPDATES:
- Single-click login using st.form()
- Base64 embedded logo (no flash)
- Clean session state management
"""
import streamlit as st  # noqa: E402

st.set_page_config(page_title="BYOV Admin Dashboard",
                   page_icon="🔧",
                   layout="wide",
                   initial_sidebar_state="collapsed")

import os  # noqa: E402
import base64  # noqa: E402
import logging  # noqa: E402

import database_pg as database  # noqa: E402
from admin_dashboard_v2 import main as render_new_admin_dashboard  # noqa: E402


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


def get_logo_base64():
    """Get logo as base64 string for embedding."""
    logo_path = "static/sears_logo_brand.png"
    if os.path.exists(logo_path):
        try:
            with open(logo_path, 'rb') as f:
                return base64.b64encode(f.read()).decode()
        except Exception as e:
            logging.error(f"Failed to load logo: {e}")
            return None
    return None


def render_admin_login():
    """Render the admin login page with single-click form submission."""
    # Get logo once
    logo_b64 = get_logo_base64()

    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        # Embed logo as base64 to prevent flash
        if logo_b64:
            st.markdown(
                f'<div style="text-align:center; margin-bottom: 1.5rem;"><img src="data:image/png;base64,{logo_b64}" width="280" alt="Sears Logo"/></div>',
                unsafe_allow_html=True)

        st.markdown("### Admin Login")
        st.markdown(
            "Please enter your credentials to access the Admin Control Center."
        )

        # Use form for single-click submission
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

    if st.session_state.admin_authenticated:
        render_admin_dashboard()
    else:
        render_admin_login()


if __name__ == "__main__":
    main()
