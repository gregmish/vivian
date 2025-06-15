import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
import hashlib
import secrets

AUTH_DIR = Path("auth")
USER_FILE = AUTH_DIR / "users.json"
SESSION_FILE = AUTH_DIR / "sessions.json"
INVITE_FILE = AUTH_DIR / "invites.json"
RESET_FILE = AUTH_DIR / "resets.json"

DEFAULT_USER_DATA = {
    "created": None,
    "token": None,
    "prefs": {},
    "roles": ["user"],
    "locked": False,
    "deleted": False,
    "deleted_at": None,
    "profile": {"name": "", "avatar": "", "bio": "", "email": "", "verified": False},
    "groups": [],
    "audit": [],
    "password_hash": "",
    "password_reset_required": False,
    "consent": {},
    "oauth": {},
    "last_login": None,
    "login_history": [],
    "failed_logins": 0,
    "2fa_enabled": False,
    "2fa_secret": "",
    "api_tokens": [],
    "invited_by": None
}
SESSION_EXPIRY_HOURS = 24
PASSWORD_RESET_EXPIRY_HOURS = 2
INVITE_EXPIRY_HOURS = 48
MAX_FAILED_LOGINS = 5
LOCKOUT_TIME_MINUTES = 30

def hash_password(password: str, salt: Optional[str] = None) -> str:
    if not salt:
        salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f"{salt}${pwd_hash.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        salt, hashval = hashed.split('$')
        return hash_password(password, salt) == hashed
    except Exception:
        return False

def generate_token(prefix="TOK") -> str:
    return f"{prefix}-{secrets.token_hex(16)}"

def now_iso() -> str:
    return datetime.utcnow().isoformat()

