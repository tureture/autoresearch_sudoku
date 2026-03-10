"""
One-time puzzle preparation and evaluation harness for autoresearch sudoku experiments.
Generates a fixed set of 16x16 Sudoku puzzles and provides the scoring function.

Usage:
    python prepare.py                  # generate puzzles
    python prepare.py --num-puzzles 50 # generate 50 puzzles

Puzzles are stored in data/ inside the repo.
"""

import os
import json
import copy
import time
import random
import argparse

# ---------------------------------------------------------------------------
# Constants (fixed, do not modify)
# ---------------------------------------------------------------------------

TIME_BUDGET = 300       # solver time budget in seconds (5 minutes)
GRID_SIZE = 16           # 16x16 Sudoku
BOX_H = 4               # box height
BOX_W = 4               # box width
NUM_PUZZLES = 10        # number of evaluation puzzles

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PUZZLES_FILE = os.path.join(DATA_DIR, "puzzles.json")
SEED = 42

# ---------------------------------------------------------------------------
# 16x16 Sudoku puzzle generator
# ---------------------------------------------------------------------------

def _is_valid_placement(grid, row, col, num):
    """Check if placing num at (row, col) is valid."""
    size = len(grid)
    if num in grid[row]:
        return False
    if any(grid[r][col] == num for r in range(size)):
        return False
    box_r, box_c = (row // BOX_H) * BOX_H, (col // BOX_W) * BOX_W
    for r in range(box_r, box_r + BOX_H):
        for c in range(box_c, box_c + BOX_W):
            if grid[r][c] == num:
                return False
    return True


def _solve_for_generation(grid):
    """Solve a grid in-place using backtracking. Returns True if solved."""
    size = len(grid)
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 0:
                nums = list(range(1, size + 1))
                random.shuffle(nums)
                for num in nums:
                    if _is_valid_placement(grid, r, c, num):
                        grid[r][c] = num
                        if _solve_for_generation(grid):
                            return True
                        grid[r][c] = 0
                return False
    return True


def _generate_full_grid(rng_seed):
    """Generate a complete valid 16x16 Sudoku grid."""
    random.seed(rng_seed)
    grid = [[0] * GRID_SIZE for _ in range(GRID_SIZE)]
    _solve_for_generation(grid)
    return grid


def _create_puzzle(full_grid, num_clues, rng_seed):
    """Remove cells from a full grid to create a puzzle with num_clues given."""
    random.seed(rng_seed)
    puzzle = copy.deepcopy(full_grid)
    total_cells = GRID_SIZE * GRID_SIZE
    cells_to_remove = total_cells - num_clues
    positions = [(r, c) for r in range(GRID_SIZE) for c in range(GRID_SIZE)]
    random.shuffle(positions)
    removed = 0
    for r, c in positions:
        if removed >= cells_to_remove:
            break
        puzzle[r][c] = 0
        removed += 1
    return puzzle


def _current_config():
    """Return the config dict that gets embedded in puzzles.json."""
    return {
        "grid_size": GRID_SIZE,
        "box_h": BOX_H,
        "box_w": BOX_W,
        "num_puzzles": NUM_PUZZLES,
        "seed": SEED,
    }


def generate_puzzles(num_puzzles=NUM_PUZZLES, seed=SEED):
    """Generate a set of Sudoku puzzles with varying difficulty."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(PUZZLES_FILE):
        with open(PUZZLES_FILE, "r") as f:
            data = json.load(f)
        saved_config = data.get("config", {})
        if saved_config == _current_config():
            print(f"Puzzles: already generated at {PUZZLES_FILE}")
            return data["puzzles"]
        print("Config changed, regenerating puzzles...")

    print(f"Generating {num_puzzles} {GRID_SIZE}x{GRID_SIZE} Sudoku puzzles...")
    puzzles = []

    for i in range(num_puzzles):
        # Vary difficulty: 80-120 clues out of 256 cells
        clues = 80 + (i * 40 // num_puzzles)
        grid_seed = seed + i * 1000
        puzzle_seed = seed + i * 1000 + 500

        full_grid = _generate_full_grid(grid_seed)
        puzzle = _create_puzzle(full_grid, clues, puzzle_seed)

        puzzles.append({
            "id": i,
            "clues": clues,
            "puzzle": puzzle,
            "solution": full_grid,
        })

        if (i + 1) % 10 == 0:
            print(f"  Generated {i + 1}/{num_puzzles} puzzles")

    data = {"config": _current_config(), "puzzles": puzzles}
    with open(PUZZLES_FILE, "w") as f:
        json.dump(data, f)

    print(f"Puzzles: saved {num_puzzles} puzzles to {PUZZLES_FILE}")
    return puzzles


def load_puzzles():
    """Load puzzles from disk."""
    with open(PUZZLES_FILE, "r") as f:
        data = json.load(f)
    saved_config = data.get("config", {})
    if saved_config != _current_config():
        print("Config changed since last generation, regenerating...")
        return generate_puzzles()
    return data["puzzles"]

# ---------------------------------------------------------------------------
# Evaluation (DO NOT CHANGE — this is the fixed metric)
# ---------------------------------------------------------------------------

def validate_solution(puzzle, solution, expected_solution):
    """
    Validate a proposed solution against the puzzle and expected solution.
    Returns (is_correct, error_message).
    """
    if solution is None:
        return False, "No solution returned"

    if len(solution) != GRID_SIZE:
        return False, f"Wrong number of rows: {len(solution)}"
    for r in range(GRID_SIZE):
        if len(solution[r]) != GRID_SIZE:
            return False, f"Wrong number of columns in row {r}: {len(solution[r])}"

    # Check that all original clues are preserved
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if puzzle[r][c] != 0 and solution[r][c] != puzzle[r][c]:
                return False, f"Clue at ({r},{c}) was changed: {puzzle[r][c]} -> {solution[r][c]}"

    # Check all values are in [1, GRID_SIZE]
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if not (1 <= solution[r][c] <= GRID_SIZE):
                return False, f"Invalid value at ({r},{c}): {solution[r][c]}"

    # Check rows
    for r in range(GRID_SIZE):
        if len(set(solution[r])) != GRID_SIZE:
            return False, f"Duplicate in row {r}"

    # Check columns
    for c in range(GRID_SIZE):
        col = [solution[r][c] for r in range(GRID_SIZE)]
        if len(set(col)) != GRID_SIZE:
            return False, f"Duplicate in column {c}"

    # Check boxes
    for box_r in range(0, GRID_SIZE, BOX_H):
        for box_c in range(0, GRID_SIZE, BOX_W):
            box = []
            for r in range(box_r, box_r + BOX_H):
                for c in range(box_c, box_c + BOX_W):
                    box.append(solution[r][c])
            if len(set(box)) != GRID_SIZE:
                return False, f"Duplicate in box starting at ({box_r},{box_c})"

    return True, "OK"


# ---------------------------------------------------------------------------
# Cooperative timeout mechanism
# ---------------------------------------------------------------------------

class SolverTimeout(Exception):
    """Raised by check_deadline() when the time budget is exhausted."""
    pass

_deadline = float("inf")  # absolute time.time() deadline

def check_deadline():
    """
    Call this periodically inside your solver. Raises SolverTimeout if
    the time budget has been exceeded. Cheap to call (just a clock read).
    """
    if time.time() >= _deadline:
        raise SolverTimeout("time budget exceeded")


def evaluate_solver(solve_fn, puzzles, time_budget=TIME_BUDGET):
    """
    Evaluate a solver function on the puzzle set within the time budget.
    Puzzles are solved sequentially. Before each puzzle, a global deadline
    is set so the solver can call check_deadline() to cooperatively abort
    when time runs out.

    Args:
        solve_fn: function(puzzle) -> solution_grid or None
        puzzles: list of puzzle dicts from load_puzzles()
        time_budget: max seconds for the entire evaluation

    Returns dict with:
        - puzzles_solved: number of correctly solved puzzles
        - puzzles_attempted: number of puzzles attempted
        - total_time: total wall clock time used
        - avg_time_per_solved: average time per solved puzzle
        - solve_rate: fraction of attempted puzzles solved correctly
        - results: list of per-puzzle results
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
        expected = p["solution"]
        puzzle_id = p["id"]

        t_puzzle_start = time.time()
        try:
            solution = solve_fn(copy.deepcopy(puzzle))
        except SolverTimeout:
            results.append({
                "id": puzzle_id,
                "solved": False,
                "time": time.time() - t_puzzle_start,
                "error": "timeout",
            })
            puzzles_attempted += 1
            break  # no time left, stop entirely
        except Exception as e:
            results.append({
                "id": puzzle_id,
                "solved": False,
                "time": time.time() - t_puzzle_start,
                "error": str(e),
            })
            puzzles_attempted += 1
            continue

        puzzle_time = time.time() - t_puzzle_start
        is_correct, msg = validate_solution(puzzle, solution, expected)

        results.append({
            "id": puzzle_id,
            "solved": is_correct,
            "time": puzzle_time,
            "error": None if is_correct else msg,
        })

        puzzles_attempted += 1
        if is_correct:
            puzzles_solved += 1

    _deadline = float("inf")  # reset after evaluation
    total_time = time.time() - t_start
    avg_time = total_time / puzzles_solved if puzzles_solved > 0 else float("inf")
    # Sum of solve times for correctly solved puzzles only
    solve_time_sum = sum(r["time"] for r in results if r["solved"])

    result = {
        "puzzles_solved": puzzles_solved,
        "puzzles_attempted": puzzles_attempted,
        "total_puzzles": len(puzzles),
        "total_time": total_time,
        "solve_time_sum": solve_time_sum,
        "avg_time_per_solved": avg_time,
        "solve_rate": puzzles_solved / puzzles_attempted if puzzles_attempted > 0 else 0.0,
        "results": results,
    }
    result["score"] = compute_score(result, time_budget)
    return result


def compute_score(result, time_budget=TIME_BUDGET):
    """
    Unified score for optimization. Higher is better.

    score = puzzles_solved + speed_bonus

    The speed bonus is in [0, 1) and only matters as a tiebreaker:
        speed_bonus = 1 - (solve_time_sum / time_budget)
    where solve_time_sum is the total time spent on correctly solved
    puzzles only. Unsolved or incorrect puzzles do not contribute.

    This means:
    - Each correctly solved puzzle contributes exactly 1 point.
    - When two solvers solve the same number of puzzles, the faster
      one scores higher.
    - A solver that solves N+1 puzzles always beats one that solves N,
      regardless of speed.
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
    parser = argparse.ArgumentParser(description="Generate 16x16 Sudoku puzzles for autoresearch")
    parser.add_argument("--num-puzzles", type=int, default=NUM_PUZZLES, help="Number of puzzles to generate")
    args = parser.parse_args()

    print(f"Data directory: {DATA_DIR}")
    print()

    puzzles = generate_puzzles(num_puzzles=args.num_puzzles)
    print()
    print(f"Done! Generated {len(puzzles)} puzzles. Ready to solve.")
