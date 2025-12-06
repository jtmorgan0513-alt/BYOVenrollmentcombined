"""
Dashboard Sync Module for BYOV Enrollment Engine.

This module contains all functions for synchronizing data with the external
Replit Dashboard API. It is used by both the enrollment app and admin app.

Functions:
- push_to_dashboard(record, enrollment_id): Create technician and upload photos
- push_dashboard_update(updated_record): Update existing technician record
- pull_dashboard_data(): Fetch technician data from dashboard

All payload shapes, endpoints, and business logic are preserved from the
original byov_app.py implementation.
"""

import os
import json
import time
import base64 as _b64
import mimetypes as _mimetypes
import hashlib
from datetime import datetime
from mimetypes import guess_type

import requests
import certifi

import database
import file_storage


# SSL certificate configuration
SYSTEM_CA_BUNDLE = '/etc/ssl/certs/ca-certificates.crt'


def _get_dashboard_credentials():
    """Get dashboard credentials from environment variables.
    
    Returns tuple of (dashboard_url, username, password).
    Ensures dashboard_url has a proper https:// scheme.
    """
    dashboard_url = os.getenv("REPLIT_DASHBOARD_URL", "https://byovdashboard.replit.app")
    username = os.getenv("REPLIT_DASHBOARD_USERNAME", "admin")
    password = os.getenv("REPLIT_DASHBOARD_PASSWORD", "")
    
    if dashboard_url and not dashboard_url.startswith(("http://", "https://")):
        dashboard_url = f"https://{dashboard_url}"
    
    return dashboard_url, username, password


def _create_dashboard_session():
    """Create a requests session configured with SSL certificate verification.
    
    Uses system CA certificates for the verify parameter when available,
    with fallback to certifi's certificate bundle.
    Returns a tuple of (session, ca_bundle_path) where ca_bundle_path should
    be passed to verify= parameter in all requests.
    """
    session = requests.Session()
    if os.path.exists(SYSTEM_CA_BUNDLE):
        ca_bundle = SYSTEM_CA_BUNDLE
    else:
        ca_bundle = certifi.where()
    return session, ca_bundle


def _dashboard_log(message: str):
    """Simple logging helper for diagnosing dashboard sync issues."""
    try:
        os.makedirs('logs', exist_ok=True)
        with open(os.path.join('logs', 'dashboard_sync.log'), 'a', encoding='utf-8') as lf:
            lf.write(f"{datetime.now().isoformat()} {message}\n")
    except Exception:
        pass


def _retry_request(func, attempts=3, backoff_base=0.5):
    """Generic retry wrapper for operations that return a requests.Response."""
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            resp = func()
            if hasattr(resp, 'ok'):
                if resp.ok:
                    return resp
                else:
                    raise RuntimeError(f"status_{resp.status_code}")
            return resp
        except Exception as e:
            last_exc = e
            _dashboard_log(f"Retry attempt {attempt} failed: {e}")
            if attempt < attempts:
                time.sleep(backoff_base * (2 ** (attempt - 1)))
    raise last_exc


