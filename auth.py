import json
import os
import hashlib
import time
import secrets
from typing import Optional, Dict, Any, List, Tuple, Callable

try:
    import bcrypt  # Secure password hashing
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

try:
    import pyotp  # TOTP-based 2FA
    HAS_PYOTP = True
except ImportError:
    HAS_PYOTP = False

class UserManager:
    """
    Vivian 2.0+ User Manager with EventBus integration, GDPR, plugin/memory hooks, and pluggable storage stub.
    """
    def __init__(self, config: Dict[str, Any], event_bus: Optional[Any] = None, storage_backend: Optional[Any] = None):
        """
        Args:
            config: Configuration dictionary.
            event_bus: EventBus instance for event-driven system.
            storage_backend: Optional pluggable backend (for future; default is filesystem).
        """
        self.event_bus = event_bus
        self.backend = storage_backend  # For future: database/cloud
        self.user_file = config.get("user_file", "users.json")
        self.session_file = config.get("session_file", "sessions.json")
        self.users: Dict[str, Dict[str, Any]] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.failed_attempts: Dict[str, Dict[str, Any]] = {}
        self.lockout_threshold = config.get("lockout_threshold", 5)
        self.lockout_time = config.get("lockout_time", 600)
        self.enable_2fa = config.get("enable_2fa", False)
        self.audit_file = config.get("audit_file", "user_audit.log")
        self.profile_fields = config.get("profile_fields", ["email", "preferences", "display_name"])
        self._load_users()
        self._load_sessions()

    # --- Secure Hashing ---
    def _hash(self, value: str) -> str:
        if HAS_BCRYPT:
            return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode()
        else:
            return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _verify(self, value: str, hashed: str) -> bool:
        if HAS_BCRYPT:
            return bcrypt.checkpw(value.encode(), hashed.encode())
        else:
            return self._hash(value) == hashed

    # --- User Data Management ---
    def _load_users(self):
        if self.backend:
            self.users = self.backend.load_users()
            return
        if os.path.exists(self.user_file):
            try:
                with open(self.user_file, "r", encoding="utf-8") as f:
                    self.users = json.load(f)
            except Exception as e:
                print(f"[Auth] Failed to load users: {e}")
        else:
            self._save_users()

    def _save_users(self):
        if self.backend:
            self.backend.save_users(self.users)
            return
        try:
            with open(self.user_file, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2)
        except Exception as e:
            print(f"[Auth] Failed to save users: {e}")

    # --- Session Management ---
    def _load_sessions(self):
        if self.backend:
            self.sessions = self.backend.load_sessions()
            return
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, "r", encoding="utf-8") as f:
                    self.sessions = json.load(f)
            except Exception:
                self.sessions = {}
        else:
            self._save_sessions()

    def _save_sessions(self):
        if self.backend:
            self.backend.save_sessions(self.sessions)
            return
        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(self.sessions, f, indent=2)
        except Exception:
            pass

    def create_session(self, username: str, user_agent: Optional[str] = None, ip_address: Optional[str] = None) -> str:
        token = secrets.token_hex(32)
        now = int(time.time())
        self.sessions[token] = {
            "username": username,
            "created": now,
            "last_active": now,
            "user_agent": user_agent,
            "ip_address": ip_address
        }
        self._save_sessions()
        self._audit("session_create", username, {"user_agent": user_agent, "ip_address": ip_address})
        self._publish_event("session_created", {"username": username, "token": token, "user_agent": user_agent, "ip_address": ip_address})
        return token

    def validate_session(self, token: str) -> Optional[str]:
        session = self.sessions.get(token)
        if session:
            session["last_active"] = int(time.time())
            self._save_sessions()
            self._publish_event("session_validated", {"username": session["username"], "token": token})
            return session["username"]
        return None

    def end_session(self, token: str):
        if token in self.sessions:
            self._audit("session_end", self.sessions[token]["username"])
            self._publish_event("session_ended", {"username": self.sessions[token]["username"], "token": token})
            del self.sessions[token]
            self._save_sessions()

    def list_active_sessions(self) -> List[str]:
        return list(self.sessions.keys())

    # --- Audit Logging & Event Emission ---
    def _audit(self, action: str, username: str, details: Optional[Dict[str, Any]] = None):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "user": username,
            "action": action,
            "details": details or {}
        }
        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass
        # Emit audit event for plugins/compliance
        self._publish_event("user_audit", {"action": action, "user": username, "details": details})

    def _publish_event(self, event_type: str, data: Dict[str, Any], context: Optional[Dict[str, Any]] = None):
        if self.event_bus:
            self.event_bus.publish(event_type, data=data, context=context or {}, async_=False, source="user_manager")

    # --- User Management & Security ---
    def register(self, username: str, password: str, role: str = "user", profile: Optional[Dict[str, Any]] = None, email: Optional[str] = None) -> Tuple[bool, str]:
        if username in self.users:
            return False, "Username already exists."
        if not password or len(password) < 8:
            return False, "Password must be at least 8 characters."
        hashed = self._hash(password)
        new_user = {
            "password": hashed,
            "role": role,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_login": None,
            "permissions": []
        }
        for field in self.profile_fields:
            if profile and field in profile:
                new_user[field] = profile[field]
            elif field == "email" and email:
                new_user[field] = email
        if self.enable_2fa:
            new_user["2fa_secret"] = (pyotp.random_base32() if HAS_PYOTP else secrets.token_hex(16))
        self.users[username] = new_user
        self._save_users()
        self._audit("register", username)
        self._publish_event("user_registered", {"username": username, "role": role, "email": email})
        return True, "User registered."

    def authenticate(self, username: str, password: str, otp: Optional[str] = None) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user:
            return False, "User not found."
        # Lockout check
        fa = self.failed_attempts.get(username, {"count": 0, "until": 0})
        if fa["count"] >= self.lockout_threshold and time.time() < fa["until"]:
            return False, "Account locked due to failed attempts. Try again later."
        if not self._verify(password, user["password"]):
            self.failed_attempts[username] = {
                "count": fa["count"] + 1,
                "until": time.time() + self.lockout_time
            } if fa["count"] + 1 >= self.lockout_threshold else {"count": fa["count"] + 1, "until": 0}
            self._audit("login_fail", username)
            self._publish_event("user_login_failed", {"username": username})
            return False, "Incorrect password."
        if self.enable_2fa and "2fa_secret" in user:
            if HAS_PYOTP:
                totp = pyotp.TOTP(user["2fa_secret"])
                if not otp or not totp.verify(otp):
                    self._audit("login_fail_2fa", username)
                    self._publish_event("user_login_failed_2fa", {"username": username})
                    return False, "2FA code required or incorrect."
            else:
                # fallback stub
                if not otp or otp != "123456":
                    self._audit("login_fail_2fa_stub", username)
                    self._publish_event("user_login_failed_2fa", {"username": username})
                    return False, "2FA required (library not installed)."
        user["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.failed_attempts[username] = {"count": 0, "until": 0}
        self._save_users()
        self._audit("login", username)
        self._publish_event("user_login", {"username": username})
        return True, "Authenticated."

    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user or not self._verify(old_password, user["password"]):
            return False, "Incorrect credentials."
        if not new_password or len(new_password) < 8:
            return False, "Password must be at least 8 characters."
        user["password"] = self._hash(new_password)
        self._save_users()
        self._audit("change_password", username)
        self._publish_event("password_changed", {"username": username})
        return True, "Password updated."

    def set_role(self, username: str, role: str) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user:
            return False, "User not found."
        user["role"] = role
        self._save_users()
        self._audit("role_change", username, {"new_role": role})
        self._publish_event("role_changed", {"username": username, "role": role})
        return True, "Role updated."

    def add_permission(self, username: str, permission: str) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user:
            return False, "User not found."
        perms = user.get("permissions", [])
        if permission not in perms:
            perms.append(permission)
            user["permissions"] = perms
            self._save_users()
            self._audit("add_permission", username, {"permission": permission})
            self._publish_event("permission_added", {"username": username, "permission": permission})
        return True, "Permission granted."

    def remove_permission(self, username: str, permission: str) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user:
            return False, "User not found."
        perms = user.get("permissions", [])
        if permission in perms:
            perms.remove(permission)
            user["permissions"] = perms
            self._save_users()
            self._audit("remove_permission", username, {"permission": permission})
            self._publish_event("permission_removed", {"username": username, "permission": permission})
        return True, "Permission revoked."

    def get_profile(self, username: str) -> Optional[Dict[str, Any]]:
        user = self.users.get(username)
        if not user:
            return None
        profile = {k: v for k, v in user.items() if k != "password"}
        return profile

    def update_profile(self, username: str, **fields) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user:
            return False, "User not found."
        for k in self.profile_fields:
            if k in fields:
                user[k] = fields[k]
        self._save_users()
        self._audit("update_profile", username, fields)
        self._publish_event("profile_updated", {"username": username, "fields": fields})
        return True, "Profile updated."

    def get_role(self, username: str) -> Optional[str]:
        return self.users.get(username, {}).get("role")

    def user_exists(self, username: str) -> bool:
        return username in self.users

    def list_users(self) -> List[str]:
        return list(self.users.keys())

    def delete_user(self, username: str, by_admin: bool = False) -> bool:
        if username in self.users:
            self._audit("delete_user", username, {"by_admin": by_admin})
            self._publish_event("user_deleted", {"username": username, "by_admin": by_admin})
            del self.users[username]
            self._save_users()
            return True
        return False

    # --- Utilities ---
    def reset_password(self, username: str, new_password: str) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user:
            return False, "User not found."
        if not new_password or len(new_password) < 8:
            return False, "Password must be at least 8 characters."
        user["password"] = self._hash(new_password)
        self._save_users()
        self._audit("reset_password", username)
        self._publish_event("password_reset", {"username": username})
        return True, "Password reset."

    def set_2fa(self, username: str, enable: bool = True) -> Tuple[bool, str]:
        user = self.users.get(username)
        if not user:
            return False, "User not found."
        if enable:
            user["2fa_secret"] = (pyotp.random_base32() if HAS_PYOTP else secrets.token_hex(16))
        else:
            user.pop("2fa_secret", None)
        self._save_users()
        self._audit("set_2fa", username, {"enabled": enable})
        self._publish_event("2fa_updated", {"username": username, "enabled": enable})
        return True, "2FA updated."

    def lock_account(self, username: str) -> bool:
        self.failed_attempts[username] = {"count": self.lockout_threshold, "until": time.time() + self.lockout_time}
        self._audit("lock_account", username)
        self._publish_event("account_locked", {"username": username})
        return True

    def unlock_account(self, username: str) -> bool:
        self.failed_attempts[username] = {"count": 0, "until": 0}
        self._audit("unlock_account", username)
        self._publish_event("account_unlocked", {"username": username})
        return True

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        logs = []
        if os.path.exists(self.audit_file):
            with open(self.audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    logs.append(json.loads(line))
        return logs[-limit:]

    # --- Permissions & OAuth/OIDC stub ---
    def has_permission(self, username: str, permission: str) -> bool:
        user = self.users.get(username)
        if not user:
            return False
        if user.get("role") == "admin":
            return True
        return permission in user.get("permissions", [])

    def get_last_login(self, username: str) -> Optional[str]:
        user = self.users.get(username)
        if not user:
            return None
        return user.get("last_login")

    # --- GDPR/Compliance ---
    def gdpr_export_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Export all user data for GDPR compliance."""
        if username not in self.users:
            return None
        user_data = self.get_profile(username)
        sessions = [s for s in self.sessions.values() if s["username"] == username]
        audit_trail = self.get_user_audit_trail(username)
        self._publish_event("gdpr_export", {"username": username})
        return {
            "profile": user_data,
            "sessions": sessions,
            "audit_trail": audit_trail
        }

    def gdpr_delete_user(self, username: str) -> bool:
        """Delete all user data for GDPR compliance."""
        result = self.delete_user(username)
        if result:
            # Remove sessions
            tokens = [t for t, s in self.sessions.items() if s["username"] == username]
            for t in tokens:
                self.end_session(t)
            self._publish_event("gdpr_delete", {"username": username})
        return result

    # --- OAuth/OIDC stub for future extension ---
    def oauth_register_or_login(self, oauth_id: str, profile: Dict[str, Any]) -> str:
        """
        Register or log in a user using OAuth or OIDC.
        """
        username = profile.get("preferred_username") or profile.get("email") or oauth_id
        if username not in self.users:
            self.users[username] = {
                "password": None,
                "role": "user",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_login": time.strftime("%Y-%m-%d %H:%M:%S"),
                "oauth_id": oauth_id,
                "permissions": [],
                "email": profile.get("email"),
                "display_name": profile.get("name", username)
            }
            self._save_users()
            self._audit("oauth_register", username, {"oauth_id": oauth_id})
            self._publish_event("user_registered_oauth", {"username": username, "oauth_id": oauth_id})
        else:
            self.users[username]["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self._save_users()
            self._audit("oauth_login", username, {"oauth_id": oauth_id})
            self._publish_event("user_login_oauth", {"username": username, "oauth_id": oauth_id})
        return username

    # --- For advanced auditing: list all actions by user ---
    def get_user_audit_trail(self, username: str, limit: int = 100) -> List[Dict[str, Any]]:
        logs = []
        if os.path.exists(self.audit_file):
            with open(self.audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry["user"] == username:
                        logs.append(entry)
        return logs[-limit:]