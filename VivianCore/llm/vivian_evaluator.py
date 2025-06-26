import math
import random
import time
import threading
import json
from typing import List, Dict, Optional, Callable, Any

class VivianEvaluator:
    """
    AGI-Grade VivianEvaluator (maximal, single file):
    - Multi-factor scoring (risk, novelty, memory, emotion, reward, plugins, context, randomness)
    - Batch compare, explainability, simulation, undo, audit, analytics, plugin registry, live REPL shell, and HTTP API.
    - Ready for deep AGI/agent/LLM integration or standalone use.
    """

    def __init__(
        self,
        personality: Optional[str] = "balanced",
        plugin_hooks: Optional[Dict[str, Callable]] = None,
        audit: bool = True,
        enable_api: bool = False,
        api_port: int = 8765
    ):
        self.personality = personality
        self.bias = self._load_bias_profile(personality)
        self.plugin_hooks = plugin_hooks or {}
        self.audit_log: List[Dict] = []
        self.eval_history: List[Dict] = []
        self.simulation_data: List[Dict] = []
        self.audit = audit
        self.api_enabled = enable_api
        self.api_port = api_port
        if enable_api:
            self.run_api_server()

    def _load_bias_profile(self, personality: str) -> Dict:
        profiles = {
            "balanced": {"risk": 0.5, "novelty": 0.5, "memory_weight": 1.0, "emotion": 0.5, "reward": 1.0},
            "cautious": {"risk": 0.3, "novelty": 0.2, "memory_weight": 1.2, "emotion": 0.3, "reward": 0.8},
            "bold": {"risk": 0.8, "novelty": 0.9, "memory_weight": 0.8, "emotion": 0.7, "reward": 1.2},
            "creative": {"risk": 0.7, "novelty": 1.2, "memory_weight": 0.7, "emotion": 0.6, "reward": 1.1},
        }
        return profiles.get(personality, profiles["balanced"])

    def score_thought(
        self,
        content: str,
        tags: Optional[List[str]] = None,
        importance: float = 1.0,
        context: Optional[Dict] = None,
        reward: float = 0.0,
        emotion: Optional[str] = None,
        plugin_scores: Optional[List[float]] = None,
        explanation: Optional[List[str]] = None,
    ) -> float:
        tags = tags or []
        context = context or {}
        base = importance * self.bias["memory_weight"]
        mods = []
        score = base

        if "risk" in tags:
            score *= self.bias["risk"]
            mods.append(f"×{self.bias['risk']} (risk)")
        if "novel" in tags:
            score *= (1.0 + self.bias["novelty"])
            mods.append(f"×{1 + self.bias['novelty']} (novel)")
        if "familiar" in tags:
            score *= 0.9
            mods.append("×0.9 (familiar)")
        if reward:
            score *= (1.0 + reward * self.bias.get("reward", 1.0) * 0.1)
            mods.append(f"×{1.0 + reward * self.bias.get('reward', 1.0) * 0.1:.2f} (reward)")
        if emotion:
            emo_weight = self.bias.get("emotion", 0.5)
            if emotion == "positive":
                score *= (1.0 + emo_weight * 0.1)
                mods.append(f"×{1.0 + emo_weight*0.1:.2f} (positive emotion)")
            elif emotion == "negative":
                score *= (1.0 - emo_weight * 0.1)
                mods.append(f"×{1.0 - emo_weight*0.1:.2f} (negative emotion)")
        if "user" in context:
            score += 0.1
            mods.append("+0.1 (user context)")
        if plugin_scores:
            plugin_contrib = sum(plugin_scores) / len(plugin_scores)
            score += plugin_contrib
            mods.append(f"+{plugin_contrib:.2f} (plugin)")
        score += random.uniform(0, 0.2)
        if explanation is not None:
            explanation.append(f"Base: {base:.2f} | Modifiers: {' '.join(mods) if mods else 'none'} | Final: {score:.3f}")
        if self.audit:
            self.audit_log.append({
                "timestamp": time.time(),
                "content": content,
                "tags": tags,
                "importance": importance,
                "context": context,
                "reward": reward,
                "emotion": emotion,
                "score": score,
                "mods": mods
            })
        return round(score, 3)

    def compare_options(self, thoughts: List[Dict]) -> Dict:
        """
        Given a list of thought dicts, return the best one (with full scoring/audit/explainability).
        """
        best = None
        best_score = -math.inf
        explanations = []
        for t in thoughts:
            plugin_scores = []
            if "on_score" in self.plugin_hooks:
                try:
                    plugin_scores = [self.plugin_hooks["on_score"](t)]
                except Exception:
                    pass
            expl = []
            s = self.score_thought(
                content=t.get("content", ""),
                tags=t.get("tags", []),
                importance=t.get("importance", 1.0),
                context=t.get("context", {}),
                reward=t.get("reward", 0.0),
                emotion=t.get("emotion"),
                plugin_scores=plugin_scores,
                explanation=expl
            )
            t["score"] = s
            t["explanation"] = expl
            explanations.append({"thought": t, "explanation": expl})
            if s > best_score:
                best = t
                best_score = s
        self.eval_history.append({"batch": thoughts, "best": best, "explanations": explanations})
        return best if best else {}

    def explain_score(self, thought: Dict) -> str:
        expl = []
        self.score_thought(
            content=thought.get("content", ""),
            tags=thought.get("tags", []),
            importance=thought.get("importance", 1.0),
            context=thought.get("context", {}),
            reward=thought.get("reward", 0.0),
            emotion=thought.get("emotion"),
            plugin_scores=None,
            explanation=expl
        )
        return expl[0] if expl else "No explanation."

    def audit_export(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.audit_log, f, indent=2)

    def analytics(self) -> Dict:
        scores = [e["score"] for e in self.audit_log]
        return {
            "total_evaluated": len(scores),
            "avg_score": sum(scores) / max(1, len(scores)),
            "max_score": max(scores) if scores else None,
            "min_score": min(scores) if scores else None,
        }

    def simulate_batch(self, thoughts: List[Dict], steps: int = 3) -> List[Dict]:
        """
        Simulate scoring the same batch with different random seeds/personalities.
        """
        results = []
        personalities = ["balanced", "cautious", "bold", "creative"]
        for i in range(steps):
            self.personality = personalities[i % len(personalities)]
            self.bias = self._load_bias_profile(self.personality)
            res = self.compare_options(thoughts)
            results.append({"personality": self.personality, "best": res})
        self.simulation_data.extend(results)
        return results

    def undo_last(self):
        if self.audit_log:
            return self.audit_log.pop()
        return None

    def plugin_register(self, name: str, fn: Callable):
        self.plugin_hooks[name] = fn

    def plugin_call(self, name: str, *args, **kwargs):
        if name in self.plugin_hooks:
            return self.plugin_hooks[name](*args, **kwargs)
        else:
            raise ValueError(f"Plugin '{name}' not found")

    def explain_batch(self, thoughts: List[Dict]) -> List[str]:
        return [self.explain_score(t) for t in thoughts]

    def batch_score(self, thoughts: List[Dict]) -> List[Dict]:
        for t in thoughts:
            t["score"] = self.score_thought(
                content=t.get("content", ""),
                tags=t.get("tags", []),
                importance=t.get("importance", 1.0),
                context=t.get("context", {}),
                reward=t.get("reward", 0.0),
                emotion=t.get("emotion")
            )
        return thoughts

    def interactive_shell(self):
        print("VivianEvaluator Interactive Shell. Type 'help' for commands.")
        while True:
            try:
                cmd = input("> ").strip()
                if cmd in ("exit", "quit"):
                    print("Exiting shell.")
                    break
                elif cmd == "help":
                    print("Commands: eval, compare, batch, explain, explain_batch, analytics, undo, simulate, audit, plugins, call, exit")
                elif cmd.startswith("eval "):
                    content = cmd[5:]
                    score = self.score_thought(content)
                    print(f"Score: {score}")
                elif cmd.startswith("compare "):
                    data = eval(cmd[8:])
                    print(self.compare_options(data))
                elif cmd.startswith("batch "):
                    data = eval(cmd[6:])
                    print(self.batch_score(data))
                elif cmd.startswith("explain "):
                    data = eval(cmd[8:])
                    print(self.explain_score(data))
                elif cmd.startswith("explain_batch "):
                    data = eval(cmd[14:])
                    print(self.explain_batch(data))
                elif cmd == "analytics":
                    print(self.analytics())
                elif cmd == "undo":
                    print(self.undo_last())
                elif cmd.startswith("simulate "):
                    data = eval(cmd[9:])
                    print(self.simulate_batch(data))
                elif cmd == "audit":
                    self.audit_export("vivian_evaluator_audit.json")
                    print("Audit exported to vivian_evaluator_audit.json")
                elif cmd == "plugins":
                    print(f"Plugins: {list(self.plugin_hooks.keys())}")
                elif cmd.startswith("call "):
                    _, name, *args = cmd.split(" ")
                    print(self.plugin_call(name, *args))
                else:
                    print("Unknown command. Type 'help' for commands.")
            except Exception as e:
                print(f"Error: {e}")

    def run_shell(self):
        threading.Thread(target=self.interactive_shell, daemon=True).start()

    def run_api_server(self):
        import http.server
        import socketserver

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                self.outer = self
                super().__init__(*args, **kwargs)
            def do_POST(this):
                length = int(this.headers.get('Content-Length', 0))
                body = this.rfile.read(length)
                try:
                    data = json.loads(body)
                    action = data.get("action")
                    if action == "score":
                        score = self.score_thought(**data.get("thought", {}))
                        this._respond({"score": score})
                    elif action == "compare":
                        best = self.compare_options(data.get("thoughts", []))
                        this._respond(best)
                    elif action == "analytics":
                        this._respond(self.analytics())
                    else:
                        this._respond({"error": "Invalid action"})
                except Exception as e:
                    this._respond({"error": str(e)})
            def _respond(this, obj):
                this.send_response(200)
                this.send_header("Content-Type", "application/json")
                this.end_headers()
                this.wfile.write(json.dumps(obj).encode())
        def serve():
            with socketserver.TCPServer(("", self.api_port), Handler) as httpd:
                print(f"VivianEvaluator API running on port {self.api_port}")
                httpd.serve_forever()
        threading.Thread(target=serve, daemon=True).start()

    def demo(self):
        print("=== VivianEvaluator AGI Demo ===")
        thoughts = [
            {"content": "Try a new solution", "tags": ["novel"], "importance": 1.2, "reward": 0.5, "emotion": "positive"},
            {"content": "Stick to what works", "tags": ["familiar"], "importance": 1.0, "reward": 0.1, "emotion": "neutral"},
            {"content": "Take a risky shortcut", "tags": ["risk", "novel"], "importance": 1.1, "reward": -0.2, "emotion": "negative"},
            {"content": "Ask user for help", "tags": ["user"], "importance": 0.9, "reward": 0.3, "emotion": "positive", "context": {"user": "gregmish"}}
        ]
        best = self.compare_options(thoughts)
        print("Best thought:", best)
        print("Explanation:", self.explain_score(best))
        print("Analytics:", self.analytics())
        print("Simulate batch:", self.simulate_batch(thoughts))
        self.audit_export("vivian_evaluator_audit.json")
        print("Demo complete. You can also start the interactive shell with .run_shell() or the HTTP API.")

if __name__ == "__main__":
    ve = VivianEvaluator(enable_api=False)
    ve.demo()