def _format_date(date_str):
    """Format date string to YYYY-MM-DD format."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(str(date_str))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def push_to_dashboard(record: dict, enrollment_id: int) -> dict:
    """Create technician in Replit dashboard with complete data and photo uploads.
    
    This is the renamed version of post_to_dashboard() - logic is identical.
    
    Authentication Flow:
    1. POST /api/login with username/password to get session cookie
    2. POST /api/technicians with complete enrollment data using session
    3. Upload photos using GCS flow (get URL → PUT file → save photo record)
    
    Returns status dict with photo_count for UI messaging.
    """
    dashboard_url, username, password = _get_dashboard_credentials()
    
    try:
        session, ca_bundle = _create_dashboard_session()
        
        login_payload = {
            "username": username,
            "password": password
        }
        
        login_resp = session.post(
            f"{dashboard_url}/api/login",
            json=login_payload,
            timeout=10,
            verify=ca_bundle
        )
        
        if not login_resp.ok:
            return {
                "error": f"Login failed with status {login_resp.status_code}",
                "body": login_resp.text[:200]
            }
        
        submission_date = record.get("submission_date", "")
        date_started = _format_date(submission_date) or datetime.now().strftime("%Y-%m-%d")
        insurance_exp = _format_date(
            record.get("insurance_exp") or record.get("insurance_expiration") or record.get("insuranceExpiration")
        )
        registration_exp = _format_date(
            record.get("registration_exp") or record.get("registration_expiration") or record.get("registrationExpiration")
        )
        
        tech_id = record.get("tech_id", "").upper()
        if not tech_id:
            return {"error": "record missing tech_id"}
        
        check_resp = session.get(
            f"{dashboard_url}/api/technicians",
            params={"techId": tech_id},
            timeout=10,
            verify=ca_bundle
        )
        
        if check_resp.ok:
            try:
                existing = check_resp.json()
                if isinstance(existing, list) and existing:
                    return {"status": "exists", "photo_count": 0}
            except Exception:
                pass
        
        industry_raw = record.get('industry')
        if industry_raw is None:
            industry_raw = record.get('industries', [])
        if isinstance(industry_raw, list):
            industry = ", ".join(industry_raw) if industry_raw else ""
        else:
            industry = str(industry_raw) if industry_raw else ""

        referred_by_val = record.get('referred_by') or record.get('referredBy') or ""

        is_new_hire = bool(record.get("is_new_hire", False))
        hire_status = "New Hire" if is_new_hire else "Existing Tech"
        
        payload = {
            "name": record.get("full_name"),
            "techId": tech_id,
            "region": record.get("state"),
            "district": record.get("district"),
            "referredBy": referred_by_val,
            "enrollmentStatus": "Enrolled",
            "isNewHire": is_new_hire,
            "hireStatus": hire_status,
            "truckId": record.get("truck_number") or "",
            "dateStartedByov": date_started,
            "vinNumber": record.get("vin"),
            "vehicleMake": record.get("make"),
            "vehicleModel": record.get("model"),
            "vehicleYear": record.get("year"),
            "industry": industry,
            "insuranceExpiration": insurance_exp,
            "registrationExpiration": registration_exp
        }
        
        create_resp = session.post(
            f"{dashboard_url}/api/technicians",
            json=payload,
            timeout=15,
            verify=ca_bundle
        )
        
        if not (200 <= create_resp.status_code < 300):
            return {
                "error": f"dashboard responded {create_resp.status_code}",
                "body": create_resp.text[:200]
            }
        
        try:
            tech_data = create_resp.json()
            dashboard_tech_id = tech_data.get("id")
        except Exception:
            return {"error": "Failed to parse technician response"}
        
        if not dashboard_tech_id:
            return {"error": "No technician ID in response"}
        
        photo_count = 0
        failed_uploads = []

        vehicle_paths = []
        insurance_paths = []
        registration_paths = []
        try:
            if record.get("vehicle_photos_paths"):
                vehicle_paths = list(record.get("vehicle_photos_paths") or [])
            if record.get("insurance_docs_paths"):
                insurance_paths = list(record.get("insurance_docs_paths") or [])
            if record.get("registration_docs_paths"):
                registration_paths = list(record.get("registration_docs_paths") or [])

            if enrollment_id and not (vehicle_paths or insurance_paths or registration_paths):
                docs = database.get_documents_for_enrollment(enrollment_id)
                for d in docs:
                    p = d.get('file_path')
                    if not p:
                        continue
                    if d.get('doc_type') == 'vehicle':
                        vehicle_paths.append(p)
                    elif d.get('doc_type') == 'insurance':
                        insurance_paths.append(p)
                    elif d.get('doc_type') == 'registration':
                        registration_paths.append(p)
        except Exception:
            pass

        category_to_paths = {
            'vehicle': vehicle_paths,
            'insurance': insurance_paths,
            'registration': registration_paths
        }

        uploaded_entries = []

        for category, paths in category_to_paths.items():
            for photo_path in (paths or []):
                if not photo_path or not os.path.exists(photo_path):
                    failed_uploads.append({'path': photo_path, 'reason': 'missing'})
                    continue

                try:
                    try:
                        upload_req = _retry_request(lambda: session.post(
                            f"{dashboard_url}/api/objects/upload",
                            json={"category": category},
                            timeout=10,
                            verify=ca_bundle
                        ), attempts=3, backoff_base=0.6)
                    except Exception as e:
                        _dashboard_log(f"Failed to get upload URL for {photo_path}: {e}")
                        failed_uploads.append({'path': photo_path, 'reason': str(e)})
                        continue

                    upload_data = upload_req.json()
                    gcs_url = upload_data.get("uploadURL")
                    if not gcs_url:
                        _dashboard_log(f"No uploadURL returned for {photo_path}: {upload_data}")
                        failed_uploads.append({'path': photo_path, 'reason': 'no_upload_url'})
                        continue

                    mime_type, _ = guess_type(photo_path)
                    if not mime_type:
                        mime_type = 'application/octet-stream'

                    try:
                        def do_put():
                            with open(photo_path, 'rb') as f:
                                r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60)
                                return r
                        gcs_resp = _retry_request(do_put, attempts=3, backoff_base=0.6)
                    except Exception as e:
                        _dashboard_log(f"GCS PUT failed for {photo_path}: {e}")
                        failed_uploads.append({'path': photo_path, 'reason': str(e)})
                        continue

                    _dashboard_log(f"Uploaded {photo_path} to GCS: {gcs_url}")

                    uploaded_entries.append({
                        'uploadURL': gcs_url,
                        'category': category,
                        'mimeType': mime_type,
                        'path': photo_path
                    })

                except Exception as exc:
                    _dashboard_log(f"Unexpected error handling {photo_path}: {exc}")
                    failed_uploads.append({'path': photo_path, 'reason': str(exc)})
                    continue

        if uploaded_entries:
            try:
                batch_payload = {'photos': [
                    { 'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType'] }
                    for e in uploaded_entries
                ]}

                batch_resp = session.post(
                    f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos/batch",
                    json=batch_payload,
                    timeout=20,
                    verify=ca_bundle
                )

                if batch_resp.ok:
                    try:
                        resp_data = batch_resp.json()
                        registered = len(resp_data) if isinstance(resp_data, list) else len(uploaded_entries)
                    except Exception:
                        registered = len(uploaded_entries)
                    photo_count += registered
                    _dashboard_log(f"Batch registered {registered} photos for technician {dashboard_tech_id}")
                else:
                    _dashboard_log(f"Batch registration failed with status {batch_resp.status_code}; falling back to per-photo registration")
                    for e in uploaded_entries:
                        try:
                            photo_payload = {
                                'uploadURL': e['uploadURL'],
                                'category': e['category'],
                                'mimeType': e['mimeType']
                            }
                            try:
                                photo_resp = _retry_request(lambda: session.post(
                                    f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos",
                                    json=photo_payload,
                                    timeout=10,
                                    verify=ca_bundle
                                ), attempts=3, backoff_base=0.6)
                                photo_count += 1
                                _dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id}")
                            except Exception as reg_exc:
                                _dashboard_log(f"Photo registration failed for {e.get('path')}: {reg_exc}")
                                failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                        except Exception as exc:
                            _dashboard_log(f"Per-photo registration unexpected error: {exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(exc)})
            except Exception as exc:
                for e in uploaded_entries:
                    try:
                        photo_payload = {
                            'uploadURL': e['uploadURL'],
                            'category': e['category'],
                            'mimeType': e['mimeType']
                        }
                        try:
                            photo_resp = _retry_request(lambda: session.post(
                                f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos",
                                json=photo_payload,
                                timeout=10,
                                verify=ca_bundle
                            ), attempts=3, backoff_base=0.6)
                            photo_count += 1
                            _dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id} after batch error")
                        except Exception as reg_exc:
                            _dashboard_log(f"Per-photo registration failed for {e.get('path')} after batch error: {reg_exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                    except Exception as exc2:
                        failed_uploads.append({'path': e.get('path'), 'reason': str(exc2)})

        result = {"status": "created", "photo_count": photo_count}
        if failed_uploads:
            result['failed_uploads'] = failed_uploads
        return result
            
    except Exception as e:
        return {"error": str(e)}


def push_to_dashboard_single_request(record: dict, enrollment_id: int = None, endpoint_path="/api/external/technicians") -> dict:
    """
    Create technician and attach photos in a single request using the external
    API that accepts base64-embedded photos.

    Payload shape follows the external API specification. Photos are
    included as objects with `category` and `base64` (either data URL or raw
    base64). Enforces 10MB per photo limit.
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    if not dashboard_url:
        return {"error": "dashboard url not configured"}

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    tech_id = (record.get('tech_id') or record.get('techId') or '').upper()
    if not tech_id:
        return {"error": "missing tech_id"}

    is_new_hire = bool(record.get("is_new_hire", False))
    hire_status = "New Hire" if is_new_hire else "Existing Tech"
    
    payload = {
        "name": record.get("full_name") or record.get("name") or "",
        "techId": tech_id,
        "region": record.get("region") or record.get("state") or "",
        "district": record.get("district") or "",
        "enrollmentStatus": record.get("enrollmentStatus", "Enrolled"),
        "isNewHire": is_new_hire,
        "hireStatus": hire_status,
        "truckId": record.get("truckId") or record.get("truck_id") or record.get("truck_number") or "",
        "mobilePhoneNumber": record.get("mobilePhoneNumber") or record.get("mobile") or record.get("phone") or "",
        "techEmail": record.get("techEmail") or record.get("email") or "",
        "cityState": record.get("cityState") or "",
        "vinNumber": record.get("vin") or record.get("vinNumber") or "",
        "insuranceExpiration": _format_date(record.get("insurance_exp") or record.get("insuranceExpiration")) or "",
        "registrationExpiration": _format_date(record.get("registration_exp") or record.get("registrationExpiration")) or "",
    }

    if record.get('make'):
        payload['vehicleMake'] = record.get('make')
    if record.get('model'):
        payload['vehicleModel'] = record.get('model')
    if record.get('year'):
        payload['vehicleYear'] = record.get('year')
    industry_raw = record.get('industry') if record.get('industry') is not None else record.get('industries', [])
    if isinstance(industry_raw, (list, tuple)):
        payload['industry'] = ", ".join(industry_raw)
    elif industry_raw:
        payload['industry'] = str(industry_raw)
    date_started = _format_date(record.get('submission_date') or record.get('dateStartedByov'))
    if date_started:
        payload['dateStartedByov'] = date_started
    
    referred_by = record.get('referred_by') or record.get('referredBy') or ""
    if referred_by:
        payload['referredBy'] = referred_by

    docs = []
    try:
        if enrollment_id:
            docs = database.get_documents_for_enrollment(enrollment_id) or []
        else:
            docs = record.get('documents') or []
    except Exception:
        docs = record.get('documents') or []

    photos = []
    failed_photos = []
    MAX_BYTES = 10 * 1024 * 1024

    for d in docs:
        path = d.get('file_path') if isinstance(d, dict) else None
        category = d.get('doc_type') or d.get('category') or 'vehicle'
        if not path:
            failed_photos.append({'path': path, 'error': 'missing path'})
            continue
        
        if not file_storage.file_exists(path):
            failed_photos.append({'path': path, 'error': 'missing'})
            continue
        try:
            b = file_storage.read_file(path)
            size = len(b)
            if size > MAX_BYTES:
                failed_photos.append({'path': path, 'error': 'size_exceeded', 'size': size})
                continue
            
            file_hash = hashlib.md5(b).hexdigest()[:8]
            print(f"[DEBUG] Encoding photo: {os.path.basename(path)} | Category: {category} | Size: {size} | Hash: {file_hash}")
            
            raw_b64 = _b64.b64encode(b).decode('ascii')
            mime = _mimetypes.guess_type(path)[0] or 'application/octet-stream'
            if mime.startswith('image/') or mime == 'application/pdf':
                data_url = f"data:{mime};base64,{raw_b64}"
                photos.append({'category': category, 'base64': data_url})
            else:
                photos.append({'category': category, 'base64': raw_b64})
        except Exception as e:
            failed_photos.append({'path': path, 'error': str(e)})

    if photos:
        payload['photos'] = photos

    url = dashboard_url.rstrip('/') + endpoint_path
    try:
        resp = session.post(url, json=payload, timeout=30, verify=ca_bundle)
    except Exception as e:
        return {"error": f"request failed: {e}", "failed_photos": failed_photos}

    result = {"status_code": resp.status_code}
    try:
        resp_json = resp.json()
    except Exception:
        resp_json = {"raw_text": resp.text}
    result['response'] = resp_json
    result['photo_count'] = len(photos)
    if failed_photos:
        result['failed_photos'] = failed_photos

    tech_id_returned = None
    if isinstance(resp_json, dict):
        tech = resp_json.get('technician') or resp_json.get('technicianCreated') or resp_json
        if isinstance(tech, dict):
            tech_id_returned = tech.get('id') or tech.get('techId')
        else:
            tech_id_returned = resp_json.get('id') or resp_json.get('technicianId')

    if enrollment_id and tech_id_returned:
        try:
            report = {"photo_count": len(photos)}
            if failed_photos:
                report['failed_uploads'] = failed_photos
            report['response'] = resp_json
            database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=str(tech_id_returned), report=report)
        except Exception:
            pass

    if resp.status_code in (201, 207) or (200 <= resp.status_code < 300):
        return result
    else:
        return result


