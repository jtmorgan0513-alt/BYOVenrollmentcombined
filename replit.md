# BYOV Enrollment Automation

## Overview
The BYOV (Bring Your Own Vehicle) Enrollment Automation System is designed to streamline the vehicle enrollment process for Sears Home Services technicians. It features a multi-step wizard for technicians to submit vehicle information, documents, signatures, and photos. An integrated admin control center allows for managing approvals and syncing approved enrollments with an external dashboard system. The core purpose is to automate this process, making it efficient and ensuring data transmission to a central system.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

The system comprises a dual-application setup connected via a proxy:

1.  **React Landing Page** (Port 5000): Serves as the public-facing frontend, offering a marketing landing page, benefits calculator, state selector, and testimonials. It includes an AI Chatbot for program information and "Enroll Now" and "Admin" buttons to access the Streamlit application.
2.  **Streamlit Enrollment Engine** (Port 8000): Handles the core enrollment wizard and an admin dashboard for managing submissions.

**Proxy Integration:** An Express server proxies the Streamlit app through port 5000 to manage Replit's single-port limitation, handling redirects for enrollment (`/enroll`) and admin (`/admin`) paths and WebSocket connections.

**Landing Page Frontend (React):** Built with React + TypeScript, Tailwind CSS, Radix UI, and shadcn/ui. Features a responsive design, Framer Motion animations, and an OpenAI-powered AI Chatbot providing comprehensive BYOV program knowledge.

**Enrollment Engine Frontend (Streamlit):** A Streamlit-based web application providing a multi-step wizard workflow (Tech Info → Vehicle & Docs → Policy & Signature → Review & Submit). Includes VIN decoding, a digital signature pad, photo/document upload, and an Admin Control Center. Performance is optimized with caching mechanisms. Special workflow for California enrollments integrates DocuSign for compliant electronic signatures.

**Backend Architecture:**
*   **Database Layer:** Primarily PostgreSQL with connection pooling (ThreadedConnectionPool, min 2, max 10 connections). SQLite/JSON fallback available. Uses an abstraction layer for flexible database management.
*   **File Storage System:** Supports both local filesystem and Replit Object Storage, with a unified interface for abstraction. Includes optimizations for photo uploads (parallel processing, compression to 1400px max, JPEG quality 65%, EXIF orientation handling).
*   **Document Generation:** Uses ReportLab and PyPDF2 to generate enrollment PDFs with state-based templates and embedded signatures.
*   **Notification System:** Employs SendGrid for email delivery, utilizing branded HTML templates for various notifications (submission, approval, HR, custom).

**Performance Optimizations:**
*   **Database Connection Pooling:** ThreadedConnectionPool (min 2, max 10) for efficient database access under load.
*   **Response Compression:** Gzip compression (level 6) for all Express responses over 1KB.
*   **Image Compression:** Automatic resizing to 1400px max dimension, JPEG compression at 65% quality.
*   **Environment Validation:** Startup validation of critical environment variables with logging.
*   **Streamlit Caching:** 30-second TTL cache for enrollment data, resource caching for database initialization.
*   **Health Endpoint:** `/health` endpoint for deployment monitoring and load balancer health checks.

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
*   **Replit Object Storage:** For private object storage, detected via `PRIVATE_OBJECT_DIR`.
*   **Local Filesystem:** Fallback storage for `uploads/` and `pdfs/`.

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