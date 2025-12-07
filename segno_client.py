"""
Segno API client for syncing BYOV enrollments to Sears Drive Enrollment system.
Handles authentication, session management, and enrollment submission.
"""
import os
import requests
from typing import Dict, Any, Optional
from datetime import datetime

SEGNO_BASE_URL = os.environ.get("SEGNO_BASE_URL", "https://workflow.segnosystems.com/")
SEGNO_USERNAME = os.environ.get("SEGNO_USERNAME", "")
SEGNO_PASSWORD = os.environ.get("SEGNO_PASSWORD", "")

class SegnoClient:
    """Client for interacting with Segno workflow system."""
    
    def __init__(self):
        self.base_url = SEGNO_BASE_URL.rstrip("/")
        self.username = SEGNO_USERNAME
        self.password = SEGNO_PASSWORD
        self.session = requests.Session()
        self.authenticated = False
    
    def login(self) -> bool:
        """Authenticate with Segno and store session cookie."""
        if not self.username or not self.password:
            print("[Segno] Missing SEGNO_USERNAME or SEGNO_PASSWORD")
            return False
        
        try:
            # First, get the login page to establish a session
            self.session.get(
                f"{self.base_url}/index.php?module=Users&action=Login",
                timeout=30
            )
            
            login_data = {
                "module": "Users",
                "action": "Authenticate",
                "return_module": "Users",
                "return_action": "Login",
                "user_name": self.username,
                "user_password": self.password,
            }
            
            response = self.session.post(
                f"{self.base_url}/index.php",
                data=login_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": self.base_url,
                    "Referer": f"{self.base_url}/index.php?module=Users&action=Login",
                },
                timeout=30,
                allow_redirects=True
            )
            
            # Debug: print cookies
            cookies = dict(self.session.cookies)
            print(f"[Segno] Cookies after login: {list(cookies.keys())}")
            
            # Check for successful login indicators
            if response.status_code == 200:
                # Check if we're NOT on a login page
                if "action=Login" not in response.url or "module=Home" in response.url:
                    self.authenticated = True
                    print(f"[Segno] Login successful, redirected to: {response.url[:80]}")
                    return True
                # Check page content for login success
                if "logout" in response.text.lower() or "dashboard" in response.text.lower():
                    self.authenticated = True
                    print("[Segno] Login successful (found dashboard/logout in page)")
                    return True
                # If we got PHPSESSID cookie, assume success
                if "PHPSESSID" in cookies:
                    self.authenticated = True
                    print("[Segno] Login response received with session cookie")
                    return True
                    
                print(f"[Segno] Login may have failed, URL: {response.url[:80]}")
                return False
            
            print(f"[Segno] Login failed with status {response.status_code}")
            return False
            
        except Exception as e:
            print(f"[Segno] Login error: {e}")
            return False
    
    def _ensure_authenticated(self) -> bool:
        """Ensure we have a valid session, re-login if needed."""
        if not self.authenticated:
            return self.login()
        return True
    
    def _format_date(self, date_str: Optional[str]) -> str:
        """Convert date string to MM/DD/YYYY format for Segno."""
        if not date_str:
            return ""
        
        try:
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y"]:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime("%m/%d/%Y")
                except ValueError:
                    continue
            return date_str
        except Exception:
            return date_str or ""
    
    def _map_industries_to_flags(self, industries: Any) -> Dict[str, str]:
        """Map our industry list to Segno product flags."""
        flags = {
            "cook": "0",
            "dish": "0",
            "mw": "0",
            "wh": "0",
            "hvac": "0",
            "ref": "0",
            "l": "0",
            "lg": "0",
            "pmt": "0",
            "apt": "0",
        }
        
        if not industries:
            return flags
        
        if isinstance(industries, str):
            try:
                import json
                industries = json.loads(industries)
            except:
                industries = [industries]
        
        industry_map = {
            "cooking": "cook",
            "cook": "cook",
            "dishwasher": "dish",
            "dish": "dish",
            "microwave": "mw",
            "mw": "mw",
            "washer": "wh",
            "water heater": "wh",
            "wh": "wh",
            "hvac": "hvac",
            "heating": "hvac",
            "cooling": "hvac",
            "refrigeration": "ref",
            "refrigerator": "ref",
            "ref": "ref",
            "laundry": "l",
            "l": "l",
            "lg": "lg",
            "pmt": "pmt",
            "apt": "apt",
            "appliance": "apt",
        }
        
        for industry in industries:
            if isinstance(industry, str):
                key = industry.lower().strip()
                if key in industry_map:
                    flags[industry_map[key]] = "1"
                elif key in flags:
                    flags[key] = "1"
        
        return flags
    
    def submit_enrollment(self, enrollment: Dict[str, Any], retry_count: int = 0) -> Dict[str, Any]:
        """
        Submit an enrollment to Segno Sears_Drive_Enrolment module.
        
        Args:
            enrollment: Full enrollment record from our database
            retry_count: Internal counter to prevent infinite retries
            
        Returns:
            dict with success, status_code, error, segno_record_id
        """
        if not self._ensure_authenticated():
            return {
                "success": False,
                "status_code": 401,
                "error": "Failed to authenticate with Segno",
                "segno_record_id": None
            }
        
        try:
            industry_flags = self._map_industries_to_flags(
                enrollment.get("industries") or enrollment.get("industry")
            )
            
            today = datetime.now().strftime("%m/%d/%Y")
            
            # Map employment status to Segno enrollment type
            is_new_hire = enrollment.get("is_new_hire", False)
            enrolment_type = "new" if is_new_hire else "existing"
            
            form_data = {
                "module": "Sears_Drive_Enrolment",
                "action": "Submit",
                "record": "",
                "return_module": "Sears_Drive_Enrolment",
                "return_action": "DetailView",
                "return_id": "",
                "relate_to": "Sears_Drive_Enrolment",
                "relate_id": "",
                "isDuplicate": "false",
                "offset": "1",
                "associate": enrollment.get("full_name", ""),
                "enrolment_type": enrolment_type,
                "enrolment_status": "enrolled",
                "vehicle_year": str(enrollment.get("year", "")),
                "vehicle_make": enrollment.get("make", ""),
                "vehicle_model": enrollment.get("model", ""),
                "vehicle_cargo": "20",
                "insurance_expiration_date": self._format_date(enrollment.get("insurance_exp")),
                "registration_expiration_date": self._format_date(enrollment.get("registration_exp")),
                "start_date": today,
                "reffered_by": enrollment.get("refered_by") or enrollment.get("referred_by") or "Tyler Morgan",
                "mileage_rate": "0.57",
            }
            
            print(f"[Segno] Submitting enrollment for {enrollment.get('full_name', 'Unknown')}")
            
            response = self.session.post(
                f"{self.base_url}/index.php",
                data=form_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
                allow_redirects=True
            )
            
            print(f"[Segno] Response status: {response.status_code}, URL: {response.url[:100]}")
            
            # Check for session expiration - only if explicitly redirected to login page
            # and we haven't already retried
            is_login_redirect = (
                response.status_code == 401 or 
                ("action=Login" in response.url and "module=Users" in response.url)
            )
            
            if is_login_redirect and retry_count < 1:
                print("[Segno] Session expired, re-authenticating (attempt 1)...")
                self.authenticated = False
                if self.login():
                    return self.submit_enrollment(enrollment, retry_count + 1)
                else:
                    return {
                        "success": False,
                        "status_code": 401,
                        "error": "Session expired and re-authentication failed",
                        "segno_record_id": None
                    }
            elif is_login_redirect:
                return {
                    "success": False,
                    "status_code": 401,
                    "error": "Authentication failed after retry",
                    "segno_record_id": None
                }
            
            if response.status_code == 200:
                segno_id = None
                import re
                # Try to extract record ID from URL
                if "record=" in response.url:
                    match = re.search(r'record=([a-f0-9-]+)', response.url)
                    if match:
                        segno_id = match.group(1)
                
                # Also check response body for record ID
                if not segno_id:
                    match = re.search(r'record["\s:=]+([a-f0-9-]{36})', response.text)
                    if match:
                        segno_id = match.group(1)
                
                print(f"[Segno] Enrollment submitted successfully. Record ID: {segno_id}")
                return {
                    "success": True,
                    "status_code": 200,
                    "error": None,
                    "segno_record_id": segno_id
                }
            
            return {
                "success": False,
                "status_code": response.status_code,
                "error": f"Unexpected response status: {response.status_code}",
                "segno_record_id": None
            }
            
        except requests.Timeout:
            return {
                "success": False,
                "status_code": 408,
                "error": "Request timed out",
                "segno_record_id": None
            }
        except Exception as e:
            print(f"[Segno] Submit error: {e}")
            return {
                "success": False,
                "status_code": 500,
                "error": str(e),
                "segno_record_id": None
            }


