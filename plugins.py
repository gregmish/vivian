import logging
import inspect
import traceback
import os
import importlib.util
import threading
import multiprocessing
import json
import time
from typing import Callable, Dict, Any, List, Optional

# ========== Core Plugin Infrastructure ==========
_plugins: Dict[str, Dict[str, Any]] = {}
_plugin_history: List[Dict[str, Any]] = []
_HISTORY_LIMIT = 100
_plugin_event_hook: Optional[Callable[[str, Dict[str, Any]], None]] = None
_plugin_event_subscribers: Dict[str, List[Callable[[str, Dict[str, Any]], None]]] = {}
_plugin_faults: Dict[str, int] = {}
_PLUGIN_FAULT_LIMIT = 5

def set_plugin_event_hook(hook: Callable[[str, Dict[str, Any]], None]):
    global _plugin_event_hook
    _plugin_event_hook = hook

def subscribe_to_event(event_type: str, handler: Callable[[str, Dict[str, Any]], None]):
    _plugin_event_subscribers.setdefault(event_type, []).append(handler)

def _emit_event(event: str, data: Dict[str, Any]):
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
    if name in _plugins:
        # Attempt graceful teardown if plugin defines teardown
        if "teardown" in _plugins[name]:
            try:
                _plugins[name]["teardown"]()
            except Exception as e:
                logging.warning(f"[Plugins] Error in teardown for '{name}': {e}")
        del _plugins[name]
        logging.info(f"[Plugins] Unregistered plugin '{name}'")
        _emit_event("plugin_unregistered", {"name": name})
        _emit_lifecycle_event("unload", name, {})

def available_plugins(tags: Optional[List[str]] = None, permissions: Optional[List[str]] = None) -> List[Dict[str, Any]]:
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
    plugin = _plugins.get(name)
    if not plugin:
        return {}
    return {k: v for k, v in plugin.items() if k != "func"}

def plugin_help(name: str) -> str:
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

def run_plugin(name: str, args: List[Any], user: Optional[str] = None, safe: bool = False, timeout: float = 10, memory_limit: int = 64*1024*1024) -> Any:
    plugin = _plugins.get(name)
    if not plugin or not plugin.get("enabled", True):
        result = f"[Plugins] Plugin '{name}' not found or is disabled."
        _emit_history(name, user, args, None, result, "not_found")
        return result

    if safe:
        return run_plugin_sandboxed(name, args, user=user, timeout=timeout, memory_limit=memory_limit)

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

def run_plugin_sandboxed(name, args, user=None, timeout=10, memory_limit=64*1024*1024):
    """Run a plugin in a subprocess with timeout and memory limit (sandbox)."""
    def target(q):
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
        except Exception:
            pass
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
    return _plugin_history[-limit:]

# ========== Advanced: Plugin Manifests & Dependency Resolution ==========
def load_plugin_manifest(plugin_dir, plugin_name):
    for ext in [".yaml", ".yml", ".json"]:
        manifest_path = os.path.join(plugin_dir, plugin_name, f"plugin{ext}")
        if os.path.exists(manifest_path):
            try:
                if ext in [".yaml", ".yml"]:
                    import yaml
                    with open(manifest_path) as f:
                        return yaml.safe_load(f)
                else:
                    with open(manifest_path) as f:
                        return json.load(f)
            except Exception as e:
                logging.warning(f"[Plugins] Failed parsing manifest {manifest_path}: {e}")
    return {}

def resolve_plugin_dependencies(plugin_manifests):
    # Returns plugin load order based on dependency graph (simple topological sort)
    from collections import defaultdict, deque
    dep_graph = defaultdict(set)
    for name, manifest in plugin_manifests.items():
        deps = manifest.get("dependencies", [])
        for dep in deps:
            dep_graph[name].add(dep)
    visited = set()
    result = []
    def visit(n):
        if n in visited:
            return
        for d in dep_graph[n]:
            visit(d)
        visited.add(n)
        result.append(n)
    for n in plugin_manifests:
        visit(n)
    return result

