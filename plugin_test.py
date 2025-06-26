import os
import sys
import json
import argparse
import logging
import traceback
import time
from datetime import datetime
from typing import Any, Dict, Tuple, List
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from VivianCore.plugin_engine import PluginEngine
except ImportError:
    print("ERROR: VivianCore.plugin_engine not found. Is Vivian properly installed?")
    sys.exit(1)

def color(text, code):
    """ANSI color helper."""
    return f"\033[{code}m{text}\033[0m"

def banner(config):
    logo = config.get("branding", {}).get("logo", "")
    tagline = config.get("branding", {}).get("tagline", "")
    name = config.get("name", "Vivian AGI")
    version = config.get("version", "?.?.?")
    theme = config.get("branding", {}).get("theme", "default")
    print(color("┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓", 94))
    print(color(f"┃ {name} Supreme Plugin Test Suite v{version}".center(74) + "┃", 96))
    if tagline:
        print(color(f"┃ {tagline.center(72)} ┃", 95))
    print(color("┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", 94))
    if logo and os.path.exists(logo):
        print(color(f"[Logo: {logo}]", 93))
    print(color(f"Theme: {theme}", 90))

def load_config(config_path: str) -> Dict[str, Any]:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "r") as f:
        return json.load(f)

def system_info(config):
    print(color("\n[Vivian System & Environment Info]", 94))
    print(f"User: {os.environ.get('USER', 'unknown')}")
    print(f"Time: {datetime.utcnow().isoformat()} UTC")
    print(f"Config: {config.get('name', '?')} v{config.get('version', '?')}")
    print(f"Environment: {config.get('environment', '?')}")
    print(f"Plugin Dir: {config.get('plugins', {}).get('directory', 'plugins')}")
    print(f"Features: {', '.join([k for k, v in config.get('features', {}).items() if v is True])}")
    print(f"Python: {sys.version}")
    print(f"Platform: {os.uname().sysname} {os.uname().release}")
    print(f"CPU Cores: {os.cpu_count()}")
    print(f"Working Dir: {os.getcwd()}")
    print(f"Memory: {config.get('memory', {}).get('type', 'N/A')} limit {config.get('memory', {}).get('max_entries', 'N/A')}")
    print()

def summarize(results: Dict[str, Any], parallel: bool):
    total = len(results)
    success = sum(1 for r in results.values() if r["status"] == "success")
    errors = sum(1 for r in results.values() if r["status"] == "error")
    skipped = sum(1 for r in results.values() if r["status"] == "skipped")
    print(color(f"\nSummary: {success} passed, {errors} failed, {skipped} skipped, {total} total", 95))
    print(color(f"Execution mode: {'parallel' if parallel else 'sequential'}", 90))

def print_metadata(plugin):
    meta = getattr(plugin, "plugin_info", None)
    if callable(meta):
        info = meta()
        print(color(f"    ├─ Version: {info.get('version', 'N/A')}", 90))
        print(color(f"    ├─ Author: {info.get('author', 'N/A')}", 90))
        print(color(f"    ├─ Tags: {', '.join(info.get('tags', []))}", 90))
        print(color(f"    └─ Desc: {info.get('description', '(none)')}", 90))
    elif plugin.__doc__:
        print(color(f"    └─ Doc: {plugin.__doc__.strip()}", 90))

def discover_plugin_tests(plugin):
    tests = []
    # All common and advanced test entrypoints (Vivian standards)
    for attr in [
        "test", "validate", "diagnose", "coverage", "lint", "benchmark", "healthcheck", "security_audit",
        "integration_test", "performance_test", "load_test", "compliance_test", "doc_test", "api_test"
    ]:
        if hasattr(plugin, attr):
            tests.append((attr, getattr(plugin, attr)))
    if callable(plugin):
        tests.append(("main", plugin))
    return tests

def run_plugin_test(label: str, test_fn, debug: bool) -> Tuple[str, Dict[str, Any]]:
    start = time.time()
    try:
        output = test_fn()
        status = "success"
    except NotImplementedError:
        output = "(skipped: not implemented)"
        status = "skipped"
    except Exception as e:
        output = str(e)
        status = "error"
        if debug:
            print(color(f"[ERROR] {label}:", 91))
            traceback.print_exc()
        else:
            print(color(f"[ERROR] {label}: {e}", 91))
    elapsed = time.time() - start
    return label, {
        "status": status,
        "output": output,
        "time_sec": round(elapsed, 4)
    }

