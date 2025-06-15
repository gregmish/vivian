import os
import logging
import json
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
import threading
import difflib

GENERATED_CODE_DIR = os.path.join("generated_code")
SNAPSHOT_DIR = os.path.join(GENERATED_CODE_DIR, "snapshots")
METADATA_FILE = os.path.join(GENERATED_CODE_DIR, "codegen_meta.json")
os.makedirs(GENERATED_CODE_DIR, exist_ok=True)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

class LLMStub:
    def enhance_code(self, prompt: str) -> str:
        # Placeholder: integrate with LLM for code improvement
        return f"# [LLM enhanced]\n{prompt}"

    def generate_tests(self, code: str) -> str:
        # Placeholder: generate unit tests for code
        return f"# [Generated test]\ndef test_example():\n    assert True"

    def code_review(self, code: str) -> List[str]:
        return ["[LLM review] Code looks syntactically correct."]

    def summarize_code(self, code: str) -> str:
        return f"[LLM summary] Code is {len(code.splitlines())} lines."

    def refactor_code(self, code: str, instruction: str) -> str:
        return f"# [Refactored]\n{code}"

    def semantic_diff(self, code1: str, code2: str) -> str:
        # Placeholder: LLM or AST-based diff
        return "\n".join(difflib.unified_diff(code1.splitlines(), code2.splitlines()))

    def generate_doc(self, code: str) -> str:
        return f"# [LLM doc] This module provides ..."

    def fix_imports(self, code: str) -> str:
        return code

    def classify_code(self, code: str) -> List[str]:
        return ["general"]

    def suggest_dependencies(self, code: str) -> List[str]:
        return []

