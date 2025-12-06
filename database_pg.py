"""
PostgreSQL database module for BYOV Enrollment Engine.
Replaces SQLite with PostgreSQL for persistent storage across deployments.
Uses connection pooling for optimal performance under load.
"""
import os
import json
import time
import atexit
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

def get_database_url():
    """Get the appropriate database URL based on environment.
    Uses PRODUCTION_DATABASE_URL in production, falls back to DATABASE_URL for development.
    """
    if os.environ.get("REPLIT_DEPLOYMENT"):
        prod_url = os.environ.get("PRODUCTION_DATABASE_URL")
        if prod_url:
            return prod_url
        print("WARNING: REPLIT_DEPLOYMENT is set but PRODUCTION_DATABASE_URL is missing. Falling back to DATABASE_URL.")
    return os.environ.get("DATABASE_URL")

DATABASE_URL = get_database_url()

MAX_RETRIES = 3
RETRY_DELAY = 0.5

# Connection pool settings
POOL_MIN_CONN = 2
POOL_MAX_CONN = 10

# Global connection pool
_connection_pool = None


def _get_pool():
    """Get or create the connection pool (singleton pattern)."""
    global _connection_pool
    if _connection_pool is None and DATABASE_URL:
        try:
            _connection_pool = pool.ThreadedConnectionPool(
                POOL_MIN_CONN,
                POOL_MAX_CONN,
                DATABASE_URL,
                connect_timeout=10
            )
            # Register cleanup on exit
            atexit.register(_cleanup_pool)
        except Exception as e:
            print(f"Warning: Could not create connection pool: {e}")
            return None
    return _connection_pool


def _cleanup_pool():
    """Clean up connection pool on shutdown."""
    global _connection_pool
    if _connection_pool:
        try:
            _connection_pool.closeall()
        except Exception:
            pass
        _connection_pool = None


def _create_connection():
    """Get a connection from pool or create new one with retry logic."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set")
    
    # Try to get from pool first
    pool_instance = _get_pool()
    if pool_instance:
        try:
            conn = pool_instance.getconn()
            # Test connection is still alive
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except Exception:
            # Connection from pool is stale, close and get new one
            try:
                pool_instance.putconn(conn, close=True)
            except Exception:
                pass
    
    # Fallback to direct connection with retry
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    
    raise last_error if last_error else RuntimeError("Failed to connect to database")


def _return_connection(conn):
    """Return connection to pool or close it."""
    pool_instance = _get_pool()
    if pool_instance:
        try:
            pool_instance.putconn(conn)
            return
        except Exception:
            pass
    # If no pool or putconn failed, just close
    try:
        conn.close()
    except Exception:
        pass


@contextmanager
def get_connection():
    """Context manager for database connections with pooling support."""
    conn = _create_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _return_connection(conn)


@contextmanager
def get_cursor(dict_cursor: bool = True):
    """Context manager for database cursors."""
    with get_connection() as conn:
        cursor_factory = RealDictCursor if dict_cursor else None
        cursor = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cursor
        finally:
            cursor.close()


def with_retry(func):
    """Decorator to retry database operations on connection errors."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise
        if last_error:
            raise last_error
    return wrapper


