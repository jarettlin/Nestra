"""A small Mamdani fuzzy inference engine that explains itself.

Why not scikit-fuzzy? This engine is ~150 lines, depends only on numpy, and
every inference returns which rules fired and how strongly. That trace is
what the dashboard's "why" panel shows.

Pipeline: fuzzify crisp inputs -> evaluate rules (AND = min, OR = max,
hedges like "very") -> clip each rule's output set at its strength ->
aggregate with max -> defuzzify by centroid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import reduce
from typing import Any, Callable

import numpy as np

MembershipFn = Callable[[Any], np.ndarray]


# --------------------------------------------------------------------------
# Membership functions
# --------------------------------------------------------------------------
def trapmf(a: float, b: float, c: float, d: float) -> MembershipFn:
    """Trapezoid: 0 below a, rises to 1 at b, flat to c, falls to 0 at d.

    Use a == b for a left shoulder and c == d for a right shoulder.
    """
    if not a <= b <= c <= d:
        raise ValueError(f"trapmf needs a <= b <= c <= d, got {(a, b, c, d)}")

    def mf(x: Any) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        y = np.zeros_like(x)
        if b > a:
            y = np.where((x > a) & (x < b), (x - a) / (b - a), y)
        y = np.where((x >= b) & (x <= c), 1.0, y)
        if d > c:
            y = np.where((x > c) & (x < d), (d - x) / (d - c), y)
        return y

    return mf


def trimf(a: float, b: float, c: float) -> MembershipFn:
    """Triangle peaking at b."""
    return trapmf(a, b, b, c)


def union(*mfs: MembershipFn) -> MembershipFn:
    """Membership that is the max of several (e.g. 'night' wraps past midnight)."""
    return lambda x: reduce(np.fmax, (mf(x) for mf in mfs))


HEDGES: dict[str, Callable[[float], float]] = {
    "very": lambda mu: mu**2,
    "extremely": lambda mu: mu**3,
    "somewhat": lambda mu: mu**0.5,
}


# --------------------------------------------------------------------------
# Linguistic variables
# --------------------------------------------------------------------------
class FuzzyVariable:
    def __init__(
        self, name: str, lo: float, hi: float, terms: dict[str, MembershipFn], resolution: int = 1001
    ) -> None:
        if lo >= hi:
            raise ValueError("lo must be < hi")
        self.name = name
        self.lo = lo
        self.hi = hi
        self.terms = dict(terms)
        self.universe = np.linspace(lo, hi, resolution)

    def clamp(self, x: float) -> float:
        return float(min(max(x, self.lo), self.hi))

    def membership(self, term: str, x: float) -> float:
        return float(self.terms[term](self.clamp(x)))

    def fuzzify(self, x: float) -> dict[str, float]:
        return {term: self.membership(term, x) for term in self.terms}

    def curve(self, term: str) -> np.ndarray:
        return self.terms[term](self.universe)

    def term_value(self, term: str) -> float:
        """Crisp value that best represents a term (its centroid). 'set fan to low' uses this."""
        curve = self.curve(term)
        return float((self.universe * curve).sum() / curve.sum())

    def best_term(self, x: float) -> str:
        memberships = self.fuzzify(x)
        return max(memberships, key=memberships.__getitem__)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Clause:
    variable: str
    term: str
    hedge: str | None = None
    negated: bool = False

    def degree(self, memberships: dict[str, dict[str, float]]) -> float:
        mu = memberships[self.variable][self.term]
        if self.hedge:
            mu = HEDGES[self.hedge](mu)
        return 1.0 - mu if self.negated else mu

    def __str__(self) -> str:
        words = [self.variable, "is"]
        if self.negated:
            words.append("not")
        if self.hedge:
            words.append(self.hedge)
        words.append(self.term)
        return " ".join(words)


@dataclass(frozen=True)
class Rule:
    clauses: tuple[Clause, ...]
    consequent: str
    connective: str = "and"
    weight: float = 1.0

    def strength(self, memberships: dict[str, dict[str, float]]) -> float:
        degrees = [c.degree(memberships) for c in self.clauses]
        combined = min(degrees) if self.connective == "and" else max(degrees)
        return combined * self.weight

    def describe(self, output: str) -> str:
        condition = f" {self.connective.upper()} ".join(str(c) for c in self.clauses)
        text = f"IF {condition} THEN {output} is {self.consequent}"
        return text if self.weight == 1.0 else f"{text} (weight {self.weight:g})"


_CLAUSE_RE = re.compile(
    r"^(?P<var>\w+)\s+is\s+(?P<neg>not\s+)?(?:(?P<hedge>very|extremely|somewhat)\s+)?(?P<term>\w+)$"
)


def rule(condition: str, then: str, weight: float = 1.0) -> Rule:
    """Build a rule from readable text, e.g. rule("temperature is very hot and humidity is humid", "max")."""
    text = " ".join(condition.lower().split())
    has_and, has_or = " and " in text, " or " in text
    if has_and and has_or:
        raise ValueError(f"Mixing AND/OR in one rule is not supported, split it: {condition!r}")
    connective = "or" if has_or else "and"
    clauses = []
    for part in text.split(f" {connective} "):
        m = _CLAUSE_RE.match(part)
        if not m:
            raise ValueError(f"Cannot parse clause {part!r} in rule {condition!r}")
        clauses.append(Clause(m["var"], m["term"], m["hedge"], bool(m["neg"])))
    return Rule(tuple(clauses), then, connective, weight)


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------
class NoRuleFired(RuntimeError):
    pass


@dataclass
class RuleActivation:
    rule: str
    strength: float


@dataclass
class InferenceResult:
    system: str
    output: str
    value: float
    term: str
    inputs: dict[str, float]
    memberships: dict[str, dict[str, float]]
    activations: list[RuleActivation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "output": self.output,
            "value": round(self.value, 2),
            "term": self.term,
            "inputs": {k: round(v, 2) for k, v in self.inputs.items()},
            "memberships": {
                var: {t: round(mu, 3) for t, mu in terms.items() if mu > 0}
                for var, terms in self.memberships.items()
            },
            "rules": [{"rule": a.rule, "strength": round(a.strength, 3)} for a in self.activations],
        }

    def summary(self, top: int = 3) -> str:
        lines = [f"{self.output} = {self.value:.1f} ({self.term})"]
        lines += [f"  {a.strength:.2f}  {a.rule}" for a in self.activations[:top]]
        return "\n".join(lines)


class MamdaniSystem:
    def __init__(
        self, name: str, inputs: list[FuzzyVariable], output: FuzzyVariable, rules: list[Rule]
    ) -> None:
        self.name = name
        self.inputs = {v.name: v for v in inputs}
        self.output = output
        self.rules = rules
        for r in rules:
            if r.consequent not in output.terms:
                raise ValueError(f"[{name}] unknown output term {r.consequent!r}")
            for c in r.clauses:
                if c.variable not in self.inputs:
                    raise ValueError(f"[{name}] unknown input variable {c.variable!r}")
                if c.term not in self.inputs[c.variable].terms:
                    raise ValueError(f"[{name}] unknown term {c.term!r} for {c.variable!r}")
        self._output_curves = {t: output.curve(t) for t in output.terms}

    def infer(self, **values: float) -> InferenceResult:
        missing = self.inputs.keys() - values.keys()
        if missing:
            raise ValueError(f"[{self.name}] missing inputs: {sorted(missing)}")
        crisp = {name: var.clamp(values[name]) for name, var in self.inputs.items()}
        memberships = {name: var.fuzzify(crisp[name]) for name, var in self.inputs.items()}

        aggregated = np.zeros_like(self.output.universe)
        activations: list[RuleActivation] = []
        for r in self.rules:
            strength = r.strength(memberships)
            if strength <= 0:
                continue
            aggregated = np.fmax(aggregated, np.fmin(strength, self._output_curves[r.consequent]))
            activations.append(RuleActivation(r.describe(self.output.name), strength))

        area = aggregated.sum()
        if area == 0:
            raise NoRuleFired(f"[{self.name}] no rule fired for inputs {crisp}")
        value = float((self.output.universe * aggregated).sum() / area)
        activations.sort(key=lambda a: a.strength, reverse=True)
        return InferenceResult(
            system=self.name,
            output=self.output.name,
            value=value,
            term=self.output.best_term(value),
            inputs=crisp,
            memberships=memberships,
            activations=activations,
        )