class UserManager:
    def __init__(self):
        AUTH_DIR.mkdir(parents=True, exist_ok=True)
        self.users: Dict[str, Dict] = {}
        self.sessions: Dict[str, Dict] = {}  # session_id -> {user, started, ip, ...}
        self.invites: Dict[str, Dict] = {}
        self.resets: Dict[str, Dict] = {}
        self.load_users()
        self.load_sessions()
        self.load_invites()
        self.load_resets()

    def _repair_user(self, user):
        for k, v in DEFAULT_USER_DATA.items():
            if k not in user:
                user[k] = v() if callable(v) else (v.copy() if isinstance(v, dict) else v)

    def save_users(self):
        try:
            with USER_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=4)
        except Exception as e:
            logging.error(f"[Auth] Failed to save users: {e}")

    def save_sessions(self):
        try:
            with SESSION_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.sessions, f, indent=4)
        except Exception as e:
            logging.error(f"[Auth] Failed to save sessions: {e}")

    def save_invites(self):
        try:
            with INVITE_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.invites, f, indent=4)
        except Exception as e:
            logging.error(f"[Auth] Failed to save invites: {e}")

    def save_resets(self):
        try:
            with RESET_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.resets, f, indent=4)
        except Exception as e:
            logging.error(f"[Auth] Failed to save resets: {e}")

    def load_users(self):
        if USER_FILE.exists():
            try:
                with USER_FILE.open("r", encoding="utf-8") as f:
                    self.users = json.load(f)
                for u in self.users.values():
                    self._repair_user(u)
                logging.info("[Auth] Loaded user data.")
            except Exception as e:
                logging.error(f"[Auth] Failed to load users: {e}")
                self.users = {}
        else:
            self.save_users()

    def load_sessions(self):
        if SESSION_FILE.exists():
            try:
                with SESSION_FILE.open("r", encoding="utf-8") as f:
                    self.sessions = json.load(f)
                logging.info("[Auth] Loaded session data.")
            except Exception as e:
                logging.error(f"[Auth] Failed to load sessions: {e}")
                self.sessions = {}
        else:
            self.save_sessions()

    def load_invites(self):
        if INVITE_FILE.exists():
            try:
                with INVITE_FILE.open("r", encoding="utf-8") as f:
                    self.invites = json.load(f)
            except Exception as e:
                logging.error(f"[Auth] Failed to load invites: {e}")
                self.invites = {}
        else:
            self.save_invites()

    def load_resets(self):
        if RESET_FILE.exists():
            try:
                with RESET_FILE.open("r", encoding="utf-8") as f:
                    self.resets = json.load(f)
            except Exception as e:
                logging.error(f"[Auth] Failed to load resets: {e}")
                self.resets = {}
        else:
            self.save_resets()

    # --- User Management ---

    def create_user(self, username: str, password: Optional[str] = None, roles: Optional[list] = None, invited_by: Optional[str] = None):
        if username in self.users:
            return False
        self.users[username] = DEFAULT_USER_DATA.copy()
        self.users[username]["created"] = now_iso()
        self.users[username]["token"] = generate_token()
        self.users[username]["roles"] = roles if roles else ["user"]
        if password:
            self.users[username]["password_hash"] = hash_password(password)
        self.users[username]["invited_by"] = invited_by
        self.users[username]["audit"].append({"event": "created", "at": now_iso(), "by": invited_by})
        self.save_users()
        logging.info(f"[Auth] User created: {username}")
        return True

    def set_password(self, username: str, password: str):
        if username in self.users:
            self.users[username]["password_hash"] = hash_password(password)
            self.users[username]["audit"].append({"event": "password_set", "at": now_iso()})
            self.save_users()
            return True
        return False

    def verify_password(self, username: str, password: str) -> bool:
        user = self.users.get(username)
        return user and user.get("password_hash") and verify_password(password, user["password_hash"])

    def request_password_reset(self, username: str) -> Optional[str]:
        if username in self.users:
            token = generate_token("RESET")
            self.resets[token] = {
                "user": username,
                "requested": now_iso(),
                "expires": (datetime.utcnow() + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS)).isoformat()
            }
            self.save_resets()
            # Here you would trigger a notification/email
            return token
        return None

    def reset_password(self, token: str, new_password: str) -> bool:
        reset = self.resets.get(token)
        if not reset:
            return False
        expires = datetime.fromisoformat(reset["expires"])
        if datetime.utcnow() > expires:
            del self.resets[token]
            self.save_resets()
            return False
        username = reset["user"]
        self.set_password(username, new_password)
        del self.resets[token]
        self.save_resets()
        return True

    def verify_token(self, token: str) -> Optional[str]:
        for user, data in self.users.items():
            if data.get("token") == token and not data.get("locked", False) and not data.get("deleted", False):
                return user
        return None

    def user_exists(self, username: str) -> bool:
        return username in self.users and not self.users[username].get("deleted", False)

    def list_users(self, role: Optional[str] = None, active: bool = True) -> list:
        users = [
            u for u, d in self.users.items()
            if (not role or role in d.get("roles", [])) and (not active or not d.get("deleted", False))
        ]
        return users

    def delete_user(self, username: str, hard: bool = False):
        if username in self.users:
            if hard:
                del self.users[username]
            else:
                self.users[username]["deleted"] = True
                self.users[username]["deleted_at"] = now_iso()
            self.save_users()
            logging.info(f"[Auth] User deleted: {username}")
            return True
        return False

    def lock_user(self, username: str):
        if username in self.users:
            self.users[username]["locked"] = True
            self.users[username]["audit"].append({"event": "locked", "at": now_iso()})
            self.save_users()
            return True
        return False

    def unlock_user(self, username: str):
        if username in self.users:
            self.users[username]["locked"] = False
            self.users[username]["failed_logins"] = 0
            self.users[username]["audit"].append({"event": "unlocked", "at": now_iso()})
            self.save_users()
            return True
        return False

    def rename_user(self, old_username: str, new_username: str):
        if old_username in self.users and new_username not in self.users:
            self.users[new_username] = self.users.pop(old_username)
            self.save_users()
            return True
        return False

    def set_user_pref(self, username: str, key: str, value: Any):
        if username in self.users:
            self.users[username]["prefs"][key] = value
            self.users[username]["audit"].append({"event": "set_pref", "key": key, "at": now_iso()})
            self.save_users()

    def get_user_pref(self, username: str, key: str, default=None):
        return self.users.get(username, {}).get("prefs", {}).get(key, default)

    def add_to_group(self, username: str, group: str):
        if username in self.users and group not in self.users[username]["groups"]:
            self.users[username]["groups"].append(group)
            self.save_users()

    def remove_from_group(self, username: str, group: str):
        if username in self.users and group in self.users[username]["groups"]:
            self.users[username]["groups"].remove(group)
            self.save_users()

    def record_consent(self, username: str, policy: str, value: bool):
        if username in self.users:
            self.users[username]["consent"][policy] = {"accepted": value, "at": now_iso()}
            self.save_users()

    def get_consent(self, username: str, policy: str):
        return self.users.get(username, {}).get("consent", {}).get(policy, None)

    def update_profile(self, username: str, **kwargs):
        if username in self.users:
            self.users[username]["profile"].update(kwargs)
            self.save_users()

    def record_login(self, username: str, ip: str = "", location: str = ""):
        if username in self.users:
            now = now_iso()
            self.users[username]["last_login"] = now
            self.users[username]["login_history"].append({"at": now, "ip": ip, "location": location})
            self.save_users()

    # --- Session Management ---

    def start_session(self, username: str, ip: Optional[str] = None) -> str:
        session_id = generate_token("SESS")
        session_data = {
            "user": username,
            "started": now_iso(),
            "ip": ip or "",
        }
        self.sessions[session_id] = session_data
        self.save_sessions()
        return session_id

    def get_user_from_session(self, session_id: str) -> Optional[str]:
        session = self.sessions.get(session_id)
        if not session:
            return None
        started = datetime.fromisoformat(session["started"])
        if datetime.utcnow() - started > timedelta(hours=SESSION_EXPIRY_HOURS):
            del self.sessions[session_id]
            self.save_sessions()
            return None
        return session["user"]

    def end_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.save_sessions()

    def end_all_sessions(self, username: str):
        session_ids = [sid for sid, s in self.sessions.items() if s["user"] == username]
        for sid in session_ids:
            del self.sessions[sid]
        self.save_sessions()

    def prune_expired_sessions(self):
        expired = []
        now = datetime.utcnow()
        for sid, session in list(self.sessions.items()):
            started = datetime.fromisoformat(session["started"])
            if now - started > timedelta(hours=SESSION_EXPIRY_HOURS):
                expired.append(sid)
        for sid in expired:
            del self.sessions[sid]
        if expired:
            self.save_sessions()
            logging.info(f"[Auth] Pruned {len(expired)} expired sessions.")

    # --- Invitation System ---

    def invite_user(self, email: str, invited_by: str) -> Optional[str]:
        code = generate_token("INVITE")
        self.invites[code] = {
            "email": email,
            "invited_by": invited_by,
            "created": now_iso(),
            "expires": (datetime.utcnow() + timedelta(hours=INVITE_EXPIRY_HOURS)).isoformat()
        }
        self.save_invites()
        # Here you would send an email/notification
        return code

    def verify_invite(self, code: str) -> Optional[Dict]:
        invite = self.invites.get(code)
        if not invite:
            return None
        expires = datetime.fromisoformat(invite["expires"])
        if datetime.utcnow() > expires:
            del self.invites[code]
            self.save_invites()
            return None
        return invite

    def accept_invite(self, code: str, username: str, password: str):
        invite = self.verify_invite(code)
        if invite:
            self.create_user(username, password=password, invited_by=invite["invited_by"])
            del self.invites[code]
            self.save_invites()
            return True
        return False

    # --- API Token Management ---

    def create_api_token(self, username: str, scope: str = "user", expires_in_hours: int = 168) -> Optional[str]:
        if username not in self.users:
            return None
        token = generate_token("API")
        expires = (datetime.utcnow() + timedelta(hours=expires_in_hours)).isoformat()
        self.users[username]["api_tokens"].append({"token": token, "scope": scope, "created": now_iso(), "expires": expires})
        self.save_users()
        return token

    def verify_api_token(self, token: str) -> Optional[str]:
        for user, data in self.users.items():
            for tok in data.get("api_tokens", []):
                if tok["token"] == token and datetime.utcnow() < datetime.fromisoformat(tok["expires"]):
                    return user
        return None

    def revoke_api_token(self, username: str, token: str):
        if username in self.users:
            self.users[username]["api_tokens"] = [
                t for t in self.users[username]["api_tokens"] if t["token"] != token
            ]
            self.save_users()

    # --- Export, Import, GDPR ---

    def export_users(self, path: str):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=4)
            logging.info(f"[Auth] Exported users to {path}")
        except Exception as e:
            logging.error(f"[Auth] Failed to export users: {e}")

    def import_users(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                users = json.load(f)
            for u, d in users.items():
                self._repair_user(d)
            self.users = users
            self.save_users()
            logging.info(f"[Auth] Imported users from {path}")
        except Exception as e:
            logging.error(f"[Auth] Failed to import users: {e}")

    def gdpr_delete_user(self, username: str):
        """Delete all data for a user in compliance with privacy laws."""
        self.delete_user(username, hard=True)
        self.end_all_sessions(username)
        # Remove from invites, resets, audit, etc.
        for code, inv in list(self.invites.items()):
            if inv.get("email") == self.users.get(username, {}).get("profile", {}).get("email"):
                del self.invites[code]
        for code, reset in list(self.resets.items()):
            if reset.get("user") == username:
                del self.resets[code]
        self.save_invites()
        self.save_resets()

    # --- Admin CLI/GUI utility stubs (for expansion) ---
    # These can be built out as needed for your CLI or web interface

    def search_users(self, query: str) -> List[str]:
        """Simple search by username, email, or profile fields."""
        results = []
        q = query.lower()
        for u, data in self.users.items():
            if q in u.lower() or q in (data.get("profile", {}).get("email", "").lower()):
                results.append(u)
        return results

if __name__ == "__main__":
    um = UserManager()
    # Admin demo/test code
    um.create_user("greg", password="SuperSecret123", roles=["admin"])
    sid = um.start_session("greg", ip="127.0.0.1")
    print(f"Session ID: {sid}")
    print(f"User from session: {um.get_user_from_session(sid)}")
    # Demo password reset
    reset_token = um.request_password_reset("greg")
    print(f"Reset token: {reset_token}")
    print(f"Reset password success: {um.reset_password(reset_token, 'NewPassword123')}")
    # Demo invite
    invite_code = um.invite_user("invitee@example.com", invited_by="greg")
    print(f"Invite code: {invite_code}")
    print(f"Accept invite: {um.accept_invite(invite_code, "newuser", "Password1!")}")
    # Demo API token
    api_token = um.create_api_token("greg", scope="admin", expires_in_hours=2)
    print(f"API token: {api_token}")
    print(f"API token verify: {um.verify_api_token(api_token)}")
    # GDPR delete demo
    um.gdpr_delete_user("newuser")
    # User search
    print("Search for greg:", um.search_users("greg"))