def init_db():
    """Initialize database tables if they don't exist."""
    with get_cursor(dict_cursor=False) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                tech_id TEXT NOT NULL,
                district TEXT,
                state TEXT,
                referred_by TEXT,
                industries JSONB DEFAULT '[]',
                industry JSONB DEFAULT '[]',
                year TEXT,
                make TEXT,
                model TEXT,
                vin TEXT,
                insurance_exp TEXT,
                registration_exp TEXT,
                template_used TEXT,
                comment TEXT,
                submission_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                approved INTEGER DEFAULT 0,
                approved_at TIMESTAMP WITH TIME ZONE,
                approved_by TEXT,
                dashboard_tech_id TEXT,
                last_upload_report JSONB
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
                doc_type TEXT NOT NULL,
                file_path TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_rules (
                id SERIAL PRIMARY KEY,
                rule_name TEXT NOT NULL,
                trigger TEXT NOT NULL,
                days_before INTEGER,
                recipients TEXT NOT NULL,
                enabled INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications_sent (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
                rule_id INTEGER NOT NULL REFERENCES notification_rules(id) ON DELETE CASCADE,
                sent_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                id SERIAL PRIMARY KEY,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value JSONB NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_tech_id ON enrollments(tech_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_enrollment_id ON documents(enrollment_id)")
        
        # Add new columns for hire status and truck number (if they don't exist)
        try:
            cursor.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS is_new_hire BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS truck_number TEXT")
            cursor.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS first_name TEXT")
            cursor.execute("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS last_name TEXT")
        except Exception:
            pass  # Columns may already exist


def insert_enrollment(record: Dict[str, Any]) -> int:
    """Insert a new enrollment and return its ID."""
    industries_list = record.get("industry", record.get("industries", []))
    if isinstance(industries_list, str):
        try:
            industries_list = json.loads(industries_list)
        except:
            industries_list = [x.strip() for x in industries_list.split(",") if x.strip()]
    
    industries_json = json.dumps(industries_list)
    
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO enrollments (
                full_name, tech_id, district, state, referred_by,
                industries, industry, year, make, model, vin,
                insurance_exp, registration_exp, template_used, comment,
                submission_date, approved, approved_at, approved_by,
                is_new_hire, truck_number, first_name, last_name
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """, (
            record.get("full_name"),
            record.get("tech_id"),
            record.get("district"),
            record.get("state"),
            record.get("referred_by"),
            industries_json,
            industries_json,
            record.get("year"),
            record.get("make"),
            record.get("model"),
            record.get("vin"),
            record.get("insurance_exp"),
            record.get("registration_exp"),
            record.get("template_used"),
            record.get("comment"),
            record.get("submission_date", datetime.now().isoformat()),
            0,
            None,
            None,
            record.get("is_new_hire", False),
            record.get("truck_number"),
            record.get("first_name"),
            record.get("last_name")
        ))
        result = cursor.fetchone()
        return result["id"] if isinstance(result, dict) else result[0]


@with_retry
def get_all_enrollments() -> List[Dict[str, Any]]:
    """Return all enrollments ordered by submission date."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM enrollments ORDER BY submission_date DESC")
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            r = dict(row)
            if r.get("industries"):
                if isinstance(r["industries"], str):
                    try:
                        r["industries"] = json.loads(r["industries"])
                    except:
                        r["industries"] = []
            else:
                r["industries"] = []
            
            if r.get("industry"):
                if isinstance(r["industry"], str):
                    try:
                        r["industry"] = json.loads(r["industry"])
                    except:
                        r["industry"] = []
            else:
                r["industry"] = r["industries"]
            
            if r.get("submission_date"):
                r["submission_date"] = str(r["submission_date"])
            if r.get("approved_at"):
                r["approved_at"] = str(r["approved_at"])
            
            results.append(r)
        
        return results


@with_retry
def get_enrollment_by_id(enrollment_id: int) -> Optional[Dict[str, Any]]:
    """Return a single enrollment with its documents."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM enrollments WHERE id = %s", (enrollment_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        record = dict(row)
        
        if record.get("industries"):
            if isinstance(record["industries"], str):
                try:
                    record["industries"] = json.loads(record["industries"])
                except:
                    record["industries"] = []
        else:
            record["industries"] = []
        
        if record.get("industry"):
            if isinstance(record["industry"], str):
                try:
                    record["industry"] = json.loads(record["industry"])
                except:
                    record["industry"] = []
        else:
            record["industry"] = record["industries"]
        
        if record.get("submission_date"):
            record["submission_date"] = str(record["submission_date"])
        if record.get("approved_at"):
            record["approved_at"] = str(record["approved_at"])
        
        cursor.execute(
            "SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = %s",
            (enrollment_id,)
        )
        docs = cursor.fetchall()
        record["documents"] = [dict(d) for d in docs]
        
        return record


def update_enrollment(enrollment_id: int, updates: Dict[str, Any]):
    """Update specific fields on an enrollment."""
    if not updates:
        return
    
    ALLOWED_COLUMNS = {
        'full_name', 'tech_id', 'district', 'state', 'referred_by', 
        'industries', 'industry', 'year', 'make', 'model', 'vin',
        'insurance_exp', 'registration_exp', 'template_used', 'comment',
        'submission_date', 'approved', 'approved_at', 'approved_by',
        'dashboard_tech_id', 'last_upload_report'
    }
    
    fields = []
    values = []
    
    for key, value in updates.items():
        if key not in ALLOWED_COLUMNS:
            raise ValueError(f"Invalid column name: {key}")
        
        if key in ("industries", "industry"):
            value = json.dumps(value) if isinstance(value, (list, dict)) else value
            if key == "industry":
                fields.append("industry = %s")
                values.append(value)
                fields.append("industries = %s")
                values.append(value)
                continue
        fields.append(f"{key} = %s")
        values.append(value)
    
    values.append(enrollment_id)
    
    with get_cursor() as cursor:
        cursor.execute(
            f"UPDATE enrollments SET {', '.join(fields)} WHERE id = %s",
            values
        )


def set_dashboard_sync_info(enrollment_id: int, dashboard_tech_id: str = None, report: dict = None):
    """Persist dashboard sync metadata on an enrollment."""
    fields = []
    values = []
    
    if dashboard_tech_id is not None:
        fields.append("dashboard_tech_id = %s")
        values.append(str(dashboard_tech_id))
    
    if report is not None:
        fields.append("last_upload_report = %s")
        values.append(json.dumps(report))
    
    if not fields:
        return
    
    values.append(enrollment_id)
    
    with get_cursor() as cursor:
        cursor.execute(
            f"UPDATE enrollments SET {', '.join(fields)} WHERE id = %s",
            values
        )


def delete_enrollment(enrollment_id: int):
    """Delete an enrollment and its documents (CASCADE)."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM enrollments WHERE id = %s", (enrollment_id,))


def add_document(enrollment_id: int, doc_type: str, file_path: str):
    """Add a document record for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO documents (enrollment_id, doc_type, file_path) VALUES (%s, %s, %s)",
            (enrollment_id, doc_type, file_path)
        )


def get_documents_for_enrollment(enrollment_id: int) -> List[Dict[str, Any]]:
    """Get all documents for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, doc_type, file_path FROM documents WHERE enrollment_id = %s",
            (enrollment_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def delete_documents_for_enrollment(enrollment_id: int):
    """Delete all documents for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM documents WHERE enrollment_id = %s", (enrollment_id,))


def add_notification_rule(rule: Dict[str, Any]):
    """Add a notification rule."""
    recipients = rule.get("recipients", [])
    if isinstance(recipients, list):
        recipients = ",".join(recipients)
    
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO notification_rules (rule_name, trigger, days_before, recipients, enabled)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            rule["rule_name"],
            rule["trigger"],
            rule.get("days_before"),
            recipients,
            1 if rule.get("enabled", True) else 0
        ))


def get_notification_rules() -> List[Dict[str, Any]]:
    """Get all notification rules."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM notification_rules ORDER BY id DESC")
        rules = []
        for row in cursor.fetchall():
            r = dict(row)
            r["recipients"] = r["recipients"].split(",") if r["recipients"] else []
            rules.append(r)
        return rules


def update_notification_rule(rule_id: int, updates: Dict[str, Any]):
    """Update a notification rule."""
    ALLOWED_COLUMNS = {
        'rule_name', 'trigger', 'days_before', 'recipients', 'enabled'
    }
    
    fields = []
    values = []
    
    for k, v in updates.items():
        if k not in ALLOWED_COLUMNS:
            raise ValueError(f"Invalid column name: {k}")
        
        if k == "recipients" and isinstance(v, list):
            v = ",".join(v)
        fields.append(f"{k} = %s")
        values.append(v)
    
    values.append(rule_id)
    
    with get_cursor() as cursor:
        cursor.execute(
            f"UPDATE notification_rules SET {', '.join(fields)} WHERE id = %s",
            values
        )


def delete_notification_rule(rule_id: int):
    """Delete a notification rule."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM notification_rules WHERE id = %s", (rule_id,))


def log_notification_sent(enrollment_id: int, rule_id: int):
    """Log that a notification was sent."""
    with get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO notifications_sent (enrollment_id, rule_id) VALUES (%s, %s)",
            (enrollment_id, rule_id)
        )


def get_sent_notifications(enrollment_id: int) -> List[Dict[str, Any]]:
    """Get sent notifications for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM notifications_sent WHERE enrollment_id = %s",
            (enrollment_id,)
        )
        results = []
        for row in cursor.fetchall():
            r = dict(row)
            if r.get("sent_at"):
                r["sent_at"] = str(r["sent_at"])
            results.append(r)
        return results


def approve_enrollment(enrollment_id: int, approved_by: str = "Admin") -> bool:
    """Mark an enrollment as approved."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE enrollments
            SET approved = 1,
                approved_at = %s,
                approved_by = %s
            WHERE id = %s
        """, (datetime.now(), approved_by, enrollment_id))
    return True


