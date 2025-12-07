#!/usr/bin/env python3
"""
Export all data from the development database to JSON backup files.
This preserves all enrollments, documents, checklists, and settings.
"""

import json
import os
from datetime import datetime
import database_pg as database

def export_all_data():
    """Export all database tables to JSON files."""
    
    backup_dir = "data_backup"
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print("Starting database export...")
    
    enrollments = database.get_all_enrollments() or []
    print(f"Found {len(enrollments)} enrollments")
    
    all_documents = []
    all_checklists = []
    
    for enrollment in enrollments:
        eid = enrollment.get('id')
        if eid is None:
            continue
        
        docs = database.get_documents_for_enrollment(eid) or []
        for doc in docs:
            doc['enrollment_id'] = eid
        all_documents.extend(docs)
        
        checklist = database.get_checklist_for_enrollment(eid) or []
        for item in checklist:
            item['enrollment_id'] = eid
        all_checklists.extend(checklist)
    
    print(f"Found {len(all_documents)} documents")
    print(f"Found {len(all_checklists)} checklist items")
    
    try:
        settings = database.get_notification_settings() or {}
        print("Found notification settings")
    except Exception as e:
        print(f"No notification settings found: {e}")
        settings = {}
    
    def serialize(obj):
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return str(obj)
    
    enrollments_file = os.path.join(backup_dir, f"enrollments_{timestamp}.json")
    with open(enrollments_file, 'w') as f:
        json.dump(enrollments, f, indent=2, default=serialize)
    print(f"Saved enrollments to {enrollments_file}")
    
    documents_file = os.path.join(backup_dir, f"documents_{timestamp}.json")
    with open(documents_file, 'w') as f:
        json.dump(all_documents, f, indent=2, default=serialize)
    print(f"Saved documents to {documents_file}")
    
    checklists_file = os.path.join(backup_dir, f"checklists_{timestamp}.json")
    with open(checklists_file, 'w') as f:
        json.dump(all_checklists, f, indent=2, default=serialize)
    print(f"Saved checklists to {checklists_file}")
    
    settings_file = os.path.join(backup_dir, f"settings_{timestamp}.json")
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2, default=serialize)
    print(f"Saved settings to {settings_file}")
    
    latest_enrollments = os.path.join(backup_dir, "enrollments_latest.json")
    latest_documents = os.path.join(backup_dir, "documents_latest.json")
    latest_checklists = os.path.join(backup_dir, "checklists_latest.json")
    latest_settings = os.path.join(backup_dir, "settings_latest.json")
    
    with open(latest_enrollments, 'w') as f:
        json.dump(enrollments, f, indent=2, default=serialize)
    with open(latest_documents, 'w') as f:
        json.dump(all_documents, f, indent=2, default=serialize)
    with open(latest_checklists, 'w') as f:
        json.dump(all_checklists, f, indent=2, default=serialize)
    with open(latest_settings, 'w') as f:
        json.dump(settings, f, indent=2, default=serialize)
    
    print("\n=== Export Complete ===")
    print(f"Backup directory: {backup_dir}")
    print(f"Enrollments: {len(enrollments)}")
    print(f"Documents: {len(all_documents)}")
    print(f"Checklists: {len(all_checklists)}")
    print(f"Settings: {'Yes' if settings else 'No'}")
    
    return {
        'enrollments': len(enrollments),
        'documents': len(all_documents),
        'checklists': len(all_checklists),
        'backup_dir': backup_dir,
        'timestamp': timestamp
    }

if __name__ == "__main__":
    result = export_all_data()
    print(f"\nExport summary: {result}")
