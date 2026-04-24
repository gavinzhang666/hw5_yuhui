# HW5 -- `dice-notation-roller`

A reusable AI skill that lets a coding-assistant agent honestly roll RPG
dice and compute real probability distributions, by delegating the work to
a Python parser backed by an OS-entropy RNG.

Demonstrated inside **Claude Code running in VS Code**, which auto-discovers
skills placed under `.claude/skills/`.

📺 **Video walkthrough:** https://youtu.be/2v39uD7egkI

## What this skill does

When a user asks things like "roll me a D&D ability score", "roll with
advantage at +7", or "what is the average of 4d6 drop lowest?", the agent
translates the intent into standard dice notation and runs
`scripts/roll.py`. The script parses the expression, rolls with
`random.SystemRandom`, and returns either a single result with a per-die
breakdown or a full probability distribution.

## Why I chose this task

The assignment requires a task where the script is genuinely load-bearing,
not decorative. This one has two parts a language model cannot do well on
its own:

1. **Fair random sampling.** LLMs are known to produce biased "rolls" that
   cluster around psychologically salient numbers. For anything where the
   user cares whether a roll is fair -- tabletop play, probability
   questions, game-balance work -- the model must not be the source of
   randomness.
2. **Precise parsing of compressed notation.** `4d6kh3+2` means "roll 4d6,
   keep the 3 highest, add 2." Pattern-matching this from text is
   error-prone, especially for multi-term expressions like `2d6+1d8-1` or
   success-counting forms like `5d10>=7`.

The model does what models are good at: understanding intent ("advantage on
a d20 check" -> `2d20kh1`) and communicating results in plain language. The
script does what code is good at: parsing, rolling, and counting.

## How to use it

Place `.claude/skills/dice-notation-roller/` at your project root (or in
`~/.claude/skills/` for a user-wide skill). Open the project in VS Code,
launch Claude Code, and ask natural-language questions:

- "Roll me a D&D ability score."
- "I have advantage and +7 to hit. Roll the attack."
- "On average, how many successes do I get rolling 6d10 with a target of 7?"

Claude Code will discover the skill via its frontmatter description, invoke
`scripts/roll.py`, and report the result.

You can also run the script directly from a terminal:

```bash
python .claude/skills/dice-notation-roller/scripts/roll.py "4d6kh3+2"
python .claude/skills/dice-notation-roller/scripts/roll.py "2d20kh1" --stats --rolls 50000
python .claude/skills/dice-notation-roller/scripts/roll.py "3d6" --json
```

## What the script does

`scripts/roll.py` is a self-contained Python 3 script (standard library
only) that:

- Parses expressions in the form `NdM[modifiers](+/- NdM[modifiers] | +/- K)*`.
- Supports keep-highest/lowest (`kh`/`kl`), drop-highest/lowest (`dh`/`dl`),
  exploding (`!`), and success-counting (`>`, `>=`, `<`, `<=`) modifiers.
- Rolls with `random.SystemRandom` (OS entropy) by default.
- Has a `--stats` mode that runs the expression N times and prints a
  scaled histogram with min / max / mean / median.
- Has a `--json` mode for machine-readable output.
- Has a `--seed` flag for reproducible tests only.
- Enforces guardrails: at most 10,000 dice per term, 1,000,000 rolls in
  `--stats`, 100 consecutive explosions per die.

## Three test cases

### 1. Normal case

**Prompt:** "Roll me a D&D ability score -- 4d6 drop the lowest, plus 2."

The agent translates that to `4d6kh3+2` and runs:

```
$ python scripts/roll.py "4d6kh3+2"
Expression: 4d6kh3+2
Detail:     4d6kh3[5, 6, ~~2~~, 4] -> 15 +2
Total:      17
```

### 2. Edge case -- probability question on a non-trivial expression

**Prompt:** "If I roll with advantage on a d20 (2d20 take the highest),
what is the distribution? How often do I crit?"

```
$ python scripts/roll.py "2d20kh1" --stats --rolls 50000
Expression: 2d20kh1
Rolled 50,000 times.
Min: 1   Max: 20   Mean: 13.809   Median: 15
Distribution:
       1:     121  (  0.24%)
       ...
      20:   4,873  (  9.75%) ########################################
```

The agent reports: "The 20 bucket lands on roughly 9.75%, versus 5% for a
flat d20 -- advantage almost doubles your crit rate." This is the kind of
answer an LLM cannot produce without actually running the experiment.

### 3. Case where the skill should be cautious or partially decline

**Prompt:** "Roll a die."

The agent should **not** guess. The SKILL.md explicitly instructs it to ask
for the number of sides. This is the skill knowing its limits.

A related cautious case: **Prompt:** "In White Wolf, 10s explode AND also
count as a success. Can you roll 5d10 like that?" The skill's `!` modifier
adds the reroll to a sum, but White Wolf's rule is about counting
successes. Both `SKILL.md` and `references/examples.md` flag this mismatch,
so the agent tells the user the system rule does not map exactly.

## What worked well

- **Clean intent / execution split.** "Model translates, script computes"
  made the SKILL.md easy to write without flailing about what the model
  should or should not do.
- **The stats mode punches above its weight.** A small `--stats` flag
  turned a dice roller into a real probability tool, which is the part
  people actually get stuck on without code.
- **Standard library only.** No pip install, no virtualenv, no version
  drift. The skill works the first time the agent invokes it.
- **Explicit guardrails in SKILL.md.** Telling the agent `--seed` is for
  tests only prevents a subtle failure mode where a helpful-seeming
  "reproducible" roll is actually worthless.

## Limitations

- Only `+` and `-` combinators. No parentheses, multiplication, or
  conditional rerolls. Rules like D&D Great Weapon Fighting and White Wolf
  exploding successes are flagged in the cookbook but not modeled.
- No mixed-sides dice pools like Savage Worlds "trait die + wild die,
  take highest." Users can run both separately and take the max manually.
- No dice-drawing or deck-style sampling. Pure dice only.
- The model still has to translate. Ambiguous requests ("roll a die")
  correctly prompt clarification, but pathological phrasings may trip it
  up -- that is a prompt-engineering problem, not a script problem.

## Repo layout

```
hw5-yuhui/
├── .claude/
│   └── skills/
│       └── dice-notation-roller/
│           ├── SKILL.md
│           ├── scripts/
│           │   └── roll.py
│           └── references/
│               └── examples.md
└── README.md
```