def load_enrollments() -> List[Dict[str, Any]]:
    """Legacy compatibility: returns all enrollments."""
    return get_all_enrollments()


def save_enrollments(records):
    """Legacy function - no-op for compatibility."""
    pass


def get_approval_notification_settings() -> Optional[Dict[str, Any]]:
    """Get the approval notification settings."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = %s",
            ("approval_notification",)
        )
        row = cursor.fetchone()
        if row:
            value = row.get('setting_value') if isinstance(row, dict) else row[0]
            if isinstance(value, str):
                return json.loads(value)
            return value
        return None


def save_approval_notification_settings(settings: Dict[str, Any]) -> bool:
    """Save the approval notification settings."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (setting_key) 
            DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at
        """, (
            "approval_notification",
            json.dumps(settings),
            datetime.now()
        ))
    return True


def get_notification_settings() -> Optional[Dict[str, Any]]:
    """Get the full notification settings (all 4 email types)."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = %s",
            ("notification_settings",)
        )
        row = cursor.fetchone()
        if row:
            value = row.get('setting_value') if isinstance(row, dict) else row[0]
            if isinstance(value, str):
                return json.loads(value)
            return value
        return None


def save_notification_settings(settings: Dict[str, Any]) -> bool:
    """Save the full notification settings (all 4 email types)."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (setting_key) 
            DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at
        """, (
            "notification_settings",
            json.dumps(settings),
            datetime.now()
        ))
    return True