def pull_dashboard_data(tech_id: str = None) -> dict:
    """Fetch technician data from the dashboard.
    
    If tech_id is provided, fetches that specific technician.
    Otherwise, fetches all technicians.
    
    Returns: {success: bool, data: list|dict, error: str}
    """
    dashboard_url, username, password = _get_dashboard_credentials()
    
    if not dashboard_url:
        return {"success": False, "error": "dashboard url not configured"}
    
    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(
            f"{dashboard_url}/api/login",
            json={"username": username, "password": password},
            timeout=10,
            verify=ca_bundle
        )
        if not login_resp.ok:
            return {"success": False, "error": f"Login failed {login_resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Login exception: {e}"}
    
    try:
        params = {}
        if tech_id:
            params["techId"] = tech_id.upper()
        
        resp = session.get(
            f"{dashboard_url}/api/technicians",
            params=params,
            timeout=15,
            verify=ca_bundle
        )
        
        if resp.ok:
            try:
                data = resp.json()
                return {"success": True, "data": data}
            except Exception:
                return {"success": False, "error": "Failed to parse response"}
        else:
            return {"success": False, "error": f"Request failed {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def push_dashboard_update(updated_record: dict) -> dict:
    """Update an existing technician record on the dashboard.
    
    Uses PATCH or PUT to update technician data.
    
    Returns: {success: bool, error: str}
    """
    dashboard_url, username, password = _get_dashboard_credentials()
    
    if not dashboard_url:
        return {"success": False, "error": "dashboard url not configured"}
    
    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(
            f"{dashboard_url}/api/login",
            json={"username": username, "password": password},
            timeout=10,
            verify=ca_bundle
        )
        if not login_resp.ok:
            return {"success": False, "error": f"Login failed {login_resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Login exception: {e}"}
    
    dashboard_tech_id = updated_record.get('dashboard_tech_id') or updated_record.get('id')
    if not dashboard_tech_id:
        tech_id = (updated_record.get('tech_id') or updated_record.get('techId') or '').upper()
        if tech_id:
            try:
                check_resp = session.get(
                    f"{dashboard_url}/api/technicians",
                    params={"techId": tech_id},
                    timeout=10,
                    verify=ca_bundle
                )
                if check_resp.ok:
                    existing = check_resp.json()
                    if isinstance(existing, list) and existing:
                        dashboard_tech_id = existing[0].get('id')
            except Exception:
                pass
    
    if not dashboard_tech_id:
        return {"success": False, "error": "No dashboard technician ID found"}
    
    is_new_hire = bool(updated_record.get("is_new_hire", False))
    hire_status = "New Hire" if is_new_hire else "Existing Tech"
    
    industry_raw = updated_record.get('industry') if updated_record.get('industry') is not None else updated_record.get('industries', [])
    if isinstance(industry_raw, list):
        industry = ", ".join(industry_raw) if industry_raw else ""
    else:
        industry = str(industry_raw) if industry_raw else ""
    
    payload = {
        "name": updated_record.get("full_name") or updated_record.get("name"),
        "techId": (updated_record.get("tech_id") or updated_record.get("techId") or "").upper(),
        "region": updated_record.get("state") or updated_record.get("region"),
        "district": updated_record.get("district"),
        "referredBy": updated_record.get('referred_by') or updated_record.get('referredBy') or "",
        "enrollmentStatus": updated_record.get("enrollmentStatus", "Enrolled"),
        "isNewHire": is_new_hire,
        "hireStatus": hire_status,
        "truckId": updated_record.get("truck_number") or updated_record.get("truckId") or "",
        "vinNumber": updated_record.get("vin") or updated_record.get("vinNumber"),
        "vehicleMake": updated_record.get("make") or updated_record.get("vehicleMake"),
        "vehicleModel": updated_record.get("model") or updated_record.get("vehicleModel"),
        "vehicleYear": updated_record.get("year") or updated_record.get("vehicleYear"),
        "industry": industry,
        "insuranceExpiration": _format_date(updated_record.get("insurance_exp") or updated_record.get("insuranceExpiration")),
        "registrationExpiration": _format_date(updated_record.get("registration_exp") or updated_record.get("registrationExpiration"))
    }
    
    payload = {k: v for k, v in payload.items() if v is not None}
    
    try:
        resp = session.patch(
            f"{dashboard_url}/api/technicians/{dashboard_tech_id}",
            json=payload,
            timeout=15,
            verify=ca_bundle
        )
        
        if not resp.ok:
            resp = session.put(
                f"{dashboard_url}/api/technicians/{dashboard_tech_id}",
                json=payload,
                timeout=15,
                verify=ca_bundle
            )
        
        if resp.ok:
            return {"success": True}
        else:
            return {"success": False, "error": f"Update failed {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_technician_on_dashboard(record: dict) -> dict:
    """Create a technician on the external dashboard using admin credentials.

    Returns: {status: 'created'|'exists', dashboard_tech_id: str, error: str}
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    submission_date = record.get("submission_date", "")
    date_started = _format_date(submission_date) or datetime.now().strftime("%Y-%m-%d")

    tech_id = (record.get('tech_id') or '').upper()
    if not tech_id:
        return {"error": "missing tech_id"}

    industry_raw = record.get('industry') if record.get('industry') is not None else record.get('industries', [])
    if isinstance(industry_raw, list):
        industry = ", ".join(industry_raw) if industry_raw else ""
    else:
        industry = str(industry_raw) if industry_raw else ""

    referred_by_val = record.get('referred_by') or record.get('referredBy') or ""

    payload = {
        "name": record.get("full_name"),
        "techId": tech_id,
        "region": record.get("state"),
        "district": record.get("district"),
        "referredBy": referred_by_val,
        "enrollmentStatus": "Enrolled",
        "dateStartedByov": date_started,
        "vinNumber": record.get("vin"),
        "vehicleMake": record.get("make"),
        "vehicleModel": record.get("model"),
        "vehicleYear": record.get("year"),
        "industry": industry,
        "insuranceExpiration": _format_date(record.get("insurance_exp")),
        "registrationExpiration": _format_date(record.get("registration_exp"))
    }

    try:
        create_resp = session.post(f"{dashboard_url}/api/technicians", json=payload, timeout=15, verify=ca_bundle)
        if not (200 <= create_resp.status_code < 300):
            return {"error": f"create responded {create_resp.status_code}", "body": create_resp.text[:200]}
        try:
            data = create_resp.json()
            dashboard_tech_id = data.get('id')
        except Exception:
            return {"error": "failed to parse create response"}
        if not dashboard_tech_id:
            return {"error": "no id returned"}
        return {"status": "created", "dashboard_tech_id": dashboard_tech_id}
    except Exception as e:
        return {"error": str(e)}


def upload_photos_for_technician(enrollment_id: int, dashboard_tech_id: str = None) -> dict:
    """Upload photos for a given enrollment to the dashboard technician id.

    If `dashboard_tech_id` is not provided, attempts to look up by tech_id on the dashboard.
    Returns: {photo_count: int, failed_uploads: [...]}
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    try:
        record = database.get_enrollment_by_id(enrollment_id)
    except Exception:
        record = None

    if not record:
        return {"error": "enrollment not found"}

    tech_id = (record.get('tech_id') or '').upper()
    if not dashboard_tech_id:
        try:
            check_resp = session.get(f"{dashboard_url}/api/technicians", params={"techId": tech_id}, timeout=10, verify=ca_bundle)
            if check_resp.ok:
                try:
                    existing = check_resp.json()
                    if isinstance(existing, list) and existing:
                        dashboard_tech_id = existing[0].get('id')
                except Exception:
                    pass
        except Exception:
            pass

    if not dashboard_tech_id:
        return {"error": "dashboard technician id not provided and lookup failed"}

    photo_count = 0
    failed_uploads = []

    try:
        docs = database.get_documents_for_enrollment(enrollment_id)
        vehicle_paths = [d['file_path'] for d in docs if d['doc_type'] == 'vehicle']
        insurance_paths = [d['file_path'] for d in docs if d['doc_type'] == 'insurance']
        registration_paths = [d['file_path'] for d in docs if d['doc_type'] == 'registration']
    except Exception:
        vehicle_paths = record.get('vehicle_photos_paths', []) or []
        insurance_paths = record.get('insurance_docs_paths', []) or []
        registration_paths = record.get('registration_docs_paths', []) or []

    category_to_paths = {
        'vehicle': vehicle_paths,
        'insurance': insurance_paths,
        'registration': registration_paths
    }

    uploaded_entries = []
    for category, paths in category_to_paths.items():
        for photo_path in (paths or []):
            if not photo_path or not os.path.exists(photo_path):
                failed_uploads.append({'path': photo_path, 'reason': 'missing'})
                continue
            try:
                try:
                    upload_req = _retry_request(lambda: session.post(
                        f"{dashboard_url}/api/objects/upload",
                        json={"category": category},
                        timeout=10,
                        verify=ca_bundle
                    ), attempts=3, backoff_base=0.6)
                except Exception as e:
                    _dashboard_log(f"Failed to get upload URL for {photo_path}: {e}")
                    failed_uploads.append({'path': photo_path, 'reason': str(e)})
                    continue

                upload_data = upload_req.json()
                gcs_url = upload_data.get("uploadURL")
                if not gcs_url:
                    _dashboard_log(f"No uploadURL returned for {photo_path}: {upload_data}")
                    failed_uploads.append({'path': photo_path, 'reason': 'no_upload_url'})
                    continue

                mime_type, _ = guess_type(photo_path)
                if not mime_type:
                    mime_type = 'application/octet-stream'

                try:
                    def do_put():
                        with open(photo_path, 'rb') as f:
                            r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60, verify=ca_bundle)
                            return r
                    gcs_resp = _retry_request(do_put, attempts=3, backoff_base=0.6)
                except Exception as e:
                    _dashboard_log(f"GCS PUT failed for {photo_path}: {e}")
                    failed_uploads.append({'path': photo_path, 'reason': str(e)})
                    continue

                _dashboard_log(f"Uploaded {photo_path} to GCS: {gcs_url}")
                uploaded_entries.append({'uploadURL': gcs_url, 'category': category, 'mimeType': mime_type, 'path': photo_path})
            except Exception as exc:
                _dashboard_log(f"Unexpected error handling {photo_path}: {exc}")
                failed_uploads.append({'path': photo_path, 'reason': str(exc)})
                continue

    if uploaded_entries:
        try:
            batch_payload = {'photos': [ {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']} for e in uploaded_entries ]}
            batch_resp = session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos/batch", json=batch_payload, timeout=20, verify=ca_bundle)
            if batch_resp.ok:
                try:
                    resp_data = batch_resp.json()
                    registered = len(resp_data) if isinstance(resp_data, list) else len(uploaded_entries)
                except Exception:
                    registered = len(uploaded_entries)
                photo_count += registered
                _dashboard_log(f"Batch registered {registered} photos for technician {dashboard_tech_id}")
            else:
                _dashboard_log(f"Batch registration failed with status {batch_resp.status_code}; falling back to per-photo registration")
                for e in uploaded_entries:
                    try:
                        photo_payload = {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']}
                        try:
                            photo_resp = _retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos", json=photo_payload, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
                            photo_count += 1
                            _dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id}")
                        except Exception as reg_exc:
                            _dashboard_log(f"Photo registration failed for {e.get('path')}: {reg_exc}")
                            failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                    except Exception as exc:
                        _dashboard_log(f"Per-photo registration unexpected error: {exc}")
                        failed_uploads.append({'path': e.get('path'), 'reason': str(exc)})
        except Exception as exc:
            for e in uploaded_entries:
                try:
                    photo_payload = {'uploadURL': e['uploadURL'], 'category': e['category'], 'mimeType': e['mimeType']}
                    try:
                        photo_resp = _retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_tech_id}/photos", json=photo_payload, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
                        photo_count += 1
                        _dashboard_log(f"Registered photo {e.get('path')} for tech {dashboard_tech_id} after batch error")
                    except Exception as reg_exc:
                        _dashboard_log(f"Per-photo registration failed for {e.get('path')} after batch error: {reg_exc}")
                        failed_uploads.append({'path': e.get('path'), 'reason': str(reg_exc)})
                except Exception as exc2:
                    failed_uploads.append({'path': e.get('path'), 'reason': str(exc2)})

    report = {"photo_count": photo_count}
    if failed_uploads:
        report['failed_uploads'] = failed_uploads

    try:
        database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=dashboard_tech_id, report=report)
    except Exception:
        pass

    result = {"photo_count": photo_count}
    if failed_uploads:
        result['failed_uploads'] = failed_uploads
    return result


def retry_failed_uploads(enrollment_id: int) -> dict:
    """Retry previously failed photo uploads recorded in `last_upload_report`.

    Returns: {retried_count: int, remaining_failed: int, still_failed: [...]} 
    """
    dashboard_url, username, password = _get_dashboard_credentials()

    session, ca_bundle = _create_dashboard_session()
    try:
        login_resp = session.post(f"{dashboard_url}/api/login", json={"username": username, "password": password}, timeout=10, verify=ca_bundle)
        if not login_resp.ok:
            return {"error": f"Login failed {login_resp.status_code}", "body": login_resp.text[:200]}
    except Exception as e:
        return {"error": f"Login exception: {e}"}

    try:
        record = database.get_enrollment_by_id(enrollment_id)
    except Exception:
        record = None
    if not record:
        return {"error": "enrollment not found"}

    dashboard_id = record.get('dashboard_tech_id')
    tech_id = (record.get('tech_id') or '').upper()
    if not dashboard_id:
        try:
            check_resp = session.get(f"{dashboard_url}/api/technicians", params={"techId": tech_id}, timeout=10, verify=ca_bundle)
            if check_resp.ok:
                try:
                    existing = check_resp.json()
                    if isinstance(existing, list) and existing:
                        dashboard_id = existing[0].get('id')
                except Exception:
                    pass
        except Exception:
            pass

    if not dashboard_id:
        return {"error": "dashboard technician id not found"}

    last_report = record.get('last_upload_report')
    if not last_report:
        return {"error": "no last_upload_report available"}
    try:
        if isinstance(last_report, str):
            report_obj = json.loads(last_report)
        else:
            report_obj = last_report
    except Exception:
        report_obj = last_report if isinstance(last_report, dict) else {}

    failed = report_obj.get('failed_uploads', []) if isinstance(report_obj, dict) else []
    if not failed:
        return {"retried_count": 0, "remaining_failed": 0}

    try:
        docs = database.get_documents_for_enrollment(enrollment_id)
        path_to_category = {d.get('file_path'): d.get('doc_type') for d in docs}
    except Exception:
        path_to_category = {}

    retried = 0
    still_failed = []

    for entry in failed:
        path = entry.get('path') if isinstance(entry, dict) else None
        if not path or not os.path.exists(path):
            still_failed.append({'path': path, 'reason': 'missing'})
            continue

        category = path_to_category.get(path, 'vehicle')
        try:
            try:
                upload_req = _retry_request(lambda: session.post(f"{dashboard_url}/api/objects/upload", json={"category": category}, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
            except Exception as e:
                _dashboard_log(f"Failed to get upload URL for {path}: {e}")
                still_failed.append({'path': path, 'reason': str(e)})
                continue

            upload_data = upload_req.json()
            gcs_url = upload_data.get('uploadURL')
            if not gcs_url:
                _dashboard_log(f"No uploadURL returned for {path}: {upload_data}")
                still_failed.append({'path': path, 'reason': 'no_upload_url'})
                continue

            mime_type, _ = guess_type(path)
            if not mime_type:
                mime_type = 'application/octet-stream'

            try:
                def do_put():
                    with open(path, 'rb') as f:
                        r = requests.put(gcs_url, data=f, headers={"Content-Type": mime_type}, timeout=60, verify=ca_bundle)
                        return r
                gcs_resp = _retry_request(do_put, attempts=3, backoff_base=0.6)
            except Exception as e:
                _dashboard_log(f"GCS PUT failed for {path}: {e}")
                still_failed.append({'path': path, 'reason': str(e)})
                continue

            try:
                photo_payload = {'uploadURL': gcs_url, 'category': category, 'mimeType': mime_type}
                try:
                    reg_resp = _retry_request(lambda: session.post(f"{dashboard_url}/api/technicians/{dashboard_id}/photos", json=photo_payload, timeout=10, verify=ca_bundle), attempts=3, backoff_base=0.6)
                    retried += 1
                    _dashboard_log(f"Retried and registered photo {path} for tech {dashboard_id}")
                except Exception as reg_exc:
                    _dashboard_log(f"Photo registration failed for {path}: {reg_exc}")
                    still_failed.append({'path': path, 'reason': str(reg_exc)})
            except Exception as exc:
                _dashboard_log(f"Unexpected registration error for {path}: {exc}")
                still_failed.append({'path': path, 'reason': str(exc)})

        except Exception as exc:
            _dashboard_log(f"Unexpected error retrying {path}: {exc}")
            still_failed.append({'path': path, 'reason': str(exc)})

    new_photo_count = (report_obj.get('photo_count', 0) if isinstance(report_obj, dict) else 0) + retried
    new_report = {"photo_count": new_photo_count}
    if still_failed:
        new_report['failed_uploads'] = still_failed

    try:
        database.set_dashboard_sync_info(enrollment_id, dashboard_tech_id=dashboard_id, report=new_report)
    except Exception:
        pass

    return {"retried_count": retried, "remaining_failed": len(still_failed), "still_failed": still_failed}


# Alias for backwards compatibility with admin_dashboard.py imports
post_to_dashboard_single_request = push_to_dashboard_single_request


# Cache clearing helper - this clears Streamlit cache when enrollment data changes
def clear_enrollment_cache():
    """Clear any cached enrollment data. 
    
    This should be called after approving, deleting, or modifying enrollments
    to ensure the admin dashboard shows fresh data.
    """
    import streamlit as st
    
    # Clear all Streamlit caches to ensure fresh data
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
