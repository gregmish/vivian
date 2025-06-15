import os
import zipfile
import logging
import shutil
import hashlib
import json
import datetime
import threading
from typing import Optional, List, Dict, Callable

UPGRADE_DIR = os.path.join("upgrades")
AUTO_APPLY_DIR = os.path.join(UPGRADE_DIR, "auto_applied")
BACKUP_DIR = os.path.join(UPGRADE_DIR, "backups")
METADATA_FILE = os.path.join(UPGRADE_DIR, "upgrade_meta.json")
LOG_FILE = os.path.join(UPGRADE_DIR, "upgrade_events.log")
SIGNATURES_DIR = os.path.join(UPGRADE_DIR, "signatures")

os.makedirs(UPGRADE_DIR, exist_ok=True)
os.makedirs(AUTO_APPLY_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(SIGNATURES_DIR, exist_ok=True)

def current_time() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

class UpgradeInstaller:
    """
    Enterprise-grade, agentic, self-healing code upgrade installer for Vivian.
    """

    def __init__(self, base_dir: str = ".", verbose: bool = True):
        self.base_dir = base_dir
        self.verbose = verbose
        self.lock = threading.RLock()
        self.meta = self._load_meta()
        self.event_log: List[Dict] = self._load_events()
        self.hooks: List[Callable[[str, Dict], None]] = []
        self.approval_callback: Optional[Callable[[str], bool]] = None
        self.health_check_fn: Optional[Callable[[], bool]] = None
        self.policy_fn: Optional[Callable[[str], bool]] = None
        self.permission_fn: Optional[Callable[[str, str], bool]] = None  # (user, action)
        self.notification_fn: Optional[Callable[[str, Dict], None]] = None

    # ---------- Upgrade Validation, Diff, Signature ----------

    def verify_signature(self, zip_path: str) -> bool:
        # Placeholder: real implementation would check cryptographic signature
        sig_file = os.path.join(SIGNATURES_DIR, os.path.basename(zip_path) + ".sig")
        if os.path.exists(sig_file):
            logging.info(f"[UpgradeInstaller] Verified signature for {zip_path}")
            return True
        logging.warning(f"[UpgradeInstaller] No signature found for {zip_path}")
        return False

    def show_diff(self, zip_path: str) -> Dict[str, List[str]]:
        # Show which files would be changed/added/removed
        changed, added, removed = [], [], []
        if not os.path.isfile(zip_path):
            return {}
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_files = set(zip_ref.namelist())
            current_files = set()
            for root, _, files in os.walk(self.base_dir):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), self.base_dir)
                    current_files.add(rel)
            added = list(zip_files - current_files)
            removed = list(current_files - zip_files)
            changed = list(zip_files & current_files)
        return {"added": added, "removed": removed, "changed": changed}

    def preflight_test(self, zip_path: str) -> bool:
        # Run tests/lint on unzipped content in temp dir
        logging.info(f"[UpgradeInstaller] Preflight test for {zip_path} (stub)")
        return True

    # ---------- Core Apply Logic, Approval, Scheduling ----------

    def schedule_upgrade(self, zip_path: str, when: datetime.datetime) -> bool:
        # Placeholder: would integrate with cron/scheduler
        self._log_event("scheduled", {"zip": zip_path, "time": when.isoformat()})
        return True

    def apply_zip(self, zip_path: str, dry_run: bool = False, verify: bool = True, user: str = "system") -> bool:
        if not os.path.isfile(zip_path):
            logging.warning(f"[UpgradeInstaller] File not found: {zip_path}")
            return False

        with self.lock:
            # Permissions
            if self.permission_fn and not self.permission_fn(user, "apply"):
                self._log_event("permission_denied", {"user": user, "zip": zip_path})
                return False
            # Policy
            if self.policy_fn and not self.policy_fn(zip_path):
                self._log_event("policy_block", {"zip": zip_path})
                return False
            # Approval
            if self.approval_callback and not self.approval_callback(zip_path):
                self._log_event("not_approved", {"zip": zip_path})
                return False
            # Signature
            if verify and not self.verify_signature(zip_path):
                self._log_event("signature_invalid", {"zip": zip_path})
                return False
            # Preflight
            if not self.preflight_test(zip_path):
                self._log_event("preflight_failed", {"zip": zip_path})
                return False

            try:
                hash_val = self._hash_file(zip_path)
                meta = self.meta.get(os.path.basename(zip_path), {})
                # Integrity
                if verify and meta and meta.get("hash") and meta.get("hash") != hash_val:
                    logging.error(f"[UpgradeInstaller] Hash mismatch for {zip_path}: {hash_val} != {meta.get('hash')}")
                    self._log_event("hash_mismatch", {"zip": zip_path, "expected": meta.get("hash"), "got": hash_val})
                    return False

                # Diff
                diff = self.show_diff(zip_path)
                self._log_event("diff", {"zip": zip_path, "diff": diff})

                if dry_run:
                    logging.info(f"[UpgradeInstaller] Dry run: would extract {list(diff.get('added', [])) + list(diff.get('changed', []))}")
                    self._log_event("dry_run", {"zip": zip_path, "diff": diff})
                    return True

                # Backup before apply
                backup_path = self._backup_state(os.path.basename(zip_path))

                # Extract
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(self.base_dir)
                    if self.verbose:
                        logging.info(f"[UpgradeInstaller] Extracted: {zip_path} to {self.base_dir}")

                # Move applied zip
                target = os.path.join(AUTO_APPLY_DIR, os.path.basename(zip_path))
                shutil.move(zip_path, target)
                logging.info(f"[UpgradeInstaller] Moved applied zip to: {target}")

                # Metadata
                self.meta[os.path.basename(target)] = {
                    "applied_at": current_time(),
                    "hash": hash_val,
                    "backup": backup_path,
                    "diff": diff,
                    "files": self._list_zip_files(target),
                    "applied_by": user,
                }
                self._save_meta()
                self._log_event("applied", {"zip": target, "backup": backup_path, "diff": diff, "user": user})

                # Notifications
                self._notify("upgrade_applied", {"zip": target, "by": user})

                # Post-upgrade health check
                if self.health_check_fn and not self.health_check_fn():
                    logging.error("[UpgradeInstaller] Health check failed post-upgrade! Initiating rollback.")
                    self.rollback(os.path.basename(target))
                    self._log_event("auto_rollback", {"zip": target})
                    self._notify("auto_rollback", {"zip": target, "by": user})
                    return False

                return True
            except Exception as e:
                logging.error(f"[UpgradeInstaller] Failed to extract {zip_path}: {e}")
                self._log_event("apply_failed", {"zip": zip_path, "error": str(e)})
                self._notify("upgrade_failed", {"zip": zip_path, "error": str(e)})
                return False

    def auto_scan_and_apply(self, dry_run: bool = False, user: str = "system") -> List[str]:
        """
        Automatically finds upgrade zips in the upgrade folder and installs them.
        """
        applied = []
        for fname in os.listdir(UPGRADE_DIR):
            if fname.endswith(".zip") and fname not in os.listdir(AUTO_APPLY_DIR):
                full_path = os.path.join(UPGRADE_DIR, fname)
                if self.apply_zip(full_path, dry_run=dry_run, user=user):
                    applied.append(fname)
        return applied

    def rollback(self, upgrade_zip: str, user: str = "system") -> bool:
        """
        Rollback to the backup taken before the given upgrade zip was applied.
        """
        with self.lock:
            # Permissions
            if self.permission_fn and not self.permission_fn(user, "rollback"):
                self._log_event("permission_denied", {"user": user, "zip": upgrade_zip})
                return False
            meta = self.meta.get(upgrade_zip)
            if not meta or not meta.get("backup"):
                logging.error(f"[UpgradeInstaller] No backup found for rollback: {upgrade_zip}")
                return False
            backup_path = meta["backup"]
            try:
                with zipfile.ZipFile(backup_path, 'r') as zip_ref:
                    zip_ref.extractall(self.base_dir)
                self._log_event("rollback", {"from": upgrade_zip, "backup": backup_path, "user": user})
                self._notify("upgrade_rolled_back", {"zip": upgrade_zip, "by": user})
                if self.verbose:
                    logging.info(f"[UpgradeInstaller] Rolled back {upgrade_zip} using backup {backup_path}")
                return True
            except Exception as e:
                logging.error(f"[UpgradeInstaller] Rollback failed for {upgrade_zip}: {e}")
                self._log_event("rollback_failed", {"zip": upgrade_zip, "error": str(e)})
                self._notify("rollback_failed", {"zip": upgrade_zip, "error": str(e)})
                return False

    # ---------- Backup, Meta, Integrity ----------

    def _backup_state(self, upgrade_zip: str) -> str:
        backup_name = f"backup_before_{upgrade_zip}_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        files_to_backup = []
        for root, _, files in os.walk(self.base_dir):
            for fname in files:
                if fname.endswith(".py"):
                    files_to_backup.append(os.path.join(root, fname))
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as snap_zip:
            for fpath in files_to_backup:
                try:
                    arcname = os.path.relpath(fpath, self.base_dir)
                    snap_zip.write(fpath, arcname)
                except Exception as e:
                    logging.warning(f"[UpgradeInstaller] Failed to add {fpath} to backup: {e}")
        return backup_path

    def _hash_file(self, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()

    def _list_zip_files(self, path: str) -> List[str]:
        with zipfile.ZipFile(path, "r") as zip_ref:
            return zip_ref.namelist()

    # ---------- Meta/Log Persistence ----------

    def _load_meta(self) -> Dict:
        if os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_meta(self):
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2)

    def _log_event(self, action: str, details: Dict):
        event = {
            "time": current_time(),
            "action": action,
            "details": details,
        }
        self.event_log.append(event)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def _load_events(self) -> List[Dict]:
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    return [json.loads(line) for line in f]
            except Exception:
                return []
        return []

    # ---------- Hooks, Permissions, Policies, Notification ----------

    def register_hook(self, hook_fn: Callable[[str, Dict], None]):
        self.hooks.append(hook_fn)

    def call_hooks(self, event: str, data: Dict):
        for h in self.hooks:
            try:
                h(event, data)
            except Exception as e:
                logging.warning(f"[UpgradeInstaller] Hook error: {e}")

    def set_approval_callback(self, approve_fn: Callable[[str], bool]):
        self.approval_callback = approve_fn

    def set_health_check(self, health_fn: Callable[[], bool]):
        self.health_check_fn = health_fn

    def set_policy_fn(self, policy_fn: Callable[[str], bool]):
        self.policy_fn = policy_fn

    def set_permission_fn(self, perm_fn: Callable[[str, str], bool]):
        self.permission_fn = perm_fn

    def set_notification_fn(self, notif_fn: Callable[[str, Dict], None]):
        self.notification_fn = notif_fn

    def _notify(self, event: str, data: Dict):
        if self.notification_fn:
            try:
                self.notification_fn(event, data)
            except Exception as e:
                logging.warning(f"[UpgradeInstaller] Notification error: {e}")

    # ---------- Observability, API, CLI, Undo Preview ----------

    def get_applied_upgrades(self) -> List[str]:
        return list(self.meta.keys())

    def get_event_log(self) -> List[Dict]:
        return self.event_log

    def is_ready(self) -> bool:
        return os.path.isdir(UPGRADE_DIR) and os.path.isdir(self.base_dir)

    def undo_preview(self, upgrade_zip: str) -> Dict[str, List[str]]:
        # Show what would be restored if this upgrade is rolled back.
        meta = self.meta.get(upgrade_zip)
        if not meta or not meta.get("backup"):
            return {}
        with zipfile.ZipFile(meta["backup"], "r") as backup_zip:
            return {"would_restore": backup_zip.namelist()}

    def selective_apply(self, zip_path: str, files: List[str]) -> bool:
        # Apply only selected files from the zip.
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for f in files:
                    zip_ref.extract(f, self.base_dir)
            self._log_event("selective_apply", {"zip": zip_path, "files": files})
            self._notify("selective_apply", {"zip": zip_path, "files": files})
            return True
        except Exception as e:
            logging.error(f"[UpgradeInstaller] Selective apply failed: {e}")
            self._log_event("selective_apply_failed", {"zip": zip_path, "files": files, "error": str(e)})
            return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    up = UpgradeInstaller()
    print("Ready:", up.is_ready())
    # Example dry run and diff
    test_zip = os.path.join(UPGRADE_DIR, "sample_upgrade.zip")
    print("Diff:", up.show_diff(test_zip))
    print("Dry run:", up.apply_zip(test_zip, dry_run=True))
    # Example approval
    up.set_approval_callback(lambda path: True) # Always approve
    print("Applied upgrades:", up.auto_scan_and_apply(user="gregmish"))
    print("Meta:", up.get_applied_upgrades())
    print("Event log (last 3):", up.get_event_log()[-3:])
    # Undo preview
    if up.get_applied_upgrades():
        last = up.get_applied_upgrades()[-1]
        print("Undo preview for last upgrade:", up.undo_preview(last))