class CodeGenerator:
    """
    Ultimate self-evolving code engine: generation, review, tests, lint, versioning, docs, security, sharing, plugins, UI-ready.
    """
    def __init__(self, llm: Optional[Any] = None):
        self.llm = llm or LLMStub()
        self.lock = threading.RLock()
        self.meta = self._load_meta()
        self.event_log: List[Dict[str, Any]] = []
        self.plugins: List[Callable[[str, Dict[str, Any]], None]] = []

    # ----------- Generation & Improvement -----------

    def generate_template(self, name: str, goal: str, tags: Optional[List[str]] = None, project: Optional[str] = None) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.py"
        filepath = os.path.join(GENERATED_CODE_DIR, filename)
        code = f'''"""
Auto-generated module for: {goal}
Created at: {timestamp}
"""

def {name}_task():
    # TODO: Implement logic for: {goal}
    print("Task '{goal}' is not yet implemented.")
'''
        if self._write_file(filepath, code):
            self._update_meta(filename, goal, tags or [], "generated", timestamp, project=project)
            self._log_event("generate_template", {"file": filename, "goal": goal, "project": project})
            self._save_snapshot(filename, code)
            self._run_post_generation(filename, code)
            return filepath
        return ""

    def evolve_code(self, base_code: str, instruction: str, filename: Optional[str] = None) -> str:
        improved_code = self.llm.enhance_code(f"Improve this code to meet: {instruction}\n\n{base_code}")
        if filename:
            self._write_file(os.path.join(GENERATED_CODE_DIR, filename), improved_code)
            self._save_snapshot(filename, improved_code)
            self._log_event("evolve_code", {"file": filename, "instruction": instruction})
            self._run_post_generation(filename, improved_code)
        return improved_code

    def write_custom_code(self, name: str, code: str, tags: Optional[List[str]] = None, description: str = "", project: Optional[str] = None) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}.py"
        filepath = os.path.join(GENERATED_CODE_DIR, filename)
        if self._write_file(filepath, code):
            self._update_meta(filename, description, tags or [], "custom", timestamp, project=project)
            self._log_event("write_custom_code", {"file": filename, "desc": description, "project": project})
            self._save_snapshot(filename, code)
            self._run_post_generation(filename, code)
            return filepath
        return ""

    # ----------- Automated Testing -----------

    def generate_and_run_tests(self, filename: str):
        code = self._read_file(os.path.join(GENERATED_CODE_DIR, filename))
        if not code: return
        test_code = self.llm.generate_tests(code)
        test_filename = filename.replace(".py", "_test.py")
        test_path = os.path.join(GENERATED_CODE_DIR, test_filename)
        self._write_file(test_path, test_code)
        test_result = self._run_pytest(test_path)
        self.meta[filename]["last_test_result"] = test_result
        self._save_meta()
        self._log_event("generate_and_run_tests", {"file": filename, "test_result": test_result})

    def _run_pytest(self, test_path: str) -> str:
        try:
            result = subprocess.run(["python", "-m", "pytest", test_path], capture_output=True, timeout=10, text=True)
            return result.stdout + "\n" + result.stderr
        except Exception as e:
            return f"[Test error] {e}"

    # ----------- Linting & Static Analysis -----------

    def run_linter(self, filename: str):
        path = os.path.join(GENERATED_CODE_DIR, filename)
        try:
            result = subprocess.run(["flake8", path], capture_output=True, timeout=10, text=True)
            lint_result = result.stdout or "[OK]"
        except Exception as e:
            lint_result = f"[Lint error] {e}"
        self.meta[filename]["lint"] = lint_result
        self._save_meta()
        self._log_event("run_linter", {"file": filename, "lint": lint_result})

    # ----------- Dependency & Import Resolution -----------

    def analyze_imports(self, filename: str):
        code = self._read_file(os.path.join(GENERATED_CODE_DIR, filename))
        if not code: return
        dependencies = self.llm.suggest_dependencies(code)
        self.meta[filename]["dependencies"] = dependencies
        self._save_meta()
        self._log_event("analyze_imports", {"file": filename, "dependencies": dependencies})

    # ----------- Execution Sandbox -----------

    def run_code(self, filename: str, input_data: Optional[str] = None) -> Dict[str, Any]:
        path = os.path.join(GENERATED_CODE_DIR, filename)
        try:
            proc = subprocess.run(["python", path], input=input_data, capture_output=True, timeout=10, text=True)
            result = {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
        except Exception as e:
            result = {"error": str(e)}
        self._log_event("run_code", {"file": filename, "result": result})
        return result

    # ----------- Multi-File/Project Support -----------

    def new_project(self, project_name: str, description: str = ""):
        proj_dir = os.path.join(GENERATED_CODE_DIR, project_name)
        os.makedirs(proj_dir, exist_ok=True)
        self.meta[project_name] = {"type": "project", "description": description, "files": [], "created": datetime.utcnow().strftime("%Y%m%d_%H%M%S")}
        self._save_meta()
        self._log_event("new_project", {"project": project_name})

    def add_file_to_project(self, project_name: str, filename: str):
        if project_name in self.meta:
            self.meta[project_name].setdefault("files", []).append(filename)
            self._save_meta()
            self._log_event("add_file_to_project", {"project": project_name, "file": filename})

    # ----------- Refactoring & Code Search -----------

    def refactor(self, filename: str, instruction: str):
        code = self._read_file(os.path.join(GENERATED_CODE_DIR, filename))
        if not code: return
        refactored = self.llm.refactor_code(code, instruction)
        self.write_custom_code(filename.replace(".py", "_refactored"), refactored)
        self._log_event("refactor", {"file": filename, "instruction": instruction})

    def search_code(self, keyword: str) -> List[str]:
        found = []
        for fname in os.listdir(GENERATED_CODE_DIR):
            if fname.endswith(".py"):
                code = self._read_file(os.path.join(GENERATED_CODE_DIR, fname))
                if code and keyword in code:
                    found.append(fname)
        return found

    # ----------- Versioning & Diff -----------

    def diff_versions(self, filename: str, v1: str, v2: str) -> str:
        snap1 = self._read_file(os.path.join(SNAPSHOT_DIR, f"{filename}_{v1}.snap"))
        snap2 = self._read_file(os.path.join(SNAPSHOT_DIR, f"{filename}_{v2}.snap"))
        if not snap1 or not snap2: return "[Error] Snapshots not found."
        return self.llm.semantic_diff(snap1, snap2)

    # ----------- Documentation -----------

    def generate_docs(self, filename: str):
        code = self._read_file(os.path.join(GENERATED_CODE_DIR, filename))
        if not code: return
        doc = self.llm.generate_doc(code)
        doc_path = filename.replace(".py", ".md")
        self._write_file(os.path.join(GENERATED_CODE_DIR, doc_path), doc)
        self._log_event("generate_docs", {"file": filename, "doc_path": doc_path})

    # ----------- Feedback Loop -----------

    def add_feedback(self, filename: str, feedback: str):
        self.meta[filename].setdefault("feedback", []).append({"feedback": feedback, "time": datetime.utcnow().isoformat()})
        self._save_meta()
        self._log_event("add_feedback", {"file": filename, "feedback": feedback})

    def adapt_from_feedback(self):
        # Placeholder: Adjust templates/prompts based on aggregate feedback
        self._log_event("adapt_from_feedback", {})

    # ----------- Security & Compliance -----------

    def run_security_scan(self, filename: str):
        path = os.path.join(GENERATED_CODE_DIR, filename)
        try:
            result = subprocess.run(["bandit", "-r", path], capture_output=True, timeout=10, text=True)
            bandit_result = result.stdout
        except Exception as e:
            bandit_result = f"[Security error] {e}"
        self.meta[filename]["bandit"] = bandit_result
        self._save_meta()
        self._log_event("run_security_scan", {"file": filename, "bandit": bandit_result})

    # ----------- API/CLI/Web Hooks -----------

    # (Placeholder for REST API/CLI/Web UI endpoints)
    # You would expose all above as endpoints/commands.

    # ----------- Collaboration -----------

    def export_file(self, filename: str, target: str):
        src = os.path.join(GENERATED_CODE_DIR, filename)
        try:
            with open(src, "r", encoding="utf-8") as fsrc, open(target, "w", encoding="utf-8") as ftgt:
                ftgt.write(fsrc.read())
            self._log_event("export_file", {"file": filename, "target": target})
            return True
        except Exception as e:
            self._log_event("export_file_failed", {"file": filename, "target": target, "error": str(e)})
            return False

    def share_gist(self, filename: str):
        # Placeholder: Integrate with GitHub Gist API
        self._log_event("share_gist", {"file": filename})

    # ----------- Plugin/Hook System -----------

    def register_plugin(self, callback: Callable[[str, Dict[str, Any]], None]):
        self.plugins.append(callback)

    def _run_post_generation(self, filename: str, code: str):
        # Run linters, tests, security scan, docs, etc, after generation
        self.run_linter(filename)
        self.generate_and_run_tests(filename)
        self.analyze_imports(filename)
        self.generate_docs(filename)
        self.run_security_scan(filename)
        self._notify_plugins("post_generation", {"file": filename, "code": code})

    def _notify_plugins(self, event: str, data: Dict[str, Any]):
        for cb in self.plugins:
            try:
                cb(event, data)
            except Exception as e:
                logging.error(f"[CodeGen] Plugin error: {e}")

    # ----------- Metadata, Snapshots, I/O, Event Log -----------

    def _load_meta(self) -> Dict[str, Any]:
        if os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _update_meta(self, filename: str, description: str, tags: List[str], mode: str, timestamp: str, project: Optional[str] = None):
        meta = {
            "description": description,
            "tags": list(set(tags)),
            "mode": mode,
            "created": timestamp,
            "last_modified": timestamp,
        }
        if project:
            meta["project"] = project
            self.add_file_to_project(project, filename)
        self.meta[filename] = meta
        self._save_meta()

    def _save_meta(self):
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, indent=2)

    def _save_snapshot(self, filename: str, code: str):
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"{filename}_{timestamp}.snap"
        snap_path = os.path.join(SNAPSHOT_DIR, snapshot_name)
        try:
            with open(snap_path, "w", encoding="utf-8") as f:
                f.write(code)
            self._log_event("save_snapshot", {"snap": snapshot_name})
        except Exception as e:
            logging.warning(f"[CodeGen] Failed to save snapshot: {e}")

    def _write_file(self, path: str, code: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
            return True
        except Exception as e:
            logging.error(f"[CodeGen] Failed to write file {path}: {e}")
            return False

    def _read_file(self, path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logging.error(f"[CodeGen] Failed to read file {path}: {e}")
            return None

    def _log_event(self, action: str, details: Dict[str, Any]):
        event = {
            "time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "action": action,
            "details": details
        }
        self.event_log.append(event)

    def get_event_log(self) -> List[Dict[str, Any]]:
        return self.event_log

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cg = CodeGenerator()
    path = cg.generate_template("mytask", "Process input data", tags=["ai", "stub"], project="datapipeline")
    print("Generated:", path)
    cg.new_project("ml_project", description="A project for ML scripts")
    cg.write_custom_code("ml_script", "# ML code here", tags=["ml"], project="ml_project")
    cg.generate_and_run_tests(os.path.basename(path))
    cg.run_linter(os.path.basename(path))
    cg.analyze_imports(os.path.basename(path))
    cg.run_security_scan(os.path.basename(path))
    cg.generate_docs(os.path.basename(path))
    cg.refactor(os.path.basename(path), "Rename function to process_data_task")
    print("Files:", cg.list_files(details=True))
    print("Snapshots:", cg.list_snapshots())
    cg.add_feedback(os.path.basename(path), "Works well, but more comments needed.")
    cg.export_file(os.path.basename(path), "shared_code.py")
    cg.share_gist(os.path.basename(path))
    print("Event log:", cg.get_event_log())