CHECKLIST_TASKS = [
    {'key': 'approved_synced', 'name': 'Approved Enrollment & Synced to Dashboard'},
    {'key': 'policy_hshr', 'name': 'Signed Policy Form Sent to HSHRpaperwork'},
    {'key': 'mileage_segno', 'name': 'Mileage form created in Segno'},
    {'key': 'supplies_magnets', 'name': 'Supplies Notified for Magnets'},
    {'key': 'fleet_inventory', 'name': 'Fleet & Inventory Notified'},
    {'key': 'survey_30day', 'name': '30 Day survey completed'},
]


def init_checklist_table():
    """Initialize the enrollment_checklist table."""
    with get_cursor(dict_cursor=False) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enrollment_checklist (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
                task_key TEXT NOT NULL,
                task_name TEXT NOT NULL,
                completed BOOLEAN DEFAULT FALSE,
                completed_at TIMESTAMPTZ,
                completed_by TEXT,
                email_recipient TEXT,
                email_sent BOOLEAN DEFAULT FALSE,
                email_sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(enrollment_id, task_key)
            )
        """)


def create_checklist_for_enrollment(enrollment_id: int) -> bool:
    """Create checklist tasks for a new enrollment."""
    with get_cursor() as cursor:
        for task in CHECKLIST_TASKS:
            cursor.execute("""
                INSERT INTO enrollment_checklist (enrollment_id, task_key, task_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (enrollment_id, task_key) DO NOTHING
            """, (enrollment_id, task['key'], task['name']))
    return True


def get_checklist_for_enrollment(enrollment_id: int) -> List[Dict[str, Any]]:
    """Get all checklist tasks for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, enrollment_id, task_key, task_name, completed, completed_at, 
                   completed_by, email_recipient, email_sent, email_sent_at, created_at
            FROM enrollment_checklist
            WHERE enrollment_id = %s
            ORDER BY id
        """, (enrollment_id,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            if r.get("completed_at"):
                r["completed_at"] = str(r["completed_at"])
            if r.get("email_sent_at"):
                r["email_sent_at"] = str(r["email_sent_at"])
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
            results.append(r)
        return results


def update_checklist_task(task_id: int, completed: bool, completed_by: str = "Admin") -> bool:
    """Update a checklist task's completion status."""
    with get_cursor() as cursor:
        if completed:
            cursor.execute("""
                UPDATE enrollment_checklist
                SET completed = %s, completed_at = %s, completed_by = %s
                WHERE id = %s
            """, (completed, datetime.now(), completed_by, task_id))
        else:
            cursor.execute("""
                UPDATE enrollment_checklist
                SET completed = %s, completed_at = NULL, completed_by = NULL
                WHERE id = %s
            """, (completed, task_id))
    return True


def mark_checklist_task_by_key(enrollment_id: int, task_key: str, completed: bool = True, completed_by: str = "System") -> bool:
    """Mark a checklist task as complete by enrollment_id and task_key."""
    with get_cursor() as cursor:
        if completed:
            cursor.execute("""
                UPDATE enrollment_checklist
                SET completed = %s, completed_at = %s, completed_by = %s
                WHERE enrollment_id = %s AND task_key = %s
            """, (completed, datetime.now(), completed_by, enrollment_id, task_key))
        else:
            cursor.execute("""
                UPDATE enrollment_checklist
                SET completed = %s, completed_at = NULL, completed_by = NULL
                WHERE enrollment_id = %s AND task_key = %s
            """, (completed, enrollment_id, task_key))
    return True


def update_checklist_task_email(task_id: int, email_recipient: str) -> bool:
    """Update the email recipient for a checklist task."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE enrollment_checklist
            SET email_recipient = %s
            WHERE id = %s
        """, (email_recipient, task_id))
    return True


