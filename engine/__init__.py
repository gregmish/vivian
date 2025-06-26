"""
Vivian Upgrade Engine
====================
Enterprise-grade, extensible upgrade orchestrator for agentic systems.

Exports:
    - UpgradeService: Main orchestrating service (REST API/dashboard ready).
    - UpgradeScheduler: Smart scheduled upgrade checker (cluster-safe, observable).
    - UpgradeTrigger: Handles immediate/manual upgrade triggers.
    - UpgradeDownloader, extract_upgrade: Utilities for downloading and extracting upgrades.
    - Factory utilities and plugin discovery.
    - Version, metadata, and health check helpers.
"""

from engine.upgrade_service import UpgradeService
from engine.upgrade_trigger import UpgradeTrigger
from engine.upgrade_scheduler import UpgradeScheduler
from engine.upgrade_utils import UpgradeDownloader, extract_upgrade
import pkgutil
import logging
import sys
import os

__version__ = "1.0.0"
__author__ = "Vivian Team"
__license__ = "MIT"
__description__ = "Vivian Enterprise Upgrade Engine: service, scheduler, trigger, utilities"
__url__ = "https://github.com/vivian-ai/enterprise-upgrade-engine"

def discover_plugins():
    """Auto-discovers upgrade plugins in the engine.upgrade_plugins namespace."""
    plugins = []
    try:
        from engine import upgrade_plugins
        for loader, name, ispkg in pkgutil.iter_modules(upgrade_plugins.__path__):
            plugins.append(name)
    except ImportError:
        pass
    return plugins

def create_default_upgrade_service():
    """Returns a default UpgradeService instance."""
    return UpgradeService()

def create_default_scheduler():
    return UpgradeScheduler()

def get_version():
    """Returns the current version of the engine."""
    return __version__

def health_check():
    """
    Performs a basic health check for the engine package.
    Returns a dict with status and info.
    """
    status = "ok"
    details = []
    # Check main components
    try:
        _ = UpgradeService()
        _ = UpgradeScheduler()
        _ = UpgradeTrigger()
        details.append("Core components loaded.")
    except Exception as e:
        status = "error"
        details.append(f"Error loading core components: {e}")
    # Check plugins
    plugins = discover_plugins()
    details.append(f"Plugins discovered: {plugins}")
    # Check write permissions
    try:
        tmp = os.path.join(os.path.dirname(__file__), "vivian_upgrade_healthcheck.tmp")
        with open(tmp, "w") as f:
            f.write("healthcheck")
        os.remove(tmp)
        details.append("Write permissions: ok")
    except Exception as e:
        status = "error"
        details.append(f"Write permission error: {e}")
    return {"status": status, "details": details, "version": __version__}

def print_status():
    """Prints a summary status for CLI use."""
    h = health_check()
    print(f"Vivian Upgrade Engine v{h['version']}\nStatus: {h['status']}")
    for d in h["details"]:
        print(f" - {d}")

__all__ = [
    "UpgradeService",
    "UpgradeTrigger",
    "UpgradeScheduler",
    "UpgradeDownloader",
    "extract_upgrade",
    "discover_plugins",
    "create_default_upgrade_service",
    "create_default_scheduler",
    "get_version",
    "health_check",
    "print_status"
] + discover_plugins()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Vivian Upgrade Engine CLI")
    parser.add_argument("command", nargs="?", default="status",
                        choices=["start", "force_check", "status", "health", "plugins"],
                        help="Command to run")
    args = parser.parse_args()

    if args.command == "start":
        svc = create_default_upgrade_service()
        svc.start()
    elif args.command == "force_check":
        svc = create_default_upgrade_service()
        svc.force_check()
    elif args.command == "status" or args.command == "health":
        print_status()
    elif args.command == "plugins":
        print("Available plugins:", discover_plugins())
    else:
        parser.print_help()