def export_html_report(path, results, config, parallel):
    now = datetime.utcnow().isoformat()
    rows = ""
    for name, res in results.items():
        color_class = "ok" if res["status"] == "success" else ("skip" if res["status"] == "skipped" else "fail")
        rows += f"<tr class='{color_class}'><td>{name}</td><td>{res['status']}</td><td>{res['time_sec']}</td><td><pre>{res['output']}</pre></td></tr>\n"
    html = f"""<!DOCTYPE html>
<html>
<head>
<title>Vivian Supreme Plugin Test Report</title>
<style>
    body {{ font-family: Arial, sans-serif; background:#222; color:#eee; }}
    .ok {{ background:#2e4; }}
    .fail {{ background:#e44; }}
    .skip {{ background:#ee4; color:#222; }}
    table {{ border-collapse: collapse; width:100%; }}
    pre {{ white-space: pre-wrap; word-break: break-all; }}
    th,td {{ border:1px solid #666; padding:8px; }}
    th {{ background:#333; }}
</style>
</head>
<body>
<h1>Vivian Plugin Test Report</h1>
<p>Time: {now}</p>
<p>Vivian version: {config.get('version','?')}</p>
<p>Execution mode: {'parallel' if parallel else 'sequential'}</p>
<table>
<tr><th>Plugin</th><th>Status</th><th>Time (sec)</th><th>Output</th></tr>
{rows}
</table>
</body>
</html>
"""
    with open(path, "w") as f:
        f.write(html)
    print(color(f"HTML report written to {path}", 96))

def plugin_coverage(plugin) -> float:
    if hasattr(plugin, "coverage"):
        try:
            c = plugin.coverage()
            if isinstance(c, (tuple, list)) and len(c) > 0:
                return float(c[0])
            return float(c)
        except Exception:
            return 0.0
    return 0.0

def plugin_lint(plugin) -> str:
    if hasattr(plugin, "lint"):
        try:
            return plugin.lint()
        except Exception as e:
            return f"Lint error: {e}"
    return "N/A"

def plugin_health(plugin) -> str:
    if hasattr(plugin, "healthcheck"):
        try:
            return plugin.healthcheck()
        except Exception as e:
            return f"Healthcheck error: {e}"
    return "N/A"

def plugin_security(plugin) -> str:
    if hasattr(plugin, "security_audit"):
        try:
            return plugin.security_audit()
        except Exception as e:
            return f"Security audit error: {e}"
    return "N/A"

def plugin_compliance(plugin) -> str:
    if hasattr(plugin, "compliance_test"):
        try:
            return plugin.compliance_test()
        except Exception as e:
            return f"Compliance test error: {e}"
    return "N/A"

def plugin_performance(plugin) -> str:
    if hasattr(plugin, "performance_test"):
        try:
            return plugin.performance_test()
        except Exception as e:
            return f"Performance test error: {e}"
    return "N/A"

def plugin_integration(plugin) -> str:
    if hasattr(plugin, "integration_test"):
        try:
            return plugin.integration_test()
        except Exception as e:
            return f"Integration test error: {e}"
    return "N/A"

