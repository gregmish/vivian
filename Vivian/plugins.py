import logging
import inspect
import traceback
import os
import importlib.util
import threading
import multiprocessing
from typing import Callable, Dict, Any, List, Optional
import time

# In-memory plugin registry
_plugins: Dict[str, Dict[str, Any]] = {}

# Analytics and plugin run history
_plugin_history: List[Dict[str, Any]] = []
_HISTORY_LIMIT = 100

# Event bus and plugin event subscribers
_plugin_event_hook: Optional[Callable[[str, Dict[str, Any]], None]] = None
_plugin_event_subscribers: Dict[str, List[Callable[[str, Dict[str, Any]], None]]] = {}

# Plugin health/fault monitoring
_plugin_faults: Dict[str, int] = {}
_PLUGIN_FAULT_LIMIT = 5

def set_plugin_event_hook(hook: Callable[[str, Dict[str, Any]], None]):
    """Set a global event bus hook (for system-wide events)."""
    global _plugin_event_hook
    _plugin_event_hook = hook

def subscribe_to_event(event_type: str, handler: Callable[[str, Dict[str, Any]], None]):
    """Plugins (or core) can subscribe to any named event (including memory events)."""
    _plugin_event_subscribers.setdefault(event_type, []).append(handler)

def _emit_event(event: str, data: Dict[str, Any]):
    """Emit event to global event hook and all per-event-type subscribers."""
    if _plugin_event_hook:
        try:
            _plugin_event_hook(event, data)
        except Exception as e:
            logging.error(f"[Plugins] Error in event hook: {e}")
    for handler in _plugin_event_subscribers.get(event, []):
        try:
            handler(event, data)
        except Exception as e:
            logging.error(f"[Plugins] Error in event subscriber: {e}")

def _emit_lifecycle_event(event: str, name: str, data: dict):
    """Emit plugin-specific lifecycle events (load, unload, error, etc.)."""
    _emit_event(f"plugin_{event}", {"name": name, **data})

def register_plugin(
    name: str,
    func: Callable,
    description: Optional[str] = None,
    author: Optional[str] = None,
    version: str = "1.0",
    tags: Optional[List[str]] = None,
    usage: Optional[str] = None,
    permissions: Optional[List[str]] = None,
):
    """Register a plugin function with metadata."""
    if not description:
        description = inspect.getdoc(func) or ""
    _plugins[name] = {
        "func": func,
        "description": description,
        "usage": usage or "",
        "author": author,
        "version": version,
        "tags": tags or [],
        "permissions": permissions or [],
        "enabled": True,
        "faults": 0,
    }
    logging.info(f"[Plugins] Registered plugin '{name}'")
    _emit_event("plugin_registered", {"name": name, "meta": plugin_metadata(name)})
    _emit_lifecycle_event("load", name, {})

def unregister_plugin(name: str):
    """Remove a plugin from the registry."""
    if name in _plugins:
        del _plugins[name]
        logging.info(f"[Plugins] Unregistered plugin '{name}'")
        _emit_event("plugin_unregistered", {"name": name})
        _emit_lifecycle_event("unload", name, {})

def available_plugins(tags: Optional[List[str]] = None, permissions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """List available plugins, optionally filtered by tag or permission."""
    result = []
    for name, plugin in _plugins.items():
        if not plugin.get("enabled", True):
            continue
        if tags and not any(t in plugin.get("tags", []) for t in tags):
            continue
        if permissions and not set(permissions).intersection(set(plugin.get("permissions", []))):
            continue
        meta = {k: v for k, v in plugin.items() if k != "func"}
        meta["name"] = name
        result.append(meta)
    return result

def plugin_metadata(name: str) -> Dict[str, Any]:
    """Return plugin metadata (excluding the function itself)."""
    plugin = _plugins.get(name)
    if not plugin:
        return {}
    return {k: v for k, v in plugin.items() if k != "func"}

def plugin_help(name: str) -> str:
    """Return formatted help/usage for a plugin."""
    meta = plugin_metadata(name)
    if not meta:
        return "[Plugins] Plugin not found."
    base = f"{name} (v{meta.get('version','')})"
    doc = meta.get("description", "")
    usage = meta.get("usage", "")
    tags = meta.get("tags", [])
    author = meta.get("author", "")
    s = f"{base}\n"
    if author:
        s += f"Author: {author}\n"
    if tags:
        s += f"Tags: {', '.join(tags)}\n"
    if usage:
        s += f"Usage: {usage}\n"
    if doc:
        s += f"{doc}\n"
    return s

def run_plugin(name: str, args: List[Any], user: Optional[str] = None, safe: bool = False, timeout: float = 10) -> Any:
    """Run a plugin by name, optionally safely in a subprocess (timeout)."""
    plugin = _plugins.get(name)
    if not plugin or not plugin.get("enabled", True):
        result = f"[Plugins] Plugin '{name}' not found or is disabled."
        _emit_history(name, user, args, None, result, "not_found")
        return result

    if safe:
        return run_plugin_safe(name, args, user=user, timeout=timeout)

    try:
        result = plugin["func"](*args)
        _emit_history(name, user, args, result, None, "success")
        _emit_event("plugin_run", {"name": name, "user": user, "args": args, "result": result})
        return result
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"[Plugins] Error running plugin '{name}': {e}\n{tb}")
        _emit_history(name, user, args, None, str(e), "error", tb)
        _emit_event("plugin_error", {"name": name, "user": user, "args": args, "error": str(e), "traceback": tb})
        report_plugin_fault(name)
        return f"[Plugins] Error running plugin '{name}': {e}"

