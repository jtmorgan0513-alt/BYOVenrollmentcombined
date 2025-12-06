#!/usr/bin/env python3
"""
Import data to production database from JSON backup files.
Run this AFTER publishing the app to populate the production database.

Usage:
  1. Set PRODUCTION_DATABASE_URL environment variable
  2. Run: python import_to_production.py

This script connects directly to the production database and imports:
- Enrollments (idempotent - skips existing based on tech_id + submission_date)
- Documents (linked to enrollments)
- Checklists (linked to enrollments)
- Notification settings (upserts into app_settings table)

All operations are wrapped in a single transaction for safety.
"""

import json
import os
import sys
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

BACKUP_DIR = "data_backup"

def get_production_db_url():
    """Get production database URL."""
    url = os.environ.get("PRODUCTION_DATABASE_URL")
    if not url:
        print("ERROR: PRODUCTION_DATABASE_URL environment variable not set.")
        print("Please set it before running this script.")
        sys.exit(1)
    return url

def load_backup_file(filename):
    """Load a JSON backup file."""
    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Warning: Backup file not found: {filepath}")
        return [] if filename != "settings_latest.json" else {}
    with open(filepath, 'r') as f:
        return json.load(f)

def create_tables(cur):
    """Create tables if they don't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id SERIAL PRIMARY KEY,
            full_name TEXT,
            tech_id TEXT,
            district TEXT,
            state TEXT,
            referred_by TEXT,
            industries JSONB,
            industry JSONB,
            year TEXT,
            make TEXT,
            model TEXT,
            vin TEXT,
            insurance_exp TEXT,
            registration_exp TEXT,
            template_used TEXT,
            comment TEXT,
            submission_date TIMESTAMPTZ DEFAULT NOW(),
            approved INTEGER DEFAULT 0,
            approved_at TIMESTAMPTZ,
            approved_by TEXT,
            dashboard_tech_id TEXT,
            last_upload_report JSONB,
            is_new_hire BOOLEAN DEFAULT FALSE,
            truck_number TEXT,
            first_name TEXT,
            last_name TEXT
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER REFERENCES enrollments(id) ON DELETE CASCADE,
            doc_type TEXT,
            file_path TEXT,
            uploaded_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checklists (
            id SERIAL PRIMARY KEY,
            enrollment_id INTEGER REFERENCES enrollments(id) ON DELETE CASCADE,
            task_key TEXT,
            task_label TEXT,
            completed BOOLEAN DEFAULT FALSE,
            completed_by TEXT,
            completed_at TIMESTAMPTZ
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            id SERIAL PRIMARY KEY,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_enrollments_tech_submission 
        ON enrollments (tech_id, submission_date)
    """)
    
    print("Tables created/verified.")

def check_existing_enrollment(cur, tech_id, submission_date):
    """Check if an enrollment already exists and return its ID if found."""
    cur.execute("""
        SELECT id FROM enrollments 
        WHERE tech_id = %s AND submission_date::text LIKE %s
    """, (tech_id, f"{str(submission_date)[:19]}%"))
    result = cur.fetchone()
    return result[0] if result else None

def import_enrollments(cur, enrollments):
    """Import enrollments to production database (idempotent)."""
    if not enrollments:
        print("No enrollments to import.")
        return {}
    
    old_to_new_id = {}
    imported = 0
    skipped = 0
    
    for e in enrollments:
        old_id = e.get('id')
        tech_id = e.get('tech_id')
        submission_date = e.get('submission_date')
        
        existing_id = check_existing_enrollment(cur, tech_id, submission_date)
        if existing_id:
            old_to_new_id[old_id] = existing_id
            skipped += 1
            continue
        
        industries = e.get('industries')
        if isinstance(industries, list):
            industries = json.dumps(industries)
        
        industry = e.get('industry')
        if isinstance(industry, list):
            industry = json.dumps(industry)
        
        last_upload_report = e.get('last_upload_report')
        if isinstance(last_upload_report, dict):
            last_upload_report = json.dumps(last_upload_report)
        
        cur.execute("""
            INSERT INTO enrollments (
                full_name, tech_id, district, state, referred_by,
                industries, industry, year, make, model, vin,
                insurance_exp, registration_exp, template_used, comment,
                submission_date, approved, approved_at, approved_by,
                dashboard_tech_id, last_upload_report, is_new_hire,
                truck_number, first_name, last_name
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) RETURNING id
        """, (
            e.get('full_name'),
            e.get('tech_id'),
            e.get('district'),
            e.get('state'),
            e.get('referred_by'),
            industries,
            industry,
            e.get('year'),
            e.get('make'),
            e.get('model'),
            e.get('vin'),
            e.get('insurance_exp'),
            e.get('registration_exp'),
            e.get('template_used'),
            e.get('comment'),
            e.get('submission_date'),
            e.get('approved', 0),
            e.get('approved_at'),
            e.get('approved_by'),
            e.get('dashboard_tech_id'),
            last_upload_report,
            e.get('is_new_hire', False),
            e.get('truck_number'),
            e.get('first_name'),
            e.get('last_name')
        ))
        
        new_id = cur.fetchone()[0]
        old_to_new_id[old_id] = new_id
        imported += 1
    
    print(f"Enrollments: {imported} imported, {skipped} skipped (already exist).")
    return old_to_new_id

