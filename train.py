"""
Autoresearch Sudoku solver. Brute-force baseline.
Solves 16x16 Sudoku puzzles using simple backtracking.

Usage: uv run train.py
"""

import time
import copy

from prepare import TIME_BUDGET, GRID_SIZE, BOX_H, BOX_W, load_puzzles, evaluate_solver, check_deadline

# ---------------------------------------------------------------------------
# Brute-force backtracking solver (edit this to optimize)
# ---------------------------------------------------------------------------

def solve(grid):
    """
    Solve a 16x16 Sudoku grid in-place using brute-force backtracking.
    Returns the solved grid, or None if unsolvable.
    """
    size = GRID_SIZE

    def is_valid(row, col, num):
        # Check row
        if num in grid[row]:
            return False
        # Check column
        for r in range(size):
            if grid[r][col] == num:
                return False
        # Check box
        box_r, box_c = (row // BOX_H) * BOX_H, (col // BOX_W) * BOX_W
        for r in range(box_r, box_r + BOX_H):
            for c in range(box_c, box_c + BOX_W):
                if grid[r][c] == num:
                    return False
        return True

    def backtrack():
        for r in range(size):
            for c in range(size):
                if grid[r][c] == 0:
                    check_deadline()
                    for num in range(1, size + 1):
                        if is_valid(r, c, num):
                            grid[r][c] = num
                            if backtrack():
                                return True
                            grid[r][c] = 0
                    return False
        return True

    if backtrack():
        return grid
    return None

# ---------------------------------------------------------------------------
# Main: run solver on puzzle set and report results
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    t_start = time.time()

    print("Loading puzzles...")
    puzzles = load_puzzles()
    print(f"Loaded {len(puzzles)} puzzles")
    print(f"Time budget: {TIME_BUDGET}s")
    print()

    print("Solving...")
    results = evaluate_solver(solve, puzzles, time_budget=TIME_BUDGET)

    # Per-puzzle details
    print()
    for r in results["results"]:
        status = "SOLVED" if r["solved"] else "FAILED"
        print(f"  Puzzle {r['id']:3d}: {status} ({r['time']:.3f}s)" +
              (f" - {r['error']}" if r.get('error') else ""))

    # Final summary
    t_end = time.time()
    print()
    print("---")
    print(f"score:             {results['score']:.6f}")
    print(f"puzzles_solved:    {results['puzzles_solved']}")
    print(f"puzzles_attempted: {results['puzzles_attempted']}")
    print(f"total_puzzles:     {results['total_puzzles']}")
    print(f"solve_rate:        {results['solve_rate']:.4f}")
    print(f"total_time:        {results['total_time']:.1f}")
    print(f"solve_time_sum:    {results['solve_time_sum']:.3f}")
    print(f"avg_time_per_solve: {results['avg_time_per_solved']:.3f}")
    print(f"wall_clock:        {t_end - t_start:.1f}")