_client_instance: Optional[SegnoClient] = None

def get_segno_client() -> SegnoClient:
    """Get or create the singleton Segno client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = SegnoClient()
    return _client_instance


def submit_enrollment_to_segno(enrollment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Submit an enrollment to Segno.
    
    Args:
        enrollment: Full enrollment record from our database
        
    Returns:
        dict with success, status_code, error, segno_record_id
    """
    client = get_segno_client()
    return client.submit_enrollment(enrollment)


def sync_enrollment_by_id(enrollment_id: int) -> Dict[str, Any]:
    """
    Look up enrollment by ID and sync to Segno.
    Updates database with sync status.
    
    Args:
        enrollment_id: Our internal enrollment ID
        
    Returns:
        dict with success, status_code, error, segno_record_id
    """
    try:
        import database_pg as database
        
        enrollment = database.get_enrollment(enrollment_id)
        if not enrollment:
            return {
                "success": False,
                "status_code": 404,
                "error": f"Enrollment {enrollment_id} not found",
                "segno_record_id": None
            }
        
        result = submit_enrollment_to_segno(enrollment)
        
        if result["success"]:
            database.update_segno_status(enrollment_id, "synced", result.get("segno_record_id"))
        else:
            database.update_segno_status(enrollment_id, "failed", None)
        
        return result
        
    except Exception as e:
        print(f"[Segno] sync_enrollment_by_id error: {e}")
        return {
            "success": False,
            "status_code": 500,
            "error": str(e),
            "segno_record_id": None
        }
