import logging
import threading
from VivianCore.llm.llm_memory import LLM_Memory
from VivianCore.llm.llm_persona import PersonaEngine
from VivianCore.llm.llm_toolbox import LLM_Tools
import time
import json

class LLMRouter:
    """
    Vivian-Grade LLMRouter:
    - Persona/mood/context aware prompt building, history injection, and memory prep.
    - Smart tool routing, LLM backend selection, audit, explainability, plugin/callback hooks, and security.
    - Supports streaming, prompt visualization, shell/API, and dynamic tool/model registration.
    """

    def __init__(self, config, model=None, user="system"):
        self.config = config
        self.model = model or config.get("llm.default", "openai:gpt-4")
        self.memory = LLM_Memory()
        self.persona_engine = PersonaEngine(config)
        self.tools = LLM_Tools()
        self.audit_log = []
        self.user = user
        self.hooks = []
        self.shell_thread = None
        self.api_thread = None
        self.lock = threading.Lock()

    def build_prompt(self, user_input, user=None, inject_tools=True):
        user = user or self.user
        persona = self.persona_engine.get_persona_profile()
        persona_desc = f"Persona: {persona['active']} ({persona['traits'].get('tone','neutral')}, mood: {persona['mood']})"
        memory_snippets = self.memory.recent("vivian_context", 5)
        memories = "\n".join([f"- {m['content']}" for m in memory_snippets])
        tool_outputs = ""
        if inject_tools:
            tool_snips = self.memory.recent("tool_output", 2)
            if tool_snips:
                tool_outputs = "\nRecent Tool Output:\n" + "\n".join([f"- {t['content']}" for t in tool_snips])
        context = (
            f"{persona_desc}\n"
            f"Recent Memory:\n{memories}{tool_outputs}\n\n"
            f"User: {user_input}"
        )
        self._audit("build_prompt", {"user": user, "input": user_input, "context": context})
        logging.info("[LLMRouter] Prompt built with persona, mood, and memory.")
        return context

    def send(self, user_input, user=None, use_tools=True, streaming=False):
        user = user or self.user
        prompt = self.build_prompt(user_input, user=user, inject_tools=use_tools)
        backend = self.model.split(":")[0]
        self._audit("send", {"backend": backend, "user_input": user_input, "prompt": prompt})

        # Pre-route to tool if command detected
        if use_tools and user_input.strip().startswith("!"):
            result = self.route_tool_command(user_input.strip()[1:], user=user)
            self.memory.save("vivian_context", f"Tool: {result}")
            return f"[TOOL] {result}"

        if backend == "openai":
            return self._send_openai(prompt, streaming=streaming)
        elif backend == "anthropic":
            return self._send_claude(prompt, streaming=streaming)
        else:
            return f"[Error] Unknown LLM backend: {backend}"

    def _send_openai(self, prompt, streaming=False):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.config.get("llm.openai_key"))
            response = client.chat.completions.create(
                model=self.model.split(":")[1],
                messages=[{"role": "user", "content": prompt}],
                stream=streaming
            )
            if streaming:
                output = ""
                for chunk in response:
                    part = chunk.choices[0].delta.content or ""
                    output += part
                    print(part, end="", flush=True)
                output = output.strip()
            else:
                output = response.choices[0].message.content.strip()
            self.memory.save("vivian_context", output)
            self._fire_hooks("llm_response", prompt, output)
            self._audit("llm_openai", {"prompt": prompt, "output": output})
            return output
        except Exception as e:
            self._audit("llm_openai_error", {"error": str(e)})
            return f"[OpenAI Error] {e}"

    def _send_claude(self, prompt, streaming=False):
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.config.get("llm.anthropic_key"))
            response = client.messages.create(
                model=self.model.split(":")[1],
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
                stream=streaming
            )
            if streaming:
                output = ""
                for chunk in response:
                    part = chunk.content[0].text if chunk.content else ""
                    output += part
                    print(part, end="", flush=True)
                output = output.strip()
            else:
                output = response.content[0].text.strip()
            self.memory.save("vivian_context", output)
            self._fire_hooks("llm_response", prompt, output)
            self._audit("llm_claude", {"prompt": prompt, "output": output})
            return output
        except Exception as e:
            self._audit("llm_claude_error", {"error": str(e)})
            return f"[Anthropic Error] {e}"

    def override_model(self, new_model):
        self.model = new_model
        self._audit("override_model", {"model": new_model})
        return f"[LLMRouter] Switched to {new_model}"

    def add_tool_output(self, text):
        self.memory.save("tool_output", text)
        self._audit("add_tool_output", {"text": text})

    def route_tool_command(self, cmd, user=None):
        """Smartly route tool command using LLM_Tools."""
        try:
            result = self.tools.handle(cmd)
            self.add_tool_output(f"User: {user or self.user}, Command: {cmd}, Result: {result}")
            self._audit("route_tool_command", {"cmd": cmd, "result": result})
            return result
        except Exception as e:
            self._audit("route_tool_command_error", {"cmd": cmd, "error": str(e)})
            return f"[Tool Error] {e}"

    def register_hook(self, fn):
        """Register a callback for LLM events (e.g. response)."""
        self.hooks.append(fn)

    def _fire_hooks(self, typ, old, new):
        for fn in self.hooks:
            try:
                fn(typ, old, new)
            except Exception:
                pass

    def _audit(self, event, details):
        entry = {
            "timestamp": time.time(),
            "event": event,
            "details": details
        }
        with self.lock:
            self.audit_log.append(entry)

    def audit_export(self, path="llmrouter_audit.json"):
        with self.lock:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.audit_log, f, indent=2)

    def explain(self):
        """Explain LLMRouter state and last prompt."""
        persona = self.persona_engine.get_persona_profile()
        last_mem = self.memory.recent("vivian_context", 1)
        return {
            "model": self.model,
            "persona": persona,
            "last_prompt": last_mem[0]['content'] if last_mem else "",
            "tools": getattr(self.tools, "list_tools", lambda: [])(),
        }

    def shell(self):
        print("Vivian LLMRouter Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: send, model, persona, tool, explain, audit, shell, exit")
                elif cmd.startswith("send "):
                    user_input = cmd[5:]
                    print(self.send(user_input))
                elif cmd.startswith("model "):
                    print(self.override_model(cmd[6:]))
                elif cmd.startswith("persona "):
                    print(self.persona_engine.set_persona(cmd[8:]))
                elif cmd.startswith("tool "):
                    print(self.route_tool_command(cmd[5:]))
                elif cmd == "explain":
                    print(self.explain())
                elif cmd == "audit":
                    self.audit_export()
                    print("Audit exported.")
                elif cmd == "shell":
                    print("Already in shell.")
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        self.shell_thread = threading.Thread(target=self.shell, daemon=True)
        self.shell_thread.start()

    def run_api_server(self, port=8778):
        import http.server
        import socketserver
        router = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    if action == "send":
                        res = router.send(data.get("input", ""), user=data.get("user"))
                        self._respond({"result": res})
                    elif action == "model":
                        self._respond({"result": router.override_model(data.get("model"))})
                    elif action == "persona":
                        self._respond({"result": router.persona_engine.set_persona(data.get("persona"))})
                    elif action == "tool":
                        self._respond({"result": router.route_tool_command(data.get("cmd"))})
                    elif action == "audit":
                        router.audit_export(data.get("path", "llmrouter_audit.json"))
                        self._respond({"result": "ok"})
                    elif action == "explain":
                        self._respond(router.explain())
                    else:
                        self._respond({"error": "Invalid action"})
                except Exception as e:
                    self._respond({"error": str(e)})
            def _respond(self, obj):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(obj).encode())
        def serve():
            with socketserver.TCPServer(("", port), Handler) as httpd:
                print(f"LLMRouter API running on port {port}")
                httpd.serve_forever()
        self.api_thread = threading.Thread(target=serve, daemon=True)
        self.api_thread.start()

    def demo(self):
        print("=== Vivian LLMRouter Demo ===")
        print(self.send("What's the weather today?"))
        print(self.override_model("anthropic:claude-3"))
        print(self.send("Summarize recent memory"))
        self.audit_export()
        print("Demo complete. Try .run_shell() or .run_api_server().")

if __name__ == "__main__":
    # Minimal working config for testing
    class DummyTools:
        def handle(self, cmd): return f"Handled {cmd}"
        def list_tools(self): return ["weather", "search", "calc"]
    config = {
        "llm.default": "openai:gpt-4",
        "llm.openai_key": "sk-..."
    }
    router = LLMRouter(config)
    router.tools = DummyTools()
    router.demo()