from engine.upgrade_service import UpgradeService
from engine.command_handler import Command
import threading
import time
import uuid

class UpgradeCommand(Command):
    """
    Advanced upgrade command for Vivian.
    Features: dry-run, status, progress, rollback, error handling, RBAC, approval, notifications, audit, hooks, observability,
    async/progress, history, scheduling, and CLI integration.
    """
    def __init__(self, upgrade_service: UpgradeService):
        super().__init__("upgrade", "Force Vivian to check for and install upgrades.")
        self.upgrade_service = upgrade_service
        self._progress = {}
        self._lock = threading.Lock()

    def execute(self, args: str = "", context: dict = None) -> str:
        if not self.upgrade_service:
            return "[UpgradeCommand] Upgrade system not available."

        # Parse options
        dry_run = "dry-run" in args or "--dry-run" in args
        show_status = "status" in args or "--status" in args
        show_history = "history" in args or "--history" in args
        rollback = "rollback" in args or "--rollback" in args
        progress = "progress" in args or "--progress" in args
        schedule = "schedule" in args or "--schedule" in args
        user = context.get("user", "system") if context else "system"
        approval_required = getattr(self.upgrade_service, "approval_fn", None) is not None

        # RBAC check (if present)
        if hasattr(self.upgrade_service, "rbac_fn") and self.upgrade_service.rbac_fn:
            if not self.upgrade_service.rbac_fn(user, "force_upgrade"):
                return f"[UpgradeCommand] User '{user}' is not authorized to perform upgrades."

        if show_status:
            status = self.upgrade_service.get_status() if hasattr(self.upgrade_service, "get_status") else {}
            return f"Upgrade system status:\n{status}"

        if show_history:
            if hasattr(self.upgrade_service, "get_upgrade_history"):
                history = self.upgrade_service.get_upgrade_history()
                return f"Upgrade history:\n{history}"
            else:
                return "[UpgradeCommand] Upgrade history is not available."

        if rollback:
            if hasattr(self.upgrade_service, "rollback_upgrade"):
                try:
                    result = self.upgrade_service.rollback_upgrade(user=user)
                    self._audit(user, args, "rollback")
                    return f"Rollback process triggered. Result: {result}"
                except Exception as e:
                    self._alert(user, args, "rollback_failed", error=str(e))
                    return f"[UpgradeCommand] Error during rollback: {e}"
            else:
                return "[UpgradeCommand] Rollback is not supported by this upgrade service."

        if progress:
            return self._get_progress(user, args)

        if schedule:
            # Allow user to schedule an upgrade (if supported)
            if hasattr(self.upgrade_service, "schedule_upgrade"):
                try:
                    # Example: parse time from args, e.g. --schedule 2025-06-15T02:00
                    import re
                    m = re.search(r"--schedule\s+([0-9T:\-]+)", args)
                    schedule_time = m.group(1) if m else None
                    if not schedule_time:
                        return "[UpgradeCommand] Please specify a schedule time, e.g. --schedule 2025-06-15T02:00"
                    result = self.upgrade_service.schedule_upgrade(schedule_time, user=user)
                    self._audit(user, args, "schedule")
                    return f"Upgrade scheduled for {schedule_time}. Result: {result}"
                except Exception as e:
                    self._alert(user, args, "schedule_failed", error=str(e))
                    return f"[UpgradeCommand] Error during scheduling: {e}"
            else:
                return "[UpgradeCommand] Scheduling is not supported by this upgrade service."

        # Approval check
        if approval_required:
            if not self.upgrade_service.approval_fn("manual-upgrade"):
                return "[UpgradeCommand] Upgrade requires approval and was not approved."

        # Trigger upgrade (possibly async)
        try:
            if dry_run:
                if hasattr(self.upgrade_service, "dry_run_upgrade"):
                    result = self.upgrade_service.dry_run_upgrade(user=user)
                else:
                    result = "[UpgradeCommand] Dry-run mode is not supported."
                self._audit(user, args, "dry-run")
                return f"Upgrade dry-run completed. Result: {result}"

            # Run upgrade async if supported
            if hasattr(self.upgrade_service, "start_upgrade_async"):
                upgrade_id = self._run_async_upgrade(user, args)
                self._audit(user, args, "upgrade_async")
                return f"Upgrade process started asynchronously. Track progress with: upgrade --progress --id {upgrade_id}"
            elif hasattr(self.upgrade_service, "start_upgrade"):
                result = self.upgrade_service.start_upgrade(user=user)
            elif hasattr(self.upgrade_service, "force_check"):
                result = self.upgrade_service.force_check(user=user)
            else:
                result = "[UpgradeCommand] No method available to trigger upgrade."
            self._audit(user, args, "upgrade")
            return f"Upgrade process triggered. Result: {result}"
        except Exception as e:
            self._alert(user, args, "upgrade_failed", error=str(e))
            return f"[UpgradeCommand] Error: {e}"

    def _run_async_upgrade(self, user, args):
        """
        Run the upgrade in a background thread and track progress.
        Returns a unique upgrade id.
        """
        upgrade_id = str(uuid.uuid4())
        def target():
            with self._lock:
                self._progress[upgrade_id] = {"status": "running", "details": ""}
            try:
                result = self.upgrade_service.start_upgrade_async(
                    user=user,
                    progress_callback=lambda msg: self._set_progress(upgrade_id, msg)
                )
                with self._lock:
                    self._progress[upgrade_id].update({"status": "completed", "details": result})
            except Exception as e:
                with self._lock:
                    self._progress[upgrade_id].update({"status": "error", "details": str(e)})
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        return upgrade_id

    def _set_progress(self, upgrade_id, message):
        with self._lock:
            if upgrade_id in self._progress:
                self._progress[upgrade_id]["details"] = message

    def _get_progress(self, user, args):
        # Optionally support --id <upgrade_id>
        import re
        m = re.search(r"--id\s+(\S+)", args)
        upgrade_id = m.group(1) if m else None
        with self._lock:
            if upgrade_id:
                prog = self._progress.get(upgrade_id)
                if not prog:
                    return f"No upgrade found with ID {upgrade_id}."
                return f"ID: {upgrade_id} | Status: {prog['status']} | Details: {prog['details']}"
            # Show all for this user (could filter further if storing user info)
            lines = []
            for uid, prog in self._progress.items():
                lines.append(f"ID: {uid} | Status: {prog['status']} | Details: {prog['details']}")
            return "Upgrade Progress:\n" + ("\n".join(lines) if lines else "No upgrades in progress.")

    def _audit(self, user, args, action):
        if hasattr(self.upgrade_service, "audit_log"):
            self.upgrade_service.audit_log(event="upgrade_command", user=user, args=args, action=action)
        if hasattr(self.upgrade_service, "alert_fn") and self.upgrade_service.alert_fn:
            self.upgrade_service.alert_fn(f"upgrade_command_{action}", {"user": user, "args": args, "action": action})

    def _alert(self, user, args, event, error=""):
        if hasattr(self.upgrade_service, "alert_fn") and self.upgrade_service.alert_fn:
            self.upgrade_service.alert_fn(event, {"user": user, "args": args, "error": error})

    def help(self) -> str:
        return (
            "Usage:\n"
            "  upgrade [--dry-run] [--status] [--history] [--rollback] [--progress] [--schedule <time>]\n"
            "Triggers an immediate upgrade if a new version is available.\n"
            "  --dry-run           : Simulate the upgrade without making changes.\n"
            "  --status            : Show upgrade system status.\n"
            "  --history           : Show upgrade history (if available).\n"
            "  --rollback          : Attempt to roll back the last upgrade (if supported).\n"
            "  --progress [--id X] : Show progress of running upgrades (for async upgrades).\n"
            "  --schedule <time>   : Schedule an upgrade at a specific time (if supported, format: YYYY-MM-DDTHH:MM)\n"
        )