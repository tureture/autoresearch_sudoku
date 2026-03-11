"""
Puzzle preparation and evaluation harness for autoresearch sudoku experiments.
Generates sets of 9x9, 16x16, and 25x25 Sudoku puzzles and provides scoring.

Usage:
    python prepare.py          # generate all puzzles

Puzzles are stored in data/ inside the repo.
"""

import os
import json
import copy
import time
import random
import argparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIME_BUDGET = 300       # solver time budget in seconds (5 minutes)
SEED = 42

TIERS = [
    {"grid_size": 9,  "box_h": 3, "box_w": 3, "num_puzzles": 100, "label": "9x9",
     "min_clues": 25, "max_clues": 40},
    {"grid_size": 16, "box_h": 4, "box_w": 4, "num_puzzles": 100, "label": "16x16",
     "min_clues": 80, "max_clues": 120},
    {"grid_size": 25, "box_h": 5, "box_w": 5, "num_puzzles": 100, "label": "25x25",
     "min_clues": 200, "max_clues": 300},
]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PUZZLES_FILE = os.path.join(DATA_DIR, "puzzles.json")

# ---------------------------------------------------------------------------
# Puzzle generator (pattern-based + shuffle for fast generation at any size)
# ---------------------------------------------------------------------------

def _generate_full_grid(grid_size, box_h, box_w, rng_seed):
    """Generate a complete valid Sudoku grid using pattern construction + shuffling."""
    random.seed(rng_seed)
    n = grid_size

    # Base pattern: produces a valid Sudoku grid
    def pattern(r, c):
        return (box_w * (r % box_h) + r // box_h + c) % n

    grid = [[pattern(r, c) + 1 for c in range(n)] for r in range(n)]

    # Permute values
    perm = list(range(1, n + 1))
    random.shuffle(perm)
    grid = [[perm[grid[r][c] - 1] for c in range(n)] for r in range(n)]

    # Shuffle rows within each band
    for band_start in range(0, n, box_h):
        rows = list(range(band_start, band_start + box_h))
        random.shuffle(rows)
        shuffled = [grid[r][:] for r in rows]
        for i, r in enumerate(range(band_start, band_start + box_h)):
            grid[r] = shuffled[i]

    # Shuffle columns within each stack
    for stack_start in range(0, n, box_w):
        cols = list(range(stack_start, stack_start + box_w))
        random.shuffle(cols)
        for r in range(n):
            vals = [grid[r][c] for c in cols]
            for i, c in enumerate(range(stack_start, stack_start + box_w)):
                grid[r][c] = vals[i]

    # Shuffle bands (groups of box_h rows)
    num_bands = n // box_h
    band_order = list(range(num_bands))
    random.shuffle(band_order)
    new_grid = []
    for b in band_order:
        for r in range(b * box_h, (b + 1) * box_h):
            new_grid.append(grid[r][:])
    grid = new_grid

    # Shuffle stacks (groups of box_w columns)
    num_stacks = n // box_w
    stack_order = list(range(num_stacks))
    random.shuffle(stack_order)
    for r in range(n):
        new_row = []
        for s in stack_order:
            for c in range(s * box_w, (s + 1) * box_w):
                new_row.append(grid[r][c])
        grid[r] = new_row

    return grid


def _create_puzzle(full_grid, grid_size, num_clues, rng_seed):
    """Remove cells from a full grid to create a puzzle with num_clues clues."""
    random.seed(rng_seed)
    puzzle = copy.deepcopy(full_grid)
    total_cells = grid_size * grid_size
    cells_to_remove = total_cells - num_clues
    positions = [(r, c) for r in range(grid_size) for c in range(grid_size)]
    random.shuffle(positions)
    removed = 0
    for r, c in positions:
        if removed >= cells_to_remove:
            break
        puzzle[r][c] = 0
        removed += 1
    return puzzle


def _current_config():
    """Config dict embedded in puzzles.json for cache invalidation."""
    return {
        "tiers": [
            {"grid_size": t["grid_size"], "box_h": t["box_h"], "box_w": t["box_w"],
             "num_puzzles": t["num_puzzles"], "min_clues": t["min_clues"],
             "max_clues": t["max_clues"]}
            for t in TIERS
        ],
        "seed": SEED,
    }


def generate_puzzles(seed=SEED):
    """Generate all puzzle tiers."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(PUZZLES_FILE):
        with open(PUZZLES_FILE, "r") as f:
            data = json.load(f)
        if data.get("config") == _current_config():
            print(f"Puzzles: already generated at {PUZZLES_FILE}")
            return data["puzzles"]
        print("Config changed, regenerating puzzles...")

    all_puzzles = []
    global_id = 0

    for tier in TIERS:
        gs = tier["grid_size"]
        bh = tier["box_h"]
        bw = tier["box_w"]
        np_ = tier["num_puzzles"]
        label = tier["label"]
        min_c = tier["min_clues"]
        max_c = tier["max_clues"]

        print(f"Generating {np_} {label} puzzles...")

        for i in range(np_):
            clues = min_c + (i * (max_c - min_c) // np_)
            grid_seed = seed + global_id * 1000
            puzzle_seed = seed + global_id * 1000 + 500

            full_grid = _generate_full_grid(gs, bh, bw, grid_seed)
            puzzle = _create_puzzle(full_grid, gs, clues, puzzle_seed)

            all_puzzles.append({
                "id": global_id,
                "label": f"{label}_{i:03d}",
                "grid_size": gs,
                "box_h": bh,
                "box_w": bw,
                "clues": clues,
                "puzzle": puzzle,
                "solution": full_grid,
            })
            global_id += 1

            if (i + 1) % 25 == 0:
                print(f"  Generated {i + 1}/{np_} {label} puzzles")

    data = {"config": _current_config(), "puzzles": all_puzzles}
    with open(PUZZLES_FILE, "w") as f:
        json.dump(data, f)

    print(f"Saved {len(all_puzzles)} total puzzles to {PUZZLES_FILE}")
    return all_puzzles


def load_puzzles():
    """Load puzzles from disk."""
    if not os.path.exists(PUZZLES_FILE):
        print("No puzzles found, generating...")
        return generate_puzzles()
    with open(PUZZLES_FILE, "r") as f:
        data = json.load(f)
    if data.get("config") != _current_config():
        print("Config changed since last generation, regenerating...")
        return generate_puzzles()
    return data["puzzles"]

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_solution(puzzle, solution, grid_size, box_h, box_w):
    """Validate a proposed solution. Returns (is_correct, error_message)."""
    if solution is None:
        return False, "No solution returned"

    if len(solution) != grid_size:
        return False, f"Wrong number of rows: {len(solution)}"
    for r in range(grid_size):
        if len(solution[r]) != grid_size:
            return False, f"Wrong number of columns in row {r}: {len(solution[r])}"

    for r in range(grid_size):
        for c in range(grid_size):
            if puzzle[r][c] != 0 and solution[r][c] != puzzle[r][c]:
                return False, f"Clue at ({r},{c}) changed: {puzzle[r][c]} -> {solution[r][c]}"

    for r in range(grid_size):
        for c in range(grid_size):
            if not (1 <= solution[r][c] <= grid_size):
                return False, f"Invalid value at ({r},{c}): {solution[r][c]}"

    for r in range(grid_size):
        if len(set(solution[r])) != grid_size:
            return False, f"Duplicate in row {r}"

    for c in range(grid_size):
        col = [solution[r][c] for r in range(grid_size)]
        if len(set(col)) != grid_size:
            return False, f"Duplicate in column {c}"

    for br in range(0, grid_size, box_h):
        for bc in range(0, grid_size, box_w):
            box = []
            for r in range(br, br + box_h):
                for c in range(bc, bc + box_w):
                    box.append(solution[r][c])
            if len(set(box)) != grid_size:
                return False, f"Duplicate in box at ({br},{bc})"

    return True, "OK"


# ---------------------------------------------------------------------------
# Cooperative timeout mechanism
# ---------------------------------------------------------------------------

class SolverTimeout(Exception):
    """Raised by check_deadline() when the time budget is exhausted."""
    pass

_deadline = float("inf")

def check_deadline():
    """Call periodically inside solver. Raises SolverTimeout if time budget exceeded."""
    if time.time() >= _deadline:
        raise SolverTimeout("time budget exceeded")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_solver(solve_fn, puzzles, time_budget=TIME_BUDGET):
    """
    Evaluate a solver on the puzzle set within the time budget.

    Puzzles are tested in order (9x9 first, then 16x16, then 25x25).
    solve_fn signature: solve_fn(grid, grid_size, box_h, box_w) -> solved_grid or None

    Returns dict with overall stats plus per-tier breakdowns.
    """
    global _deadline
    results = []
    puzzles_solved = 0
    puzzles_attempted = 0
    t_start = time.time()
    _deadline = t_start + time_budget

    for p in puzzles:
        if time.time() >= _deadline:
            break

        puzzle = p["puzzle"]
        puzzle_id = p["id"]
        gs = p["grid_size"]
        bh = p["box_h"]
        bw = p["box_w"]

        t_puzzle_start = time.time()
        try:
            solution = solve_fn(copy.deepcopy(puzzle), gs, bh, bw)
        except SolverTimeout:
            results.append({
                "id": puzzle_id,
                "label": p.get("label", str(puzzle_id)),
                "grid_size": gs,
                "solved": False,
                "time": time.time() - t_puzzle_start,
                "error": "timeout",
            })
            puzzles_attempted += 1
            break
        except Exception as e:
            results.append({
                "id": puzzle_id,
                "label": p.get("label", str(puzzle_id)),
                "grid_size": gs,
                "solved": False,
                "time": time.time() - t_puzzle_start,
                "error": str(e),
            })
            puzzles_attempted += 1
            continue

        puzzle_time = time.time() - t_puzzle_start
        is_correct, msg = validate_solution(puzzle, solution, gs, bh, bw)

        results.append({
            "id": puzzle_id,
            "label": p.get("label", str(puzzle_id)),
            "grid_size": gs,
            "solved": is_correct,
            "time": puzzle_time,
            "error": None if is_correct else msg,
        })

        puzzles_attempted += 1
        if is_correct:
            puzzles_solved += 1

    _deadline = float("inf")
    total_time = time.time() - t_start
    avg_time = total_time / puzzles_solved if puzzles_solved > 0 else float("inf")
    solve_time_sum = sum(r["time"] for r in results if r["solved"])

    # Per-tier breakdown
    tier_results = {}
    for tier in TIERS:
        gs = tier["grid_size"]
        label = tier["label"]
        tier_r = [r for r in results if r["grid_size"] == gs]
        tier_solved = sum(1 for r in tier_r if r["solved"])
        tier_attempted = len(tier_r)
        tier_solve_time = sum(r["time"] for r in tier_r if r["solved"])
        tier_results[label] = {
            "puzzles_solved": tier_solved,
            "puzzles_attempted": tier_attempted,
            "total_puzzles": tier["num_puzzles"],
            "solve_time_sum": tier_solve_time,
            "avg_time_per_solved": tier_solve_time / tier_solved if tier_solved > 0 else float("inf"),
        }

    result = {
        "puzzles_solved": puzzles_solved,
        "puzzles_attempted": puzzles_attempted,
        "total_puzzles": len(puzzles),
        "total_time": total_time,
        "solve_time_sum": solve_time_sum,
        "avg_time_per_solved": avg_time,
        "solve_rate": puzzles_solved / puzzles_attempted if puzzles_attempted > 0 else 0.0,
        "results": results,
        "tier_results": tier_results,
    }
    result["score"] = compute_score(result, time_budget)
    return result


def compute_score(result, time_budget=TIME_BUDGET):
    """
    Unified score. Higher is better.

    score = puzzles_solved + speed_bonus

    The speed bonus is in [0, 1) and only matters as a tiebreaker:
        speed_bonus = 1 - (solve_time_sum / time_budget)

    Each solved puzzle = 1 point regardless of size.
    Total possible = 300 (100 per tier).
    """
    solved = result["puzzles_solved"]
    if solved == 0:
        return 0.0
    solve_time = result["solve_time_sum"]
    speed_bonus = max(0.0, 1.0 - solve_time / time_budget)
    return solved + speed_bonus


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Sudoku puzzles for autoresearch")
    args = parser.parse_args()

    print(f"Data directory: {DATA_DIR}")
    print()

    puzzles = generate_puzzles()

    print()
    for tier in TIERS:
        label = tier["label"]
        count = sum(1 for p in puzzles if p["grid_size"] == tier["grid_size"])
        print(f"  {label}: {count} puzzles")
    print(f"  Total: {len(puzzles)} puzzles")
    print()
    print("Done! Ready to solve.")
