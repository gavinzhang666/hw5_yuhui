---
name: dice-notation-roller
description: Rolls and analyzes RPG dice expressions such as "3d6+2", "4d6kh3" (D&D ability scores), "2d20kh1" (advantage), "2d20kl1" (disadvantage), "5d10>=7" (success counting), and "1d6!" (exploding dice). Also computes probability distributions over thousands of rolls with --stats. Use when the user asks to roll dice, simulate RPG outcomes, or answer probability questions about dice. Do NOT use for generic "pick a random number" requests or for cryptographic randomness.
---

# Dice Notation Roller

This skill turns a natural-language dice request into a precise dice
expression, then hands that expression to `scripts/roll.py`, which does the
actual parsing and rolling with a cryptographically strong RNG.

## Why a script is load-bearing here

Language models cannot do this task alone:

1. **LLMs cannot roll fair dice.** They produce plausible-looking but
   non-uniform sequences, and they cannot sample from non-trivial
   distributions like "2d20 keep highest" at all.
2. **Modifiers like `4d6kh3+2` need a real parser.** Pattern-matching on
   text silently mishandles edge cases (keep vs. drop, exploding chains,
   multi-term expressions with mixed signs).

The model's job is intent to expression. The script's job is expression to
an honest result.

## When to use this skill

- The user asks to roll dice ("roll 3d6", "roll for initiative").
- The user describes an RPG situation that implies dice: advantage,
  disadvantage, ability scores, attack rolls with modifiers.
- The user asks a probability question about dice: "what's the average of
  4d6 drop lowest", "how often do I crit with advantage".
- The user wants to compare outcomes of different dice expressions.

## When NOT to use this skill

- The user just wants a random integer with no dice semantics -- a one-line
  `random.randint` is simpler.
- The user wants weighted choices, deck-of-cards sampling, or shuffling --
  this skill only does dice.
- The user wants a cryptographic secret or token -- direct them to the
  `secrets` module.
- The request is ambiguous ("roll a die" with no sides specified) -- ask a
  clarifying question instead of guessing.

## Supported notation

| Syntax          | Meaning                                   | Example     |
|-----------------|-------------------------------------------|-------------|
| `NdM`           | Roll N dice with M sides (N defaults 1)   | `3d6`, `d20`|
| `NdM+K` / `-K`  | Add or subtract a constant modifier       | `1d20+5`    |
| `NdMkhK`        | Roll N, keep K highest                    | `4d6kh3`    |
| `NdMklK`        | Roll N, keep K lowest                     | `2d20kl1`   |
| `NdMdhK`        | Roll N, drop K highest                    | `4d6dh1`    |
| `NdMdlK`        | Roll N, drop K lowest                     | `4d6dl1`    |
| `NdM!`          | Exploding -- reroll and add on max        | `1d6!`      |
| `NdM>T` / `>=T` | Count dice strictly / inclusively above T | `5d10>=7`   |
| `NdM<T` / `<=T` | Count dice strictly / inclusively below T | `3d6<=2`    |

Terms combine with `+` or `-`, for example `2d6+1d8-1`.

## How to run

Single roll:

```
python scripts/roll.py "4d6kh3+2"
```

Probability distribution (rolls the expression N times, prints a histogram):

```
python scripts/roll.py "2d20kh1" --stats --rolls 50000
```

JSON output for structured downstream use:

```
python scripts/roll.py "3d6" --json
```

Reproducible output for testing only (real rolls should never use `--seed`):

```
python scripts/roll.py "3d6" --seed 42
```

## Step-by-step workflow

1. **Read intent.** Confirm the user is asking about dice, not generic
   randomness.
2. **Translate intent to notation.** Common mappings:
   - "Roll with advantage on a d20" -> `2d20kh1`
   - "Roll with disadvantage" -> `2d20kl1`
   - "Standard D&D ability score (4d6 drop lowest)" -> `4d6kh3`
   - "Attack at +7" -> `1d20+7`
   - "5 WoD dice, successes on 7+" -> `5d10>=7`
   - "Savage Worlds exploding d6" -> `1d6!`
3. **Choose mode.**
   - Outcome question ("roll it") -> single-roll mode.
   - Probability question ("on average", "how often", "distribution of")
     -> `--stats` with 10k to 100k rolls.
4. **Run the script** from the skill folder.
5. **Report conversationally.** Include the `Detail:` breakdown when it
   helps the user see kept vs. dropped dice (especially for `4d6kh3`). For
   `--stats`, cite min / max / mean and a few relevant buckets -- do not
   dump the whole histogram.
6. **If a request maps to multiple reasonable expressions, ask** which
   mapping the user means. Example: "exploding successes" in White Wolf
   games is not the same as `!` here; flag the mismatch.

## Output format

Single-roll human-readable mode prints three lines:

```
Expression: 4d6kh3+2
Detail:     4d6kh3[5, 6, ~~2~~, 4] -> 15 +2
Total:      17
```

- Dropped dice appear in `~~strikethrough~~`.
- Exploded dice appear as `6!4` (rolled a 6, exploded, added 4).

`--stats` mode prints a histogram scaled to the most common outcome, plus
min / max / mean / median.

`--json` emits `{"expression", "total", "detail"}` for single rolls, or a
full distribution object for `--stats`.

## Limitations and safeguards

- **Max 10,000 dice per term.** Rejected with a clear error.
- **Max 1,000,000 rolls in `--stats` mode.** Rejected with a clear error.
- **Max 100 consecutive explosions per die.** Prevents runaway loops.
- **No parentheses, no multiplication, no conditional rerolls.** Only `+`
  and `-` between terms.
- **No system-specific rules** (White Wolf exploding successes, Shadowrun
  edge-spending, D&D Great Weapon Fighting rerolls). Tell the user when
  their system rule does not map cleanly onto the supported notation.
- **Default RNG is `random.SystemRandom`** (OS entropy). The `--seed` flag
  exists for tests -- do not use it to answer real user rolls. A seeded
  "roll" is reproducible and therefore not a roll.

See `references/examples.md` for a larger cookbook of patterns covering
D&D 5e, Pathfinder, World of Darkness, Savage Worlds, and common
probability questions.
