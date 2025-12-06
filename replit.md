# BYOV Enrollment Automation

## Overview
The BYOV (Bring Your Own Vehicle) Enrollment Automation System is designed to streamline the vehicle enrollment process for Sears Home Services technicians. It features a multi-step wizard for technicians to submit vehicle information, documents, signatures, and photos. An integrated admin control center allows for managing approvals and syncing approved enrollments with an external dashboard system. The core purpose is to automate this process, making it efficient and ensuring data transmission to a central system.

## User Preferences
Preferred communication style: Simple, everyday language.

## Recent Changes (December 2025)
- **Enrollment Wizard Updates:**
  - Split Full Name into First Name + Last Name fields (combined for storage as full_name)
  - Renamed "Tech ID" label to "Enterprise ID" (data still stored as tech_id)
  - Added Employment Status dropdown: "New Hire (less than 30 days)" / "Existing Tech"
  - Added Truck Number field with skip option for new hires
  - New database columns: first_name, last_name, is_new_hire (boolean), truck_number
- **Dashboard Sync:** Now sends isNewHire (boolean) and truckId fields to external API
- **Email Notifications:** Updated templates and admin field metadata to include new fields

## System Architecture

The system comprises a tri-application setup connected via a proxy:

1.  **React Landing Page** (Port 5000): Serves as the public-facing frontend, offering a marketing landing page, benefits calculator, state selector, and testimonials. It includes an AI Chatbot for program information and "Enroll Now" and "Admin" buttons to access the Streamlit applications.
2.  **Streamlit Enrollment App** (Port 8000, route `/enroll`): Handles the core enrollment wizard for technicians to submit vehicle information, documents, signatures, and photos.
3.  **Streamlit Admin App** (Port 8080, route `/admin`): Provides the admin control center for managing approvals and syncing with the external dashboard.

**Key Application Files:**
*   `enrollment_app.py`: Enrollment wizard (port 8000)
*   `admin_app.py`: Admin dashboard (port 8080)
*   `dashboard_sync.py`: Shared module for dashboard sync functions (push_to_dashboard, pull_dashboard_data, push_dashboard_update)
*   `byov_app.py`: DEPRECATED legacy monolithic app (kept for reference only)

**Proxy Integration:** An Express server proxies both Streamlit apps through port 5000 to manage Replit's single-port limitation. Routes `/enroll/*` proxy to port 8000, routes `/admin/*` proxy to port 8080. Both HTTP and WebSocket connections are handled with automatic health checks and keepalive pings.

**Landing Page Frontend (React):** Built with React + TypeScript, Tailwind CSS, Radix UI, and shadcn/ui. Features a responsive design, Framer Motion animations, and an OpenAI-powered AI Chatbot providing comprehensive BYOV program knowledge.

**Enrollment Engine (enrollment_app.py):** A Streamlit-based web application providing a multi-step wizard workflow (Tech Info → Vehicle & Docs → Policy & Signature → Review & Submit). Includes VIN decoding, a digital signature pad, photo/document upload. Performance is optimized with caching mechanisms. Special workflow for California enrollments integrates DocuSign for compliant electronic signatures.

**Admin Dashboard (admin_app.py):** A Streamlit-based admin control center with login authentication, technician enrollment list, approval workflow, document viewing, checklist management, notification settings, and dashboard sync functionality. Injects custom CSS theme for polished appearance.

**Backend Architecture:**
*   **Database Layer:** Primarily PostgreSQL with connection pooling (ThreadedConnectionPool, min 2, max 10 connections). SQLite/JSON fallback available. Uses an abstraction layer for flexible database management.
*   **File Storage System:** Supports both local filesystem and Replit Object Storage, with a unified interface for abstraction. Includes optimizations for photo uploads (parallel processing, compression to 1600px max, JPEG quality 65%, EXIF orientation handling).
*   **Document Generation:** Uses ReportLab and PyPDF2 to generate enrollment PDFs with state-based templates and embedded signatures.
*   **Notification System:** Employs SendGrid for email delivery, utilizing branded HTML templates for various notifications (submission, approval, HR, custom).

