#!/usr/bin/env python3
"""Dice notation roller for RPG-style dice expressions.

Notation
--------
  NdM           Roll N dice with M sides (N defaults to 1).
  NdM+K / -K    Add or subtract a constant modifier.
  NdMkhK        Keep the K highest dice.
  NdMklK        Keep the K lowest dice.
  NdMdhK        Drop the K highest dice.
  NdMdlK        Drop the K lowest dice.
  NdM!          Exploding dice -- reroll and add on a max roll.
  NdM>T / >=T   Count dice strictly / inclusively above T.
  NdM<T / <=T   Count dice strictly / inclusively below T.

Terms combine with + or -, for example "2d6+1d8-1".

Usage
-----
  python roll.py "4d6kh3+2"
  python roll.py "2d20kh1" --stats --rolls 100000
  python roll.py "3d6" --json
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union


# --- parsing --------------------------------------------------------------- #

# One signed term: either a dice block (NdM + optional modifiers) or a constant.
TOKEN_RE = re.compile(
    r"""
    (?P<sign>[+-])
    (?:
        (?P<count>\d+)?d(?P<sides>\d+)
        (?P<modifiers>(?:[!]|[kd][hl]\d+|[<>]=?\d+)*)
      |
        (?P<constant>\d+)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# One modifier chunk inside the modifiers group.
MOD_RE = re.compile(r"(?P<kind>[!]|[kd][hl]|[<>]=?)(?P<num>\d+)?", re.IGNORECASE)

# Guardrails -- reject pathological inputs with a clear error.
MAX_DICE_PER_TERM = 10_000
MAX_STATS_ROLLS = 1_000_000
EXPLODE_CAP = 100


@dataclass
class DieTerm:
    """A single dice block like 4d6kh3 or 1d6!."""
    count: int
    sides: int
    sign: int = 1                            # +1 or -1
    keep_highest: Optional[int] = None
    keep_lowest: Optional[int] = None
    drop_highest: Optional[int] = None
    drop_lowest: Optional[int] = None
    exploding: bool = False
    success_op: Optional[str] = None         # ">", ">=", "<", "<="
    success_threshold: Optional[int] = None
    raw: str = ""                            # term text without its sign


@dataclass
class ConstantTerm:
    """A signed integer term like +2 or -1."""
    value: int
    sign: int = 1
    raw: str = ""


Term = Union[DieTerm, ConstantTerm]


# Map from modifier keyword to the DieTerm attribute it should set.
_KEEP_DROP_ATTR = {
    "kh": "keep_highest",
    "kl": "keep_lowest",
    "dh": "drop_highest",
    "dl": "drop_lowest",
}


def _apply_modifiers(term: DieTerm, mods: str) -> None:
    """Parse the modifier tail (kh3, dl1, !, >=7, ...) onto a dice term."""
    pos = 0
    while pos < len(mods):
        m = MOD_RE.match(mods, pos)
        if not m:
            raise ValueError(f"Unknown modifier near: {mods[pos:]!r}")
        kind = m.group("kind").lower()
        num = int(m.group("num")) if m.group("num") else None

        if kind == "!":
            term.exploding = True
        elif kind in _KEEP_DROP_ATTR:
            if num is None:
                raise ValueError(f"Modifier {kind} needs a number")
            if not (1 <= num < term.count):
                raise ValueError(
                    f"Modifier {kind}{num} needs 1 <= N < {term.count} "
                    f"for {term.raw!r}"
                )
            setattr(term, _KEEP_DROP_ATTR[kind], num)
        elif kind in (">", ">=", "<", "<="):
            if num is None:
                raise ValueError(f"Modifier {kind} needs a number")
            term.success_op = kind
            term.success_threshold = num
        else:
            raise ValueError(f"Unknown modifier: {kind!r}")

        pos = m.end()


def parse_expression(expr: str) -> List[Term]:
    """Parse a dice expression into a list of signed terms."""
    s = expr.strip().replace(" ", "")
    if not s:
        raise ValueError("Empty expression")
    # Prepend an explicit "+" so every term starts with a sign.
    if s[0] not in "+-":
        s = "+" + s

    terms: List[Term] = []
    pos = 0
    while pos < len(s):
        m = TOKEN_RE.match(s, pos)
        if not m or m.end() == pos:
            raise ValueError(f"Could not parse expression near: {s[pos:]!r}")
        pos = m.end()

        sign = -1 if m.group("sign") == "-" else 1
        # Strip the leading sign char so raw is just "3d6" not "+3d6".
        raw_body = m.group(0).lstrip("+-")

        if m.group("constant") is not None:
            terms.append(ConstantTerm(
                value=int(m.group("constant")),
                sign=sign,
                raw=raw_body,
            ))
            continue

        count = int(m.group("count")) if m.group("count") else 1
        sides = int(m.group("sides"))
        if sides < 2:
            raise ValueError(f"Dice need at least 2 sides: {raw_body!r}")
        if count < 1:
            raise ValueError(f"Must roll at least 1 die: {raw_body!r}")
        if count > MAX_DICE_PER_TERM:
            raise ValueError(
                f"Too many dice (max {MAX_DICE_PER_TERM:,}): {raw_body!r}"
            )

        term = DieTerm(count=count, sides=sides, sign=sign, raw=raw_body)
        _apply_modifiers(term, m.group("modifiers") or "")
        terms.append(term)

    return terms


# --- rolling --------------------------------------------------------------- #

def _roll_one(sides: int, rng: random.Random, exploding: bool) -> List[int]:
    """Roll one die. Returns a list; length > 1 only when the die exploded."""
    rolls = [rng.randint(1, sides)]
    if exploding and sides > 1:
        explosions = 0
        while rolls[-1] == sides and explosions < EXPLODE_CAP:
            rolls.append(rng.randint(1, sides))
            explosions += 1
    return rolls


def _pick_indices(values: List[int], n: int, highest: bool) -> set:
    """Return the n indices with the highest or lowest values."""
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=highest)
    return set(order[:n])


