# autoresearch — sudoku

Autonomous AI-driven optimization of a 16x16 Sudoku solver.

## Overview

Give an AI agent a brute-force Sudoku solver and let it experiment autonomously. It modifies the solver code, runs on a fixed set of 100 puzzles with a 5-minute time budget, checks if more puzzles were solved, keeps or discards the change, and repeats. You come back to a log of experiments and (hopefully) a much faster solver.

## How it works

The repo has three files that matter:

- **`prepare.py`** — fixed constants, puzzle generation, and evaluation harness. Generates 100 16x16 Sudoku puzzles of varying difficulty and scores solvers. Not modified.
- **`train.py`** — the single file the agent edits. Contains the Sudoku solver implementation. Starts as a simple brute-force backtracker. **This file is edited and iterated on by the agent**.
- **`program.md`** — baseline instructions for the agent. **This file is edited and iterated on by the human**.

The metric is **puzzles_solved** — how many of the 100 puzzles are correctly solved within the 5-minute time budget. Higher is better. Secondary metric is **avg_time_per_solve** (lower is better).

## Quick start

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv/).

```bash
# 1. Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Generate puzzles (one-time)
uv run prepare.py

# 4. Run the solver baseline
uv run train.py
```

## Project structure

```
prepare.py      — constants, puzzle generation, evaluation harness (do not modify)
train.py        — sudoku solver implementation (agent modifies this)
program.md      — agent instructions
pyproject.toml  — dependencies
```

## License

MIT