# ========== Enhanced: Reload Plugins, Hot Unplug, Manifest, Async Register, Dependency Order ==========
def reload_plugins(
    directory: str = "plugins",
    auto_reload: bool = False,
    **system_deps
):
    """
    Reload all plugins from a directory.
    Supports manifest, dependency resolution, sandboxing, async register, hot unplug, event bus, and version compatibility.
    """
    logging.info(f"[Plugins] Reloading plugins from {directory}")
    count = 0
    loaded_plugin_names = set()
    manifests = {}
    # Load all manifests first for dependency resolution
    for fname in os.listdir(directory):
        if fname.endswith(".py") and not fname.startswith("_"):
            name = os.path.splitext(fname)[0]
            manifests[name] = load_plugin_manifest(directory, name)
    load_order = resolve_plugin_dependencies(manifests)
    # Load in dependency order
    for name in load_order:
        fname = f"{name}.py"
        path = os.path.join(directory, fname)
        if not os.path.exists(path):
            continue
        loaded_plugin_names.add(name)
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            manifest = manifests.get(name, {})
            if hasattr(module, "register"):
                argspec = inspect.getfullargspec(module.register)
                kwargs = {k: v for k, v in system_deps.items()
                          if k in argspec.args or k in argspec.kwonlyargs}
                if "register_plugin" in argspec.args:
                    kwargs["register_plugin"] = register_plugin
                # Manifest-based injection of permissions, tags, etc.
                if manifest.get("permissions") and "permissions" in argspec.args:
                    kwargs["permissions"] = manifest["permissions"]
                if manifest.get("tags") and "tags" in argspec.args:
                    kwargs["tags"] = manifest["tags"]
                # Version compatibility
                plugin_version = getattr(module, "PLUGIN_API_VERSION", manifest.get("api_version", "1.0"))
                platform_version = "1.0"
                if plugin_version.split(".")[0] != platform_version.split(".")[0]:
                    logging.warning(f"[Plugins] {name} version mismatch: {plugin_version} (required: {platform_version})")
                    _emit_event("plugin_version_mismatch", {"name": name, "plugin_version": plugin_version, "platform_version": platform_version})
                    continue
                # Register (sync or async)
                if inspect.iscoroutinefunction(module.register):
                    import asyncio
                    asyncio.run(module.register(**kwargs))
                else:
                    module.register(**kwargs)
                # Attach teardown if present
                if hasattr(module, "teardown"):
                    _plugins[name]["teardown"] = module.teardown
                count += 1
            else:
                logging.warning(f"[Plugins] '{fname}' does not have a register() function")
        except Exception as e:
            logging.error(f"[Plugins] Error loading plugin '{fname}': {e}\n{traceback.format_exc()}")
            _emit_event("plugin_load_error", {"name": name, "error": str(e), "traceback": traceback.format_exc()})

    # Unregister plugins whose files were removed (hot-unplug support)
    to_remove = [p for p in list(_plugins.keys()) if p not in loaded_plugin_names]
    for p in to_remove:
        unregister_plugin(p)
        logging.info(f"[Plugins] Unregistered plugin '{p}' (file removed)")

    logging.info(f"[Plugins] Reloaded {count} plugins from {directory}")
    _emit_event("plugins_reloaded", {"directory": directory, "count": count})

    if auto_reload:
        threading.Thread(target=lambda: _plugin_auto_reload(directory, **system_deps), daemon=True).start()

def _plugin_auto_reload(directory: str, **system_deps):
    import time as _time
    last_mtimes = {}
    while True:
        changed = False
        try:
            files = [f for f in os.listdir(directory) if f.endswith(".py") and not f.startswith("_")]
            curr_files = set(files)
            curr_mtimes = {}
            for fname in files:
                path = os.path.join(directory, fname)
                mtime = os.path.getmtime(path)
                curr_mtimes[fname] = mtime
                if fname not in last_mtimes or mtime != last_mtimes[fname]:
                    changed = True
            for fname in set(last_mtimes.keys()) - curr_files:
                changed = True
            if changed:
                reload_plugins(directory, **system_deps)
                last_mtimes = curr_mtimes
        except Exception as e:
            logging.error(f"[Plugins] Auto-reload error: {e}\n{traceback.format_exc()}")
        _time.sleep(2)