def _evaluate_term(term: Term, rng: random.Random) -> Tuple[int, str]:
    """Evaluate one term and return (signed_value, human-readable detail)."""
    if isinstance(term, ConstantTerm):
        signed = term.sign * term.value
        return signed, f"{'+' if term.sign > 0 else '-'}{term.value}"

    # DieTerm: roll dice, then apply keep/drop, then success-count or sum.
    raw_rolls = [_roll_one(term.sides, rng, term.exploding)
                 for _ in range(term.count)]
    die_values = [sum(r) for r in raw_rolls]

    # Decide which dice survive keep/drop.
    all_idx = set(range(len(die_values)))
    if term.keep_highest is not None:
        kept = _pick_indices(die_values, term.keep_highest, highest=True)
    elif term.keep_lowest is not None:
        kept = _pick_indices(die_values, term.keep_lowest, highest=False)
    elif term.drop_highest is not None:
        kept = all_idx - _pick_indices(die_values, term.drop_highest, highest=True)
    elif term.drop_lowest is not None:
        kept = all_idx - _pick_indices(die_values, term.drop_lowest, highest=False)
    else:
        kept = all_idx
    kept_mask = [i in kept for i in range(len(die_values))]
    kept_values = [v for v, k in zip(die_values, kept_mask) if k]

    # Reduce kept dice to a number: success count or plain sum.
    if term.success_threshold is not None:
        target = term.success_threshold
        hits = {
            ">":  lambda v: v >  target,
            ">=": lambda v: v >= target,
            "<":  lambda v: v <  target,
            "<=": lambda v: v <= target,
        }[term.success_op]
        subtotal = sum(1 for v in kept_values if hits(v))
        tail = f" -> {subtotal} success(es)"
    else:
        subtotal = sum(kept_values)
        tail = f" -> {subtotal}"

    # Build the per-die breakdown string.
    parts = []
    for v, k, raw in zip(die_values, kept_mask, raw_rolls):
        s = "!".join(str(x) for x in raw) if len(raw) > 1 else str(raw[0])
        if not k:
            s = f"~~{s}~~"
        parts.append(s)
    detail = f"{'+' if term.sign > 0 else '-'}{term.raw}[{', '.join(parts)}]{tail}"

    return term.sign * subtotal, detail