def import_documents(cur, documents, id_mapping):
    """Import documents to production database (idempotent)."""
    if not documents:
        print("No documents to import.")
        return
    
    imported = 0
    skipped = 0
    
    for d in documents:
        old_enrollment_id = d.get('enrollment_id')
        new_enrollment_id = id_mapping.get(old_enrollment_id)
        
        if not new_enrollment_id:
            skipped += 1
            continue
        
        file_path = d.get('file_path')
        doc_type = d.get('doc_type')
        
        cur.execute("""
            SELECT id FROM documents 
            WHERE enrollment_id = %s AND file_path = %s
        """, (new_enrollment_id, file_path))
        
        if cur.fetchone():
            skipped += 1
            continue
        
        cur.execute("""
            INSERT INTO documents (enrollment_id, doc_type, file_path, uploaded_at)
            VALUES (%s, %s, %s, %s)
        """, (
            new_enrollment_id,
            doc_type,
            file_path,
            d.get('uploaded_at')
        ))
        imported += 1
    
    print(f"Documents: {imported} imported, {skipped} skipped.")

def import_checklists(cur, checklists, id_mapping):
    """Import checklists to production database (idempotent)."""
    if not checklists:
        print("No checklists to import.")
        return
    
    imported = 0
    skipped = 0
    
    for c in checklists:
        old_enrollment_id = c.get('enrollment_id')
        new_enrollment_id = id_mapping.get(old_enrollment_id)
        
        if not new_enrollment_id:
            skipped += 1
            continue
        
        task_key = c.get('task_key')
        
        cur.execute("""
            SELECT id FROM checklists 
            WHERE enrollment_id = %s AND task_key = %s
        """, (new_enrollment_id, task_key))
        
        if cur.fetchone():
            skipped += 1
            continue
        
        cur.execute("""
            INSERT INTO checklists (enrollment_id, task_key, task_label, completed, completed_by, completed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            new_enrollment_id,
            task_key,
            c.get('task_label'),
            c.get('completed', False),
            c.get('completed_by'),
            c.get('completed_at')
        ))
        imported += 1
    
    print(f"Checklists: {imported} imported, {skipped} skipped.")

def import_settings(cur, settings):
    """Import notification settings to production database using app_settings table (upsert)."""
    if not settings:
        print("No settings to import.")
        return
    
    cur.execute("""
        INSERT INTO app_settings (setting_key, setting_value, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (setting_key) 
        DO UPDATE SET setting_value = EXCLUDED.setting_value, updated_at = NOW()
    """, ('notification_settings', json.dumps(settings)))
    
    print("Notification settings imported (upserted).")

def main():
    print("=== Production Database Import ===\n")
    
    db_url = get_production_db_url()
    print("Connecting to production database...")
    
    try:
        conn = psycopg2.connect(db_url, connect_timeout=10)
        conn.autocommit = False
        print("Connected successfully.\n")
    except Exception as e:
        print(f"ERROR: Could not connect to production database: {e}")
        sys.exit(1)
    
    try:
        print("Loading backup files...")
        enrollments = load_backup_file("enrollments_latest.json")
        documents = load_backup_file("documents_latest.json")
        checklists = load_backup_file("checklists_latest.json")
        settings = load_backup_file("settings_latest.json")
        
        print(f"  Enrollments: {len(enrollments)}")
        print(f"  Documents: {len(documents)}")
        print(f"  Checklists: {len(checklists)}")
        print(f"  Settings: {'Yes' if settings else 'No'}\n")
        
        with conn.cursor() as cur:
            print("Creating tables if needed...")
            create_tables(cur)
            print()
            
            print("Importing data (idempotent - safe to re-run)...")
            id_mapping = import_enrollments(cur, enrollments)
            import_documents(cur, documents, id_mapping)
            import_checklists(cur, checklists, id_mapping)
            import_settings(cur, settings)
        
        conn.commit()
        print("\n=== Import Complete (Transaction Committed) ===")
        print("Your production database now has all the data from development.")
        print("The development database remains unchanged for testing.")
        
    except Exception as e:
        conn.rollback()
        print(f"\nERROR: Import failed, transaction rolled back: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