def main():
    parser = argparse.ArgumentParser(description="Vivian Supreme Plugin Tester")
    parser.add_argument("--config", default="config/vivian_config.json", help="Path to Vivian config JSON")
    parser.add_argument("--list", action="store_true", help="List plugins with metadata")
    parser.add_argument("--run", action="store_true", help="Run all plugins (default)")
    parser.add_argument("--export", help="Export results to JSON file")
    parser.add_argument("--debug", action="store_true", help="Show error tracebacks")
    parser.add_argument("--profile", action="store_true", help="Time plugin execution")
    parser.add_argument("--filter", help="Only run plugins containing this string")
    parser.add_argument("--info", action="store_true", help="Show Vivian config, env, and system info")
    parser.add_argument("--report", help="Export a detailed HTML report")
    parser.add_argument("--failfast", action="store_true", help="Stop on first plugin error")
    parser.add_argument("--all", action="store_true", help="Run all available test/validate/diagnose/main/etc methods in each plugin")
    parser.add_argument("--parallel", action="store_true", help="Run plugins in parallel (threaded)")
    parser.add_argument("--lint", action="store_true", help="Show plugin lint results")
    parser.add_argument("--health", action="store_true", help="Show plugin healthcheck results")
    parser.add_argument("--coverage", action="store_true", help="Show plugin test coverage (if available)")
    parser.add_argument("--security", action="store_true", help="Show plugin security audit results")
    parser.add_argument("--compliance", action="store_true", help="Show plugin compliance test results")
    parser.add_argument("--performance", action="store_true", help="Show plugin performance test results")
    parser.add_argument("--integration", action="store_true", help="Show plugin integration tests results")
    parser.add_argument("--live", action="store_true", help="Enable live reload mode (auto-retest on file change)")
    parser.add_argument("--max-workers", type=int, default=8, help="Max threads for parallel mode")
    args = parser.parse_args()

    base_path = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config if os.path.isabs(args.config) else os.path.join(base_path, args.config)

    try:
        config = load_config(config_path)
    except Exception as e:
        print(color(f"[Config Error] {e}", 91))
        sys.exit(1)

    log_level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    if args.info:
        system_info(config)
        sys.exit(0)

    banner(config)
    plugin_dir = os.path.join(base_path, config["plugins"]["directory"])
    engine = PluginEngine(plugin_dir, config)
    engine.load_plugins()

    all_plugins = engine.plugins
    if args.filter:
        plugins = {n: p for n, p in all_plugins.items() if args.filter.lower() in n.lower()}
    else:
        plugins = all_plugins

    print(color(f"\nLoaded Plugins ({len(plugins)}/{len(all_plugins)})", 92))
    for name in plugins:
        print(color(f" - {name}", 94))
        print_metadata(plugins[name])

    if args.lint:
        print(color("\n[Plugin Lint Results]", 96))
        for name, plugin in plugins.items():
            print(color(f"[{name}]", 94), "=>", plugin_lint(plugin))
    if args.health:
        print(color("\n[Plugin Healthcheck Results]", 96))
        for name, plugin in plugins.items():
            print(color(f"[{name}]", 94), "=>", plugin_health(plugin))
    if args.coverage:
        print(color("\n[Plugin Coverage]", 96))
        for name, plugin in plugins.items():
            pct = plugin_coverage(plugin)
            print(color(f"[{name}]", 94), f"=> {pct:.2f}%")
    if args.security:
        print(color("\n[Plugin Security Audit Results]", 96))
        for name, plugin in plugins.items():
            print(color(f"[{name}]", 94), "=>", plugin_security(plugin))
    if args.compliance:
        print(color("\n[Plugin Compliance Test Results]", 96))
        for name, plugin in plugins.items():
            print(color(f"[{name}]", 94), "=>", plugin_compliance(plugin))
    if args.performance:
        print(color("\n[Plugin Performance Test Results]", 96))
        for name, plugin in plugins.items():
            print(color(f"[{name}]", 94), "=>", plugin_performance(plugin))
    if args.integration:
        print(color("\n[Plugin Integration Test Results]", 96))
        for name, plugin in plugins.items():
            print(color(f"[{name}]", 94), "=>", plugin_integration(plugin))
    if any([args.list, args.lint, args.health, args.coverage, args.security, args.compliance, args.performance, args.integration]):
        return

    # Main run logic
    results = {}
    parallel = args.parallel
    # Discover test callables
    plugin_tests: List[Tuple[str, Any]] = []
    for name, plugin in plugins.items():
        tests = discover_plugin_tests(plugin) if args.all else [("main", plugin)]
        for test_name, test_fn in tests:
            label = f"{name}.{test_name}" if test_name != "main" else name
            plugin_tests.append((label, test_fn))

    print(color(f"\n[Running Plugins{' in Parallel' if parallel else ''}...]", 96))
    if parallel:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_to_label = {executor.submit(run_plugin_test, label, test_fn, args.debug): label for label, test_fn in plugin_tests}
            for future in as_completed(future_to_label):
                label = future_to_label[future]
                try:
                    label, res = future.result()
                    results[label] = res
                    if res["status"] == "success":
                        print(color(f"[{label}]", 92), "=>", res["output"])
                    elif res["status"] == "skipped":
                        print(color(f"[SKIPPED] {label}", 93))
                    else:
                        print(color(f"[ERROR] {label}: {res['output']}", 91))
                    if args.profile and res["status"] == "success":
                        print(color(f"   (time: {res['time_sec']:.4f} sec)", 90))
                except Exception as exc:
                    print(color(f"[FATAL ERROR] {label}: {exc}", 91))
                    if args.failfast:
                        break
    else:
        for label, test_fn in plugin_tests:
            label, res = run_plugin_test(label, test_fn, args.debug)
            results[label] = res
            if res["status"] == "success":
                print(color(f"[{label}]", 92), "=>", res["output"])
            elif res["status"] == "skipped":
                print(color(f"[SKIPPED] {label}", 93))
            else:
                print(color(f"[ERROR] {label}: {res['output']}", 91))
            if args.profile and res["status"] == "success":
                print(color(f"   (time: {res['time_sec']:.4f} sec)", 90))
            if args.failfast and res["status"] == "error":
                break

    summarize(results, parallel)
    if args.export:
        with open(args.export, "w") as out:
            json.dump(results, out, indent=2)
        print(color(f"Results exported to {args.export}", 93))
    if args.report:
        export_html_report(args.report, results, config, parallel)

    if args.live:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            class PluginReloadHandler(FileSystemEventHandler):
                def on_any_event(self, event):
                    print(color(f"\n[Live Reload] Detected change: {event.src_path}", 93))
                    main()
            observer = Observer()
            observer.schedule(PluginReloadHandler(), plugin_dir, recursive=True)
            observer.start()
            print(color("[Live reload enabled: Monitoring plugin directory... Press Ctrl+C to exit]", 96))
            while True:
                time.sleep(1)
        except ImportError:
            print(color("[Live reload requires watchdog: pip install watchdog]", 91))
        except KeyboardInterrupt:
            print(color("\n[Live reload stopped]", 94))

if __name__ == "__main__":
    main()