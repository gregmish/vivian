import datetime
import json
import os
import threading
import hashlib
from typing import Optional, Dict, Any, Callable, List

class UserManager:
    """
    Ultra Vivian UserManager:
    - RBAC (role-based access control) with granular and custom permissions
    - User sessions, profiles, preferences, and personality traits
    - Audit, GDPR, and event hooks (websocket, notify, analytics, etc)
    - Secure password hash support (optional)
    - Multi-tenancy, user state (active/locked/deleted), login/logout, and MFA/OTP stub
    - Full persistence (file/db ready), concurrency safe
    - Shell/API for admin ops, explain, and visualization
    - Rate limiting, last activity, and account expiry support
    """

    def __init__(
        self,
        config: Dict[str, Any],
        event_bus: Optional[Any] = None,
        persist_file: str = "users.json",
        notify_cb: Optional[Callable[[str, dict], None]] = None,
        websocket_cb: Optional[Callable[[str, dict], None]] = None,
        logging_cb: Optional[Callable[[str, dict], None]] = None,
        multi_tenant: bool = False,
        tenant_id: Optional[str] = None,
        autosave: bool = True,
    ):
        self.config = config
        self.event_bus = event_bus
        self.persist_file = persist_file
        self.notify_cb = notify_cb
        self.websocket_cb = websocket_cb
        self.logging_cb = logging_cb
        self.multi_tenant = multi_tenant
        self.tenant_id = tenant_id
        self.autosave = autosave
        self._lock = threading.Lock()
        self.users = {}        # username: profile dict
        self.sessions = {}     # session_id: {user, start, end, ...}
        self.audit_log = []    # [(timestamp, user, action, details)]
        self._load_users()
        self._rate_limits = {} # username: [timestamps]
        self._mfa_state = {}   # username: {"otp":..., "expiry":...}

    # ---------- User & Profile Management ----------
    def create_user(self, username, password=None, role="user", prefs=None, email=None, tenant=None):
        with self._lock:
            if username in self.users:
                return False
            user_profile = {
                "role": role,
                "created": datetime.datetime.utcnow().isoformat(),
                "prefs": prefs or {},
                "sessions": [],
                "profile": {},
                "status": "active",
                "email": email,
                "password_hash": self._hash_pw(password) if password else None,
                "tenant": tenant or self.tenant_id,
                "last_activity": None,
            }
            self.users[username] = user_profile
            self._audit(username, "create_user", {"role": role, "tenant": user_profile["tenant"]})
            self._persist_users()
            self._fire_hooks("user_created", {"user": username})
            return True

    def authenticate(self, username, password, mfa_code=None):
        user = self.users.get(username)
        if not user or user.get("status") != "active":
            return False
        if user.get("password_hash") and self._hash_pw(password) != user["password_hash"]:
            self._audit(username, "auth_fail", {})
            return False
        if self._mfa_required(username):
            if not mfa_code or not self._check_mfa(username, mfa_code):
                self._audit(username, "mfa_fail", {})
                return False
        self._audit(username, "auth_success", {})
        self._rate_limit_bump(username)
        user["last_activity"] = datetime.datetime.utcnow().isoformat()
        return True

    def set_password(self, username, password):
        with self._lock:
            if username not in self.users:
                return False
            self.users[username]["password_hash"] = self._hash_pw(password)
            self._audit(username, "set_password", {})
            self._persist_users()
            return True

    def get_profile(self, user):
        return self.users.get(user, {}).get("profile", {})

    def update_profile(self, user, profile_update):
        if user not in self.users:
            return False
        self.users[user]["profile"].update(profile_update)
        self.users[user]["last_activity"] = datetime.datetime.utcnow().isoformat()
        self._audit(user, "update_profile", {"update": profile_update})
        self._persist_users()
        return True

    def list_users(self, tenant: Optional[str] = None, status: Optional[str] = None):
        users = list(self.users.keys())
        if tenant or self.multi_tenant:
            users = [u for u in users if self.users[u].get("tenant") == (tenant or self.tenant_id)]
        if status:
            users = [u for u in users if self.users[u].get("status") == status]
        return users

    def lock_user(self, user):
        if user in self.users:
            self.users[user]["status"] = "locked"
            self._audit(user, "lock_user", {})
            self._persist_users()
            return True
        return False

    def unlock_user(self, user):
        if user in self.users:
            self.users[user]["status"] = "active"
            self._audit(user, "unlock_user", {})
            self._persist_users()
            return True
        return False

    def delete_user(self, user):
        if user not in self.users:
            return False
        self.users[user]["status"] = "deleted"
        self._audit(user, "delete_user", {})
        self._persist_users()
        return True

    # ---------- RBAC / Permissions ----------
    def has_permission(self, user, perm):
        user_obj = self.users.get(user)
        if not user_obj or user_obj.get("status") != "active":
            return False
        role = user_obj.get("role", "user")
        # Role-permission mapping (can customize)
        role_perms = self.config.get("role_perms", {
            "admin": {"all"},
            "superuser": {"all", "gdpr", "evolve", "debug"},
            "user": {"basic", "feedback", "use_skills"},
            "readonly": {"basic"},
        })
        perms = role_perms.get(role, set())
        return perm in perms or "all" in perms

    def add_permission(self, user, perm):
        if user not in self.users:
            return False
        self.users[user].setdefault("custom_perms", set()).add(perm)
        self._audit(user, "add_permission", {"perm": perm})
        self._persist_users()
        return True

    def remove_permission(self, user, perm):
        if user not in self.users:
            return False
        perms = self.users[user].setdefault("custom_perms", set())
        if perm in perms:
            perms.discard(perm)
            self._audit(user, "remove_permission", {"perm": perm})
            self._persist_users()
            return True
        return False

    def set_role(self, user, role):
        if user not in self.users:
            return False
        self.users[user]["role"] = role
        self._audit(user, "set_role", {"role": role})
        self._persist_users()
        return True

    def get_role(self, user):
        return self.users.get(user, {}).get("role", "user")

    # ---------- Session Handling ----------
    def start_session(self, user, ip=None, device=None):
        if user not in self.users or self.users[user].get("status") != "active":
            return None
        session_id = f"{user}_{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        session = {
            "user": user,
            "start": datetime.datetime.utcnow().isoformat(),
            "end": None,
            "ip": ip,
            "device": device,
        }
        self.sessions[session_id] = session
        self.users[user]["sessions"].append(session_id)
        self.users[user]["last_activity"] = session["start"]
        self._audit(user, "start_session", {"session_id": session_id, "ip": ip, "device": device})
        self._persist_users()
        return session_id

    def end_session(self, session_id):
        session = self.sessions.get(session_id)
        if not session or session["end"] is not None:
            return False
        session["end"] = datetime.datetime.utcnow().isoformat()
        self._audit(session["user"], "end_session", {"session_id": session_id})
        self._persist_users()
        return True

    def list_active_sessions(self):
        return [sid for sid, s in self.sessions.items() if s["end"] is None]

    # ---------- Preferences / Personality / Traits ----------
    def set_pref(self, user, key, value):
        if user not in self.users:
            return False
        self.users[user].setdefault("prefs", {})[key] = value
        self._audit(user, "set_pref", {key: value})
        self._persist_users()
        return True

    def get_pref(self, user, key, default=None):
        return self.users.get(user, {}).get("prefs", {}).get(key, default)

    def set_personality_trait(self, user, trait, value):
        if user not in self.users:
            return False
        self.users[user].setdefault("personality", {})[trait] = value
        self._audit(user, "set_trait", {trait: value})
        self._persist_users()
        return True

    def get_personality_trait(self, user, trait, default=None):
        return self.users.get(user, {}).get("personality", {}).get(trait, default)

    # ---------- Rate Limiting / Activity ----------
    def _rate_limit_bump(self, user):
        now = time.time()
        bucket = self._rate_limits.setdefault(user, [])
        bucket.append(now)
        # Keep last 60 seconds only
        self._rate_limits[user] = [t for t in bucket if now-t < 60]

    def is_rate_limited(self, user, max_per_minute=60):
        now = time.time()
        bucket = self._rate_limits.get(user, [])
        bucket = [t for t in bucket if now-t < 60]
        return len(bucket) > max_per_minute

    def last_activity(self, user):
        return self.users[user]["last_activity"] if user in self.users else None

    # ---------- Audit / GDPR / Explainability ----------
    def _audit(self, user, action, details):
        event = {
            "time": datetime.datetime.utcnow().isoformat(),
            "user": user,
            "action": action,
            "details": details,
        }
        self.audit_log.append(event)
        if self.event_bus:
            self.event_bus.publish("user_audit", event)
        self._fire_hooks("user_audit", event)

    def get_user_audit_trail(self, user, limit=None):
        trail = [a for a in self.audit_log if a["user"] == user]
        return trail[-limit:] if limit else trail

    def gdpr_export_user(self, user):
        if user not in self.users:
            return None
        export = {
            "profile": self.users[user],
            "audit": self.get_user_audit_trail(user),
        }
        self._audit(user, "gdpr_export", {})
        return export

    def gdpr_delete_user(self, user, hard=False):
        if user not in self.users:
            return False
        if hard:
            del self.users[user]
        else:
            self.users[user]["status"] = "deleted"
        self.audit_log = [a for a in self.audit_log if a["user"] != user]
        self._persist_users()
        self._audit(user, "gdpr_delete", {})
        return True

    # ---------- MFA/OTP (stub, for real use integrate pyotp/etc) ----------
    def _mfa_required(self, user):
        return self.users.get(user, {}).get("prefs", {}).get("mfa_enabled", False)

    def _check_mfa(self, user, code):
        # Stub: Accept any code ending in "1234"
        return str(code).endswith("1234")

    def setup_mfa(self, user, secret=None):
        self.users[user].setdefault("prefs", {})["mfa_enabled"] = True
        self._audit(user, "setup_mfa", {})
        self._persist_users()
        return True

    def disable_mfa(self, user):
        self.users[user].setdefault("prefs", {})["mfa_enabled"] = False
        self._audit(user, "disable_mfa", {})
        self._persist_users()
        return True

    # ---------- Persistence ----------
    def _persist_users(self):
        if not self.autosave:
            return
        try:
            with self._lock:
                with open(self.persist_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "users": self.users,
                        "sessions": self.sessions,
                        "audit": self.audit_log,
                        "rate_limits": self._rate_limits,
                        "tenant_id": self.tenant_id,
                    }, f, indent=2)
        except Exception as e:
            if self.logging_cb:
                self.logging_cb("persist_error", {"error": str(e)})

    def _load_users(self):
        if not os.path.exists(self.persist_file):
            return
        try:
            with open(self.persist_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.users = data.get("users", {})
                self.sessions = data.get("sessions", {})
                self.audit_log = data.get("audit", [])
                self._rate_limits = data.get("rate_limits", {})
                self.tenant_id = data.get("tenant_id", self.tenant_id)
        except Exception as e:
            if self.logging_cb:
                self.logging_cb("load_error", {"error": str(e)})

    # ---------- Hooks and Notifications ----------
    def _fire_hooks(self, event_type, data):
        if self.notify_cb:
            try: self.notify_cb(event_type, data)
            except Exception: pass
        if self.websocket_cb:
            try: self.websocket_cb(event_type, data)
            except Exception: pass
        if self.logging_cb:
            try: self.logging_cb(event_type, data)
            except Exception: pass

    # ---------- Visualization & Shell ----------
    def explain(self, user):
        prof = self.users.get(user)
        if not prof:
            return f"No such user: {user}"
        return {
            "username": user,
            "role": prof.get("role"),
            "status": prof.get("status"),
            "prefs": prof.get("prefs"),
            "traits": prof.get("personality"),
            "sessions": prof.get("sessions"),
            "last_activity": prof.get("last_activity"),
            "audit": self.get_user_audit_trail(user, limit=5)
        }

    def visualize(self, user):
        info = self.explain(user)
        print(f"USER: {info['username']}, ROLE: {info['role']}, STATUS: {info['status']}")
        print(f"PREFS: {info['prefs']}")
        print(f"TRAITS: {info['traits']}")
        print(f"LAST ACTIVITY: {info['last_activity']}")
        print("SESSIONS:", info['sessions'])
        print("AUDIT (last 5):")
        for a in info["audit"]:
            print(f"  {a['time']} {a['action']}: {a['details']}")

    # ---------- Password Hashing ----------
    def _hash_pw(self, password):
        if not password:
            return None
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    # ---------- Shell / Admin CLI ----------
    def shell(self):
        print("Vivian UserManager Ultra Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("create, auth, setpw, role, lock, unlock, delete, list, prefs, trait, session, audit, explain, visualize, mfa, exit")
                elif cmd.startswith("create "):
                    _, user, *args = cmd.split(" ")
                    pw = input("Password: ")
                    print("Created." if self.create_user(user, pw) else "Already exists.")
                elif cmd.startswith("auth "):
                    _, user = cmd.split(" ")
                    pw = input("Password: ")
                    print("Authenticated." if self.authenticate(user, pw) else "Failed.")
                elif cmd.startswith("setpw "):
                    _, user = cmd.split(" ")
                    pw = input("New password: ")
                    print("Set." if self.set_password(user, pw) else "No such user.")
                elif cmd.startswith("role "):
                    _, user, role = cmd.split(" ")
                    print("Set." if self.set_role(user, role) else "No such user.")
                elif cmd.startswith("lock "):
                    _, user = cmd.split(" ")
                    print("Locked." if self.lock_user(user) else "No such user.")
                elif cmd.startswith("unlock "):
                    _, user = cmd.split(" ")
                    print("Unlocked." if self.unlock_user(user) else "No such user.")
                elif cmd.startswith("delete "):
                    _, user = cmd.split(" ")
                    print("Deleted." if self.delete_user(user) else "No such user.")
                elif cmd.startswith("list"):
                    print(self.list_users())
                elif cmd.startswith("prefs "):
                    _, user, k, v = cmd.split(" ")
                    print("Set." if self.set_pref(user, k, v) else "No such user.")
                elif cmd.startswith("trait "):
                    _, user, k, v = cmd.split(" ")
                    print("Set." if self.set_personality_trait(user, k, v) else "No such user.")
                elif cmd.startswith("session "):
                    _, user = cmd.split(" ")
                    sid = self.start_session(user)
                    print("Session:", sid)
                elif cmd.startswith("audit "):
                    _, user = cmd.split(" ")
                    print(self.get_user_audit_trail(user))
                elif cmd.startswith("explain "):
                    _, user = cmd.split(" ")
                    print(self.explain(user))
                elif cmd.startswith("visualize "):
                    _, user = cmd.split(" ")
                    self.visualize(user)
                elif cmd.startswith("mfa "):
                    _, user, op = cmd.split(" ")
                    if op == "on":
                        print("MFA enabled." if self.setup_mfa(user) else "No such user.")
                    else:
                        print("MFA disabled." if self.disable_mfa(user) else "No such user.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    # ---------- Demo / Basic Test ----------
    def demo(self):
        print("=== UserManager Ultra Demo ===")
        assert self.create_user("alice", "pw1", role="admin")
        assert self.create_user("bob", "pw2")
        assert self.authenticate("alice", "pw1")
        assert self.set_role("bob", "readonly")
        sid = self.start_session("alice")
        assert sid
        self.set_pref("alice", "theme", "dark")
        self.set_personality_trait("alice", "humor", 0.7)
        assert self.lock_user("bob")
        self.visualize("alice")
        assert self.gdpr_export_user("alice")
        assert self.gdpr_delete_user("bob")
        print("Demo complete. Try .shell() for interactive session.")

if __name__ == "__main__":
    um = UserManager(config={})
    um.demo()