def run_plugin_safe(name: str, args: List[Any], user: Optional[str] = None, timeout: float = 10) -> Any:
    """Run a plugin in a subprocess for safety and timeout enforcement."""
    def target(q):
        try:
            plugin = _plugins.get(name)
            if not plugin:
                q.put(f"[Plugins] Plugin '{name}' not found.")
            else:
                result = plugin["func"](*args)
                q.put(result)
        except Exception as e:
            q.put(f"[Plugins] Error: {e}")

    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=target, args=(q,))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()
        _emit_history(name, user, args, None, f"Timeout after {timeout}s", "timeout")
        _emit_event("plugin_timeout", {"name": name, "user": user, "args": args, "timeout": timeout})
        report_plugin_fault(name)
        return f"[Plugins] Plugin '{name}' timed out after {timeout}s."
    result = q.get() if not q.empty() else "[Plugins] No result."
    _emit_history(name, user, args, result, None, "success")
    return result

def _emit_history(name, user, args, result, error, status, traceback_str=None):
    """Track plugin run history for analytics and audit."""
    entry = {
        "plugin": name,
        "user": user,
        "args": args,
        "result": result,
        "error": error,
        "status": status,
        "traceback": traceback_str,
        "time": time.time()
    }
    _plugin_history.append(entry)
    if len(_plugin_history) > _HISTORY_LIMIT:
        del _plugin_history[0]

