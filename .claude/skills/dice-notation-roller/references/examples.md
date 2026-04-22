# Dice Expression Cookbook

Quick reference for mapping common RPG requests onto the notation supported
by `scripts/roll.py`. Consult this when a user's phrasing is ambiguous or
when they invoke a system-specific term.

## D&D 5e / Pathfinder

| Situation                                  | Expression            |
|--------------------------------------------|-----------------------|
| Standard ability score (4d6 drop lowest)   | `4d6kh3` or `4d6dl1`  |
| Attack roll at +5 to hit                   | `1d20+5`              |
| Advantage on a d20 check                   | `2d20kh1`             |
| Disadvantage on a d20 check                | `2d20kl1`             |
| Elven Accuracy (3d20 keep highest)         | `3d20kh1`             |
| Longsword damage (1d8+3)                   | `1d8+3`               |
| Critical longsword (2d8+3)                 | `2d8+3`               |
| Fireball at 3rd level                      | `8d6`                 |
| Sneak attack at level 11                   | `6d6`                 |

**Not cleanly expressible:**

- Great Weapon Fighting (reroll 1s and 2s, keep second roll). The real
  distribution differs from `4d6`; tell the user.
- Halfling Lucky (reroll natural 1s once). Not supported.

## World of Darkness / Storyteller

| Situation                               | Expression  |
|-----------------------------------------|-------------|
| Basic dice pool, success on 7+          | `5d10>=7`   |
| Difficulty 8                            | `5d10>=8`   |
| Counting only natural 10s (crit)        | `5d10>=10`  |

**Not cleanly expressible:** 10s that both count as a success AND let you
reroll for more successes. The skill's `!` adds exploded results to a sum;
World of Darkness counts successes. Tell the user this does not map.

## Savage Worlds / Shadowrun

| Situation                                  | Expression |
|--------------------------------------------|------------|
| Trait die that aces on max                 | `1d8!`     |
| Exploding d6 "ace"                         | `1d6!`     |
| Shadowrun 5 dice pool, hits on 5+          | `5d6>=5`   |

**Not cleanly expressible:** Savage Worlds "roll trait + wild die, keep
highest" mixes two different dice types. You can run both separately and
take the max manually, but the skill cannot combine `1d8!` and `1d6!` into
one "take highest" roll.

## Generic probability questions

Use `--stats --rolls 100000` for tight estimates.

| Question                                          | Command |
|---------------------------------------------------|---------|
| "What is the average of 3d6?"                     | `roll.py "3d6" --stats --rolls 100000` |
| "How likely is 15+ on 4d6 drop lowest?"           | `roll.py "4d6kh3" --stats --rolls 100000` -- sum buckets >= 15 |
| "How often do I crit (20) with advantage?"        | `roll.py "2d20kh1" --stats --rolls 100000` -- read the 20 bucket |
| "Expected successes on 6d10 versus target 7?"     | `roll.py "6d10>=7" --stats --rolls 100000` -- read the mean |

## Cautions to surface to the user

- **Seeded rolls are not rolls.** If the user asks for a seeded roll "for
  fun", explain that the seed makes it deterministic -- useful for demos,
  useless for actual play.
- **Huge dice pools are slow in `--stats` mode.** 1,000,000 runs x 1000
  dice per roll means a billion rolls. Warn before running.
- **Long-term "fairness".** OS entropy is effectively fair over any
  sensible number of rolls. If the user suspects something is off, suggest
  running `--stats` and comparing to the theoretical distribution.