**Performance Optimizations:**
*   **Database Connection Pooling:** ThreadedConnectionPool (min 2, max 10) for efficient database access under load.
*   **Response Compression:** Gzip compression (level 6) for all Express responses over 1KB.
*   **Client-Side Image Compression:** JavaScript-based compression that resizes images to 1600px max and 65% JPEG quality before upload, reducing file sizes by 5-10x for faster mobile uploads.
*   **Server-Side Image Compression:** Automatic server-side resizing to 1600px max dimension, JPEG compression at 65% quality as backup.
*   **Environment Validation:** Startup validation of critical environment variables with logging.
*   **Streamlit Caching:** 30-second TTL cache for enrollment data, resource caching for database initialization.
*   **Health Endpoint:** `/health` endpoint for deployment monitoring and load balancer health checks.

**Reliability Features:**
*   **Streamlit Keepalive:** Express server pings both Streamlit backends every 30 seconds to prevent cold starts.
*   **Startup Health Check:** Express proxy verifies both Streamlit apps are ready before accepting requests via `/_stcore/health` endpoint.
*   **Retry with Backoff:** Exponential backoff retry logic (8 retries, 300ms initial delay) for graceful Streamlit connection handling.
*   **Friendly Loading State:** Shows branded loading page with spinner instead of server errors during startup.
*   **Extended Proxy Timeouts:** Increased timeout from 30s to 60s for long-running operations.
*   **Dual Process Management:** Production server manages both Streamlit processes with independent health monitoring and restart logic.

**Data Flow & Admin Workflow:**
Enrollment submission involves data validation, photo uploads, signature capture (or DocuSign for CA), saving to the database, PDF generation (or DocuSign request), and optional email notifications. The Admin Approval Workflow in the Streamlit dashboard provides a comprehensive interface for reviewing enrollments, managing checklists, viewing documents, and approving submissions, which triggers dashboard sync and custom email notifications.

## External Dependencies

### Third-Party APIs
*   **NHTSA VIN Decoder API:** Used for vehicle information lookup.
*   **Replit Dashboard API:** External REST API for technician record management and data synchronization, configured via `REPLIT_DASHBOARD_URL`.

### Database Services
*   **PostgreSQL:** Primary database, configured via `DATABASE_URL`.
*   **SQLite:** Local fallback database (`data/byov.db`).

### Cloud Storage
*   **Replit Object Storage:** Primary storage for uploaded files (photos, PDFs). Configured via `PRIVATE_OBJECT_DIR` environment variable pointing to the bucket path. **Required for production** - files persist across deployments.
*   **Local Filesystem:** Development fallback only - files in `uploads/` and `pdfs/` are NOT persistent across deployments.

### Email Services
*   **SendGrid:** Exclusively used for all email notifications. Requires `SENDGRID_API_KEY` and `SENDGRID_FROM_EMAIL`.

### Python Dependencies
*   `streamlit`: Web application framework.
*   `psycopg2-binary`: PostgreSQL adapter.
*   `Pillow`: Image processing.
*   `reportlab`, `PyPDF2`: PDF generation/manipulation.
*   `streamlit-drawable-canvas`: Signature capture.
*   `st_aggrid`: Data grid for admin dashboard.
*   `requests`: HTTP client.

### Environment Configuration
*   `DATABASE_URL` (Optional): PostgreSQL connection string.
*   `REPLIT_DASHBOARD_URL`: External dashboard API endpoint.
*   `REPLIT_DASHBOARD_USERNAME`, `REPLIT_DASHBOARD_PASSWORD`: Dashboard API authentication.
*   `PRIVATE_OBJECT_DIR` (Optional): Replit Object Storage bucket path.
*   `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`: SendGrid API key and sender email.