def plugin_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Return recent plugin execution history."""
    return _plugin_history[-limit:]

def reload_plugins(directory: str = "plugins", auto_reload: bool = False, memory_manager=None):
    """Reload all plugins from a directory. Supports memory manager injection."""
    logging.info(f"[Plugins] Reloading plugins from {directory}")
    count = 0
    for fname in os.listdir(directory):
        if fname.endswith(".py") and not fname.startswith("_"):
            path = os.path.join(directory, fname)
            name = os.path.splitext(fname)[0]
            try:
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "register"):
                    argspec = inspect.getfullargspec(module.register)
                    if "memory_manager" in argspec.args and memory_manager:
                        module.register(register_plugin, memory_manager)
                    else:
                        module.register(register_plugin)
                    count += 1
                else:
                    logging.warning(f"[Plugins] '{fname}' does not have a register() function")
            except Exception as e:
                logging.error(f"[Plugins] Error loading plugin '{fname}': {e}")
    logging.info(f"[Plugins] Reloaded {count} plugins from {directory}")
    _emit_event("plugins_reloaded", {"directory": directory, "count": count})

    if auto_reload:
        threading.Thread(target=_plugin_auto_reload, args=(directory,), daemon=True).start()

def _plugin_auto_reload(directory: str):
    """Background thread to watch for plugin file changes and reload on the fly."""
    import time as _time
    last_mtimes = {}
    while True:
        changed = False
        for fname in os.listdir(directory):
            if fname.endswith(".py") and not fname.startswith("_"):
                path = os.path.join(directory, fname)
                mtime = os.path.getmtime(path)
                if fname not in last_mtimes or mtime != last_mtimes[fname]:
                    changed = True
                    last_mtimes[fname] = mtime
        if changed:
            reload_plugins(directory)
        _time.sleep(2)

def load_plugin_from_file(filepath: str, memory_manager=None):
    """Load and register a plugin from a single file. Supports memory manager injection."""
    name = os.path.splitext(os.path.basename(filepath))[0]
    try:
        spec = importlib.util.spec_from_file_location(name, filepath)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "register"):
            argspec = inspect.getfullargspec(module.register)
            if "memory_manager" in argspec.args and memory_manager:
                module.register(register_plugin, memory_manager)
            else:
                module.register(register_plugin)
            logging.info(f"[Plugins] Loaded plugin from {filepath}")
    except Exception as e:
        logging.error(f"[Plugins] Error loading plugin from {filepath}: {e}")

def validate_plugin_args(name: str, args: List[Any]) -> bool:
    """Check if a plugin can be called with the given args."""
    plugin = _plugins.get(name)
    if not plugin:
        return False
    func = plugin["func"]
    sig = inspect.signature(func)
    try:
        sig.bind(*args)
        return True
    except TypeError as e:
        logging.warning(f"[Plugins] Arg validation failed for '{name}': {e}")
        return False

def list_plugin_tags() -> List[str]:
    """Return all tags used by registered plugins."""
    tags = set()
    for plugin in _plugins.values():
        tags.update(plugin.get("tags", []))
    return list(tags)

def get_plugins_by_tag(tag: str) -> List[str]:
    """List plugin names for a given tag."""
    return [name for name, plugin in _plugins.items() if tag in plugin.get("tags", [])]

def set_plugin_permission(name: str, permissions: List[str]):
    """Set permissions for a plugin."""
    if name in _plugins:
        _plugins[name]["permissions"] = permissions

def get_plugin_permissions(name: str) -> List[str]:
    """Get permissions required by a plugin."""
    if name in _plugins:
        return _plugins[name].get("permissions", [])
    return []

def register_plugin_state_handler(name: str, get_state: Callable[[], Any], set_state: Callable[[Any], None]):
    """Allow plugins to register state get/set handlers."""
    if name in _plugins:
        _plugins[name]["get_state"] = get_state
        _plugins[name]["set_state"] = set_state

def get_plugin_state(name: str) -> Any:
    """Get persistent state for a plugin (if supported)."""
    if name in _plugins and "get_state" in _plugins[name]:
        return _plugins[name]["get_state"]()
    return None

def set_plugin_state(name: str, state: Any):
    """Set persistent state for a plugin (if supported)."""
    if name in _plugins and "set_state" in _plugins[name]:
        _plugins[name]["set_state"](state)

def plugin_stats() -> Dict[str, Any]:
    """Basic plugin analytics (run/fail count per plugin)."""
    stats = {}
    for entry in _plugin_history:
        name = entry["plugin"]
        stats.setdefault(name, {"runs": 0, "fails": 0})
        stats[name]["runs"] += 1
        if entry["status"] != "success":
            stats[name]["fails"] += 1
    return stats

def is_plugin_compatible(name: str, required_api_version: str = "1.0") -> bool:
    """Check plugin version compatibility (simple major.minor match)."""
    plugin = _plugins.get(name)
    if not plugin:
        return False
    return plugin.get("version", "1.0").split(".")[0] == required_api_version.split(".")[0]

def report_plugin_fault(name: str):
    """Track and auto-disable plugins that repeatedly fail."""
    _plugin_faults[name] = _plugin_faults.get(name, 0) + 1
    if _plugin_faults[name] > _PLUGIN_FAULT_LIMIT:
        logging.warning(f"[Plugins] Plugin {name} has failed repeatedly. Auto-disabling.")
        if name in _plugins:
            _plugins[name]["enabled"] = False
        _emit_lifecycle_event("disabled", name, {"reason": "fault_limit_exceeded"})

def load_remote_plugin(url: str):
    """Stub for loading plugin from remote source (future/distributed plugins)."""
    # TODO: Download, verify, and load plugin from remote URL
    pass

# --- API/GUI integration helpers with docstrings ---
def plugin_api_list() -> List[Dict[str, Any]]:
    """API: List all plugins."""
    return available_plugins()

def plugin_api_run(name: str, args: List[Any], user: Optional[str] = None) -> Any:
    """API: Run a plugin."""
    return run_plugin(name, args, user=user)

def plugin_api_help(name: str) -> str:
    """API: Get plugin help/usage."""
    return plugin_help(name)

def plugin_api_history(limit: int = 10) -> List[Dict[str, Any]]:
    """API: Get plugin run history."""
    return plugin_history(limit=limit)

def plugin_api_stats() -> Dict[str, Any]:
    """API: Get plugin analytics."""
    return plugin_stats()

# --- Compliance/audit: add hooks for GDPR, audit, or event-driven plugin compliance as needed ---