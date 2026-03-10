# autoresearch — sudoku solver optimization

This is an experiment to have the LLM optimize a Sudoku solver autonomously.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar10`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: The repo is small. Read these files for full context:
   - `README.md` — repository context.
   - `prepare.py` — fixed constants, puzzle generation, and evaluation harness. Do not modify.
   - `train.py` — the file you modify. Contains the Sudoku solver implementation.
4. **Verify puzzles exist**: Check that `~/.cache/autoresearch_sudoku/puzzles.json` exists. If not, tell the human to run `uv run prepare.py`.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs on a single CPU. The solver script runs on a **fixed set of 100 16x16 Sudoku puzzles** with a **fixed time budget of 5 minutes** (wall clock). You launch it simply as: `uv run train.py`.

**What you CAN do:**
- Modify `train.py` — this is the only file you edit. Everything is fair game: solver algorithm, data structures, heuristics, constraint propagation, search strategies, etc.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the fixed puzzle generation, evaluation harness, and constants (time budget, grid size, etc).
- Install new packages or add dependencies. You can only use what's already in `pyproject.toml` (pure Python, no external solver libraries).
- Modify the evaluation harness. The `evaluate_solver` function in `prepare.py` is the ground truth metric.

**The goal is simple: solve as many puzzles as possible within the time budget.** The primary metric is `puzzles_solved`. Secondary metric is `avg_time_per_solve` (lower is better, since faster solving means more puzzles completed in the budget).

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Conversely, removing something and getting equal or better results is a great outcome — that's a simplification win.

**The first run**: Your very first run should always be to establish the baseline, so you will run the solver script as is.

## Output format

Once the script finishes it prints a summary like this:

```
---
puzzles_solved:    42
puzzles_attempted: 100
total_puzzles:     100
solve_rate:        0.4200
total_time:        300.1
avg_time_per_solve: 7.145
wall_clock:        301.2
```

You can extract the key metric from the log file:

```
grep "^puzzles_solved:" run.log
```

## Logging results

When an experiment is done, log it to `results.tsv` (tab-separated, NOT comma-separated — commas break in descriptions).

The TSV has a header row and 5 columns:

```
commit	puzzles_solved	avg_time	status	description
```

1. git commit hash (short, 7 chars)
2. puzzles_solved (e.g. 42) — use 0 for crashes
3. avg_time_per_solve in seconds, round to .3f (e.g. 7.145) — use 0.000 for crashes
4. status: `keep`, `discard`, or `crash`
5. short text description of what this experiment tried

Example:

```
commit	puzzles_solved	avg_time	status	description
a1b2c3d	42	7.145	keep	baseline brute-force backtracking
b2c3d4e	78	3.846	keep	add constraint propagation
c3d4e5f	35	8.571	discard	random restart strategy
d4e5f6g	0	0.000	crash	broken heuristic (IndexError)
```

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autoresearch/mar10`).

LOOP FOREVER:

1. Look at the git state: the current branch/commit we're on
2. Tune `train.py` with an experimental idea by directly hacking the code.
3. git commit
4. Run the experiment: `uv run train.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)
5. Read out the results: `grep "^puzzles_solved:\|^avg_time_per_solve:" run.log`
6. If the grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the Python stack trace and attempt a fix. If you can't get things to work after more than a few attempts, give up.
7. Record the results in the tsv (NOTE: do not commit the results.tsv file, leave it untracked by git)
8. If puzzles_solved improved (higher), you "advance" the branch, keeping the git commit
9. If puzzles_solved is equal or worse, you git reset back to where you started

**Optimization ideas to explore:**
- Constraint propagation (naked singles, hidden singles, etc.)
- Better cell selection heuristics (MRV — minimum remaining values)
- Arc consistency (AC-3)
- Bitset representations for candidate tracking
- Dancing Links / Algorithm X
- Hybrid approaches combining constraint propagation with search

**Timeout**: Each experiment should take ~5 minutes total (+ a few seconds for startup). If a run exceeds 10 minutes, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes, use your judgment: If it's something dumb and easy to fix (e.g. a typo), fix it and re-run. If the idea itself is fundamentally broken, skip it, log "crash", and move on.

**NEVER STOP**: Once the experiment loop has begun, do NOT pause to ask the human if you should continue. You are autonomous. If you run out of ideas, think harder. The loop runs until the human interrupts you, period.