def load_remote_plugin(url: str):
    """Download and register a plugin from a remote URL (requires trusted source)."""
    import requests
    resp = requests.get(url)
    if resp.status_code == 200:
        fname = os.path.basename(url)
        path = os.path.join("plugins", fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(resp.text)
        logging.info(f"[Plugins] Downloaded remote plugin: {fname}")
        reload_plugins("plugins")
    else:
        logging.error(f"[Plugins] Remote plugin fetch failed {url}: {resp.status_code}")

def validate_plugin_args(name: str, args: List[Any]) -> bool:
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
    tags = set()
    for plugin in _plugins.values():
        tags.update(plugin.get("tags", []))
    return list(tags)

def get_plugins_by_tag(tag: str) -> List[str]:
    return [name for name, plugin in _plugins.items() if tag in plugin.get("tags", [])]

def set_plugin_permission(name: str, permissions: List[str]):
    if name in _plugins:
        _plugins[name]["permissions"] = permissions

def get_plugin_permissions(name: str) -> List[str]:
    if name in _plugins:
        return _plugins[name].get("permissions", [])
    return []

def register_plugin_state_handler(name: str, get_state: Callable[[], Any], set_state: Callable[[Any], None]):
    if name in _plugins:
        _plugins[name]["get_state"] = get_state
        _plugins[name]["set_state"] = set_state

def get_plugin_state(name: str) -> Any:
    if name in _plugins and "get_state" in _plugins[name]:
        return _plugins[name]["get_state"]()
    return None

def set_plugin_state(name: str, state: Any):
    if name in _plugins and "set_state" in _plugins[name]:
        _plugins[name]["set_state"](state)

def plugin_stats() -> Dict[str, Any]:
    stats = {}
    for entry in _plugin_history:
        name = entry["plugin"]
        stats.setdefault(name, {"runs": 0, "fails": 0})
        stats[name]["runs"] += 1
        if entry["status"] != "success":
            stats[name]["fails"] += 1
    return stats

def is_plugin_compatible(name: str, required_api_version: str = "1.0") -> bool:
    plugin = _plugins.get(name)
    if not plugin:
        return False
    return plugin.get("version", "1.0").split(".")[0] == required_api_version.split(".")[0]

def report_plugin_fault(name: str):
    _plugin_faults[name] = _plugin_faults.get(name, 0) + 1
    if _plugin_faults[name] > _PLUGIN_FAULT_LIMIT:
        logging.warning(f"[Plugins] Plugin {name} has failed repeatedly. Auto-disabling.")
        if name in _plugins:
            _plugins[name]["enabled"] = False
        _emit_lifecycle_event("disabled", name, {"reason": "fault_limit_exceeded"})

# ========== API/GUI Integration ==========
def plugin_api_list() -> List[Dict[str, Any]]:
    return available_plugins()

def plugin_api_run(name: str, args: List[Any], user: Optional[str] = None) -> Any:
    return run_plugin(name, args, user=user)

def plugin_api_help(name: str) -> str:
    return plugin_help(name)

def plugin_api_history(limit: int = 10) -> List[Dict[str, Any]]:
    return plugin_history(limit=limit)

def plugin_api_stats() -> Dict[str, Any]:
    return plugin_stats()

# ========== Plugin Health Monitoring ==========
def heartbeat_check():
    """Background thread that checks for plugin health/heartbeat."""
    while True:
        for name, plugin in list(_plugins.items()):
            health = None
            try:
                health = None
                if "health" in plugin:
                    health = plugin["health"]()
                elif hasattr(plugin.get("func"), "health"):
                    health = plugin["func"].health()
                # If plugin has missed multiple heartbeats, disable it
                if health is False:
                    report_plugin_fault(name)
            except Exception as e:
                logging.warning(f"[Plugins] Health check failed for {name}: {e}")
                report_plugin_fault(name)
        time.sleep(30)

# Optionally start the heartbeat monitor in your main app
# threading.Thread(target=heartbeat_check, daemon=True).start()
# ========== Alias for GUI compatibility ==========
load_plugins = reload_plugins