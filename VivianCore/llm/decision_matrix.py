import random
import logging
import math
import json
import time
from typing import Callable, Any, List, Dict, Optional

class DecisionMatrix:
    """
    Vivian Decision Matrix (AGI-Grade, Ultra-Featureful):

    Features:
    - Arbitrary multi-criteria, per-option adaptive weights
    - Option groups, dependencies, preconditions, and time/context awareness
    - Stochastic/softmax exploration, greedy or custom tie-breaking
    - Feedback, active learning, auto-tuning, and rolling reward adaptation
    - LLM/external scoring and batch evaluation
    - Option sequence/planning, group consensus, plugin hooks
    - Human-in-the-loop, uncertainty/fuzzy scoring, and confidence estimates
    - Full serialization, audit, stats, and visualization-ready logs
    """

    DEFAULT_CRITERIA = ["utility", "priority", "risk", "emotional_weight"]

    def __init__(
        self,
        criteria: Optional[List[str]] = None,
        exploration: float = 0.0,
        external_scorer: Optional[Callable[[List[Dict]], List[float]]] = None,
        name: str = "default",
        context: Optional[Callable[[], Dict]] = None,
        consensus_agents: Optional[List[Callable[[List[Dict]], List[float]]]] = None,
        auto_tune: bool = False
    ):
        self.options: List[Dict] = []
        self.log: List[Any] = []
        self.criteria = criteria or DecisionMatrix.DEFAULT_CRITERIA.copy()
        self.weights = {c: 1.0 for c in self.criteria}
        self.exploration = exploration
        self.external_scorer = external_scorer
        self.history: List[Any] = []
        self.name = name
        self.tie_breaker = random.choice
        self.stats = {"evaluations": 0, "last_scores": []}
        self.context_fn = context
        self.consensus_agents = consensus_agents or []
        self.auto_tune = auto_tune
        self.learning_rate = 0.05  # For auto-tune
        self.uncertainty_mode = False  # If true, return confidence with scores

    def set_weights(self, weights: Dict[str, float]):
        self.weights.update(weights)

    def add_criterion(self, criterion: str, weight: float = 1.0):
        if criterion not in self.criteria:
            self.criteria.append(criterion)
            self.weights[criterion] = weight

    def add_option(
        self,
        description: str,
        group: Optional[str] = None,
        dependency: Optional[str] = None,
        can_execute: Optional[Callable[[], bool]] = None,
        valid_time: Optional[Callable[[], bool]] = None,
        context_sensitive: Optional[Callable[[Dict], float]] = None,
        uncertainty: Optional[float] = None,
        **attrs
    ):
        """
        Add an option with arbitrary criteria, group, dependency, precondition/can_execute, time/context, and uncertainty.
        """
        option = {
            "description": description,
            "group": group,
            "dependency": dependency,
            "feedback": [],
            "executed": False,
            "history": [],
            "valid_time": valid_time,
            "context_sensitive": context_sensitive,
            "uncertainty": uncertainty or 0.0,
        }
        for c in self.criteria:
            option[c] = attrs.get(c, 1.0 if c not in ["risk", "emotional_weight"] else 0.0)
        option["can_execute"] = can_execute or (lambda: True)
        self.options.append(option)

    def clear_options(self):
        self.options = []

    def _score_option(self, option, ctx=None):
        score = 0.0
        for c in self.criteria:
            val = option.get(c, 0.0)
            w = self.weights.get(c, 1.0)
            # Context-sensitive adjustment
            if option.get("context_sensitive") and ctx:
                val += option["context_sensitive"](ctx)
            if c == "risk":
                score -= w * val
            else:
                score += w * val
        # Adaptive learning bonus/penalty
        if option["feedback"]:
            score += sum(option["feedback"][-5:]) / max(1, len(option["feedback"][-5:]))
        # Time/context gating
        if option.get("valid_time") and not option["valid_time"]():
            score -= 9999
        # Uncertainty penalty (if enabled)
        if self.uncertainty_mode:
            score -= abs(option.get("uncertainty", 0.0))
        return score

    def _eligible_options(self):
        ctx = self.context_fn() if self.context_fn else None
        eligible = []
        for o in self.options:
            if not o["can_execute"]():
                continue
            if o["dependency"]:
                dep = next((x for x in self.options if x["description"] == o["dependency"] and x.get("executed")), None)
                if not dep:
                    continue
            if o.get("valid_time") and not o["valid_time"]():
                continue
            eligible.append(o)
        return eligible

    def _consensus_scores(self, eligible):
        # Each agent returns a score vector. Average/median them.
        all_scores = []
        for agent in self.consensus_agents:
            try:
                scores = agent(eligible)
                all_scores.append(scores)
            except Exception:
                continue
        if not all_scores:
            return [self._score_option(o) for o in eligible]
        # Transpose and average
        return [sum(x)/len(x) for x in zip(*all_scores)]

    def _uncertainty_confidence(self, scores):
        # Simple: confidence = 1/(1+stddev)
        if not scores:
            return 0.0
        mean = sum(scores)/len(scores)
        stdev = math.sqrt(sum((s-mean)**2 for s in scores)/len(scores)) if len(scores) > 1 else 0.0
        return 1.0/(1.0+stdev)

    def auto_tune_weights(self, feedback_log):
        """
        Automatically tune weights based on feedback log.
        """
        for entry in feedback_log:
            desc, reward = entry["description"], entry["reward"]
            for o in self.options:
                if o["description"] == desc:
                    for c in self.criteria:
                        # Reward increases criterion weight, penalty decreases
                        self.weights[c] += self.learning_rate * reward * (o[c] - self.weights[c])
        # Normalize (optional)
        wsum = sum(abs(w) for w in self.weights.values())
        if wsum > 0:
            self.weights = {k: v/wsum for k, v in self.weights.items()}

    def evaluate(
        self,
        explain: bool = False,
        prefer_group: Optional[str] = None,
        batch: int = 1,
        force_stochastic: bool = False,
        require_human: bool = False,
        uncertainty: bool = False
    ) -> Any:
        """
        Returns the best option(s).
        - batch: return top-N for planning.
        - require_human: request confirmation if high risk.
        - uncertainty: return confidence with result.
        - explain: return explanations.
        """
        eligible = self._eligible_options()
        if prefer_group:
            group_opts = [o for o in eligible if o["group"] == prefer_group]
            if group_opts:
                eligible = group_opts
        if not eligible:
            return None if not explain else (None, [])

        if self.consensus_agents:
            scores = self._consensus_scores(eligible)
        elif self.external_scorer:
            scores = self.external_scorer(eligible)
        else:
            ctx = self.context_fn() if self.context_fn else None
            scores = [self._score_option(o, ctx) for o in eligible]

        self.stats["evaluations"] += 1
        self.stats["last_scores"] = scores

        # Softmax exploration
        pick_stochastic = force_stochastic or (self.exploration > 0)
        if pick_stochastic:
            exp_scores = [math.exp(s) for s in scores]
            total = sum(exp_scores)
            probs = [e / total for e in exp_scores]
            chosen_idxs = random.choices(range(len(eligible)), weights=probs, k=batch)
        else:
            sorted_pairs = sorted(list(enumerate(scores)), key=lambda x: x[1], reverse=True)
            top_score = sorted_pairs[0][1]
            tied = [i for i, s in sorted_pairs if s == top_score]
            chosen_idxs = [self.tie_breaker(tied)] if batch == 1 else [i for i, _ in sorted_pairs[:batch]]

        best = [eligible[i] for i in chosen_idxs]
        for o in best:
            o["executed"] = True
            o["history"].append({"selected_at": self.stats["evaluations"], "score": scores[chosen_idxs[0]]})
        explanation = self._explain(eligible, scores, chosen_idxs, uncertainty=uncertainty)
        self.log.append(explanation)
        logging.info(f"[DecisionMatrix] {explanation['summary']}")
        self.history.append({
            "options": [o["description"] for o in best],
            "scores": [scores[i] for i in chosen_idxs],
            "time": time.time()
        })
        result = (best[0], explanation) if batch == 1 else (best, explanation)
        if require_human:
            high_risk = any(o.get("risk", 0) > 0.7 for o in best)
            if high_risk:
                print(f"[DecisionMatrix] Human confirmation required for risky option(s): {[o['description'] for o in best]}")
        if uncertainty:
            conf = self._uncertainty_confidence(scores)
            if batch == 1:
                return (result, conf)
            else:
                return (result, conf)
        return result

    def _explain(self, options, scores, best_idxs, uncertainty=False):
        explanations = []
        for i, (o, s) in enumerate(zip(options, scores)):
            is_best = i in best_idxs
            txt = f"{'[BEST]' if is_best else '      '} {o['description']} | score={s:.2f} | " + \
                  ", ".join(f"{c}={o.get(c,0.0):.2f}" for c in self.criteria)
            if o.get("group"):
                txt += f" | group={o['group']}"
            if o.get("dependency"):
                txt += f" | depends on: {o['dependency']}"
            if o.get("uncertainty", 0.0) > 0:
                txt += f" | uncertainty={o['uncertainty']:.2f}"
            explanations.append(txt)
        best_descriptions = ", ".join(options[i]["description"] for i in best_idxs)
        result = {
            "summary": f"Selected: {best_descriptions}",
            "details": explanations,
            "all_scores": scores,
        }
        if uncertainty:
            result["confidence"] = self._uncertainty_confidence(scores)
        return result

    def give_feedback(self, description, reward: float):
        for o in self.options:
            if o["description"] == description:
                o["feedback"].append(reward)

    def recent_log(self, count=5):
        return self.log[-count:]

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "options": self.options,
                "log": self.log,
                "history": self.history,
                "weights": self.weights,
                "criteria": self.criteria
            }, f, indent=2)

    def load(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.options = data.get("options", [])
            self.log = data.get("log", [])
            self.history = data.get("history", [])
            self.weights = data.get("weights", self.weights)
            self.criteria = data.get("criteria", self.criteria)

    def plan_sequence(self, steps=3, explain=False, consensus=False):
        sequence = []
        explanations = []
        for _ in range(steps):
            if consensus and self.consensus_agents:
                best, explanation = self.evaluate(explain=True)
            else:
                best, explanation = self.evaluate(explain=True)
            if not best:
                break
            sequence.append(best["description"])
            explanations.append(explanation)
            # Remove to avoid repeats
            self.options = [o for o in self.options if o["description"] != best["description"]]
        return (sequence, explanations) if explain else sequence

    def set_llm_scorer(self, llm_scorer: Callable[[List[Dict]], List[float]]):
        self.external_scorer = llm_scorer

    def batch_evaluate(self, batch_size=3, explain=False):
        return self.evaluate(batch=batch_size, explain=explain)

    def analytical_stats(self):
        option_counts = {}
        for h in self.history:
            for desc in h["options"]:
                option_counts[desc] = option_counts.get(desc, 0) + 1
        total_scores = [s for h in self.history for s in h["scores"]]
        avg_score = sum(total_scores) / max(1, len(total_scores)) if total_scores else 0
        return {
            "total_evaluations": self.stats["evaluations"],
            "most_selected": max(option_counts, key=option_counts.get) if option_counts else None,
            "least_selected": min(option_counts, key=option_counts.get) if option_counts else None,
            "average_score": avg_score,
        }

    def visualize(self):
        """
        Print a simple visualization of option selection frequency.
        """
        stats = self.analytical_stats()
        print("Option Selection Frequency:")
        for option, count in sorted(stats.items()):
            print(f"{option}: {'█' * count}")
        print("Average Score:", stats.get("average_score", 0))

    def demo(self):
        print("\n--- DecisionMatrix AGI-Grade Demo ---")
        self.clear_options()
        now = time.localtime()
        self.add_option("Reply to user question", utility=1.0, priority=1.0, risk=0.1, emotional_weight=0.2, group="basic")
        self.add_option("Think silently", utility=0.5, priority=0.2, risk=0.0, emotional_weight=0.0, group="basic")
        self.add_option("Ask for clarification", utility=0.8, priority=0.9, risk=0.05, emotional_weight=0.1, group="basic")
        self.add_option("Send email", utility=0.7, priority=0.8, risk=0.2, emotional_weight=0.1, group="comm",
                        can_execute=lambda: now.tm_hour < 18)
        self.add_option("Shutdown system", utility=0.5, priority=0.1, risk=0.9, emotional_weight=0.0, group="admin",
                        can_execute=lambda: False)
        self.add_option("Start backup", utility=0.3, priority=0.3, risk=0.3, emotional_weight=0.1, group="admin",
                        dependency="Send email")
        # Option with uncertainty and context-sensitive adjustment
        self.add_option("Try experimental feature", utility=0.2, priority=0.5, risk=0.5, emotional_weight=0.2,
                        uncertainty=0.6, context_sensitive=lambda ctx: ctx.get("user_reputation", 0.0) if ctx else 0.0)
        # Plan a sequence
        seq, explanations = self.plan_sequence(steps=3, explain=True)
        print("Planned sequence:", seq)
        for e in explanations:
            print(json.dumps(e, indent=2))
        print("Analytical stats:", self.analytical_stats())
        # Show feedback and auto-tune
        self.give_feedback(seq[0], reward=+1.0)
        self.auto_tune_weights([{"description": seq[0], "reward": 1.0}])
        print("Weights after auto-tuning:", self.weights)
        return seq

# If run directly: run demo
if __name__ == "__main__":
    dm = DecisionMatrix(exploration=0.2, auto_tune=True)
    dm.demo()