def mark_checklist_email_sent(task_id: int) -> bool:
    """Mark that the notification email was sent for a task."""
    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE enrollment_checklist
            SET email_sent = TRUE, email_sent_at = %s
            WHERE id = %s
        """, (datetime.now(), task_id))
    return True


def get_checklist_task_recipients() -> Dict[str, str]:
    """Get default email recipients for each task type from app_settings."""
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key = %s",
            ("checklist_recipients",)
        )
        row = cursor.fetchone()
        if row:
            value = row.get('setting_value') if isinstance(row, dict) else row[0]
            if isinstance(value, str):
                return json.loads(value)
            return value
        return {}


def save_checklist_task_recipients(recipients: Dict[str, str]) -> bool:
    """Save default email recipients for checklist tasks."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (setting_key) 
            DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = EXCLUDED.updated_at
        """, (
            "checklist_recipients",
            json.dumps(recipients),
            datetime.now()
        ))
    return True


def init_docusign_tokens_table():
    """Initialize the docusign_tokens table for California signature confirmations."""
    with get_cursor(dict_cursor=False) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS docusign_tokens (
                id SERIAL PRIMARY KEY,
                enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
                token VARCHAR(64) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP,
                confirmed BOOLEAN DEFAULT FALSE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_docusign_token ON docusign_tokens(token)")
    return True


def create_docusign_token(enrollment_id: int) -> str:
    """Create a unique token for DocuSign confirmation."""
    import secrets
    token = secrets.token_urlsafe(32)
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO docusign_tokens (enrollment_id, token)
            VALUES (%s, %s)
            ON CONFLICT (enrollment_id) DO UPDATE SET token = EXCLUDED.token, confirmed = FALSE, confirmed_at = NULL
        """, (enrollment_id, token))
    return token


def confirm_docusign_token(token: str) -> Dict[str, Any]:
    """Confirm a DocuSign token and mark the checklist task as complete.
    
    Returns dict with 'success', 'enrollment_id', 'tech_name' on success,
    or 'error' key on failure.
    """
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT dt.id, dt.enrollment_id, dt.confirmed, e.full_name, e.tech_id
            FROM docusign_tokens dt
            JOIN enrollments e ON dt.enrollment_id = e.id
            WHERE dt.token = %s
        """, (token,))
        row = cursor.fetchone()
        
        if not row:
            return {'error': 'Invalid or expired confirmation link'}
        
        if row.get('confirmed'):
            return {'error': 'This DocuSign has already been confirmed', 'already_confirmed': True}
        
        cursor.execute("""
            UPDATE docusign_tokens
            SET confirmed = TRUE, confirmed_at = %s
            WHERE token = %s
        """, (datetime.now(), token))
        
        enrollment_id = row.get('enrollment_id')
        mark_checklist_task_by_key(enrollment_id, 'policy_hshr', completed=True, completed_by='DocuSign Confirmation')
        
        return {
            'success': True,
            'enrollment_id': enrollment_id,
            'tech_name': row.get('full_name'),
            'tech_id': row.get('tech_id')
        }


def get_docusign_status(enrollment_id: int) -> Dict[str, Any]:
    """Get the DocuSign confirmation status for an enrollment."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT token, confirmed, confirmed_at, created_at
            FROM docusign_tokens
            WHERE enrollment_id = %s
        """, (enrollment_id,))
        row = cursor.fetchone()
        if row:
            return {
                'has_token': True,
                'confirmed': row.get('confirmed', False),
                'confirmed_at': str(row.get('confirmed_at')) if row.get('confirmed_at') else None,
                'created_at': str(row.get('created_at')) if row.get('created_at') else None
            }
        return {'has_token': False, 'confirmed': False}


USE_SQLITE = False
DB_PATH = None

try:
    init_db()
    init_checklist_table()
    init_docusign_tokens_table()
except Exception as e:
    print(f"Warning: Could not initialize PostgreSQL database: {e}")
