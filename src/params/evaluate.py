"""
Evaluate Basel-derived parameters against a bank's reported quarter.

A parameter is only "analysable" if it runs. This module executes the `formula`
field of an extracted parameter over a symbol table built from one bank-quarter
of FDIC data and reports whether the constraint holds, by how much, and — when
it cannot be evaluated — exactly which symbol was missing and where that number
would have to come from.

Formulas are parsed with `ast` and walked over a whitelist of arithmetic nodes.
`eval` is never called on model-authored text.
"""
from __future__ import annotations

import ast
import math
import operator as op
from dataclasses import dataclass, field
from typing import Any

from symbols import AVAILABLE, CALLREPORT, DERIVED, SYMBOLS, UNAVAILABLE  # noqa: F401

_BIN = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
        ast.Div: op.truediv, ast.Pow: op.pow, ast.Mod: op.mod}
_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg}
_CMP = {ast.Gt: op.gt, ast.GtE: op.ge, ast.Lt: op.lt, ast.LtE: op.le, ast.Eq: op.eq}
_FUNCS = {"min": min, "max": max, "abs": abs, "sqrt": math.sqrt}

OPERATORS = {">=": op.ge, "<=": op.le, ">": op.gt, "<": op.lt, "==": op.eq}


class MissingSymbol(Exception):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


def _eval(node: ast.AST, env: dict[str, float]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"non-numeric constant {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id not in env or env[node.id] is None:
            raise MissingSymbol(node.id)
        return env[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, env), _eval(node.right, env))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, env))
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
        return _CMP[type(node.ops[0])](_eval(node.left, env), _eval(node.comparators[0], env))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_eval(a, env) for a in node.args])
    raise ValueError(f"disallowed expression node {type(node).__name__}")


def evaluate_expression(expr: str, env: dict[str, float]) -> float:
    return _eval(ast.parse(expr.strip(), mode="eval"), env)


def _clean(v) -> float | None:
    if v is None or v == "" or v == "CONF":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def build_env(row: dict[str, Any],
              call_report: dict[str, Any] | None = None) -> dict[str, float | None]:
    """Symbol table for one bank-quarter.

    `row` is an FDIC record. `call_report` is optional: a mapping of MDRM code to
    filed value, as produced by `ingest.callreport`. Supplying it resolves the
    symbols the FDIC series omits — chiefly undrawn credit-card lines, without
    which no off-balance-sheet constraint can be evaluated at all.
    """
    env: dict[str, float | None] = {}
    for s in SYMBOLS.values():
        if s.availability == AVAILABLE:
            env[s.name] = _clean(row.get(s.fdic_field))
        elif s.availability == CALLREPORT:
            env[s.name] = next(
                (v for v in (_clean((call_report or {}).get(c)) for c in s.mdrm)
                 if v is not None), None)
        elif s.availability == UNAVAILABLE:
            env[s.name] = None

    # derived symbols may depend on each other; a couple of passes settles it
    for _ in range(3):
        for s in SYMBOLS.values():
            if s.availability != DERIVED or env.get(s.name) is not None:
                continue
            try:
                env[s.name] = float(evaluate_expression(s.formula, env))
            except (MissingSymbol, ZeroDivisionError, ValueError, TypeError):
                env.setdefault(s.name, None)
    return env


@dataclass
class Result:
    param_id: str
    status: str                      # satisfied | breached | computed | not_computable
    value: float | None = None
    threshold: float | None = None
    operator: str | None = None
    headroom: float | None = None    # value - threshold, signed by the operator
    missing: list[str] = field(default_factory=list)
    missing_sources: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], {})}


def evaluate_param(param: dict, env: dict[str, float | None]) -> Result:
    pid = param.get("param_id", "?")
    formula = (param.get("formula") or "").strip()
    if not formula:
        return Result(pid, "not_computable", error="no formula")

    # "lhs = rhs" -> evaluate rhs; a bare expression is evaluated as-is
    expr = formula.split("=", 1)[1] if ("=" in formula and "==" not in formula) else formula

    try:
        value = float(evaluate_expression(expr, env))
    except MissingSymbol as m:
        sym = SYMBOLS.get(m.name)
        return Result(pid, "not_computable", missing=[m.name],
                      missing_sources={m.name: (sym.call_report or "unknown source") if sym
                                       else "symbol not in vocabulary"})
    except ZeroDivisionError:
        return Result(pid, "not_computable", error="division by zero (denominator absent)")
    except Exception as exc:
        return Result(pid, "not_computable", error=f"{type(exc).__name__}: {exc}")

    opstr, thr = param.get("operator"), param.get("value")
    if opstr in OPERATORS and isinstance(thr, (int, float)):
        ok = OPERATORS[opstr](value, float(thr))
        sign = 1.0 if opstr in (">=", ">") else -1.0
        return Result(pid, "satisfied" if ok else "breached", value=value,
                      threshold=float(thr), operator=opstr,
                      headroom=sign * (value - float(thr)))
    return Result(pid, "computed", value=value)


def evaluate_all(params: list[dict], row: dict[str, Any]) -> tuple[list[Result], dict]:
    env = build_env(row)
    results = [evaluate_param(p, env) for p in params]
    summary = {
        "n_params": len(results),
        "satisfied": sum(r.status == "satisfied" for r in results),
        "breached": sum(r.status == "breached" for r in results),
        "computed": sum(r.status == "computed" for r in results),
        "not_computable": sum(r.status == "not_computable" for r in results),
    }
    return results, summary