@dataclass
class RollResult:
    expression: str
    total: int
    detail: str


def roll_expression(expr: str, rng: Optional[random.Random] = None) -> RollResult:
    """Parse, roll, and return a single evaluated result."""
    if rng is None:
        rng = random.SystemRandom()
    terms = parse_expression(expr)
    total = 0
    parts: List[str] = []
    for t in terms:
        value, detail = _evaluate_term(t, rng)
        total += value
        parts.append(detail)
    text = " ".join(parts)
    # Drop the cosmetic leading "+" from the first positive term.
    if text.startswith("+"):
        text = text[1:]
    return RollResult(expression=expr, total=total, detail=text)


def compute_distribution(expr: str, n_rolls: int,
                         rng: Optional[random.Random] = None) -> dict:
    """Run expr n_rolls times. Return summary stats plus a full histogram."""
    if rng is None:
        rng = random.SystemRandom()
    totals = [roll_expression(expr, rng).total for _ in range(n_rolls)]
    counter = Counter(totals)
    n = len(totals)
    return {
        "expression": expr,
        "n_rolls": n,
        "min": min(totals),
        "max": max(totals),
        "mean": sum(totals) / n,
        "median": sorted(totals)[n // 2],
        "distribution": {
            str(k): {"count": v, "percent": round(100 * v / n, 3)}
            for k, v in sorted(counter.items())
        },
    }


# --- CLI ------------------------------------------------------------------- #

def _print_single(result: RollResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps({
            "expression": result.expression,
            "total": result.total,
            "detail": result.detail,
        }, indent=2))
    else:
        print(f"Expression: {result.expression}")
        print(f"Detail:     {result.detail}")
        print(f"Total:      {result.total}")


def _print_stats(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2))
        return
    print(f"Expression: {result['expression']}")
    print(f"Rolled {result['n_rolls']:,} times.")
    print(f"Min: {result['min']}   Max: {result['max']}   "
          f"Mean: {result['mean']:.3f}   Median: {result['median']}")
    print("Distribution:")
    # Scale the bar so the mode fills about 40 characters.
    max_pct = max(info["percent"] for info in result["distribution"].values())
    scale = 40 / max_pct if max_pct > 0 else 1
    for value, info in result["distribution"].items():
        bar = "#" * int(info["percent"] * scale)
        print(f"  {value:>6}: {info['count']:>7,}  "
              f"({info['percent']:6.2f}%) {bar}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Roll dice using RPG dice notation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("expression",
                    help='Dice expression, e.g. "3d6+2" or "4d6kh3".')
    ap.add_argument("--stats", action="store_true",
                    help="Compute a distribution over many rolls.")
    ap.add_argument("--rolls", type=int, default=10_000,
                    help="Number of rolls for --stats (default 10000).")
    ap.add_argument("--seed", type=int, default=None,
                    help="Seed the RNG for tests only. A seeded 'roll' is "
                         "reproducible and therefore not random.")
    ap.add_argument("--json", action="store_true",
                    help="Emit JSON instead of human-readable text.")
    args = ap.parse_args()

    rng = random.Random(args.seed) if args.seed is not None else random.SystemRandom()

    try:
        if args.stats:
            if not (1 <= args.rolls <= MAX_STATS_ROLLS):
                raise ValueError(
                    f"--rolls must be between 1 and {MAX_STATS_ROLLS:,}"
                )
            result = compute_distribution(args.expression, args.rolls, rng)
            _print_stats(result, args.json)
        else:
            result = roll_expression(args.expression, rng)
            _print_single(result, args.json)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # Downstream (e.g. `head`) closed the pipe -- exit cleanly.
        sys.exit(0)
