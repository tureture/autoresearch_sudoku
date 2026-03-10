"""
Autoresearch Sudoku solver.
Constraint propagation + backtracking with MRV heuristic.

Usage: uv run train.py
"""

import time
import copy

from prepare import TIME_BUDGET, GRID_SIZE, BOX_H, BOX_W, load_puzzles, evaluate_solver, check_deadline

# ---------------------------------------------------------------------------
# Precompute peer groups for each cell
# ---------------------------------------------------------------------------

_ALL_VALUES = frozenset(range(1, GRID_SIZE + 1))

# For each cell (r, c), list of peer cells (same row, col, or box, excluding self)
_PEERS = [[None] * GRID_SIZE for _ in range(GRID_SIZE)]
for _r in range(GRID_SIZE):
    for _c in range(GRID_SIZE):
        peers = set()
        for i in range(GRID_SIZE):
            if i != _c:
                peers.add((_r, i))
            if i != _r:
                peers.add((i, _c))
        br, bc = (_r // BOX_H) * BOX_H, (_c // BOX_W) * BOX_W
        for i in range(br, br + BOX_H):
            for j in range(bc, bc + BOX_W):
                if (i, j) != (_r, _c):
                    peers.add((i, j))
        _PEERS[_r][_c] = tuple(peers)

# For each cell, list of (unit_type, unit_cells) where unit_cells excludes self
_UNITS = [[None] * GRID_SIZE for _ in range(GRID_SIZE)]
for _r in range(GRID_SIZE):
    for _c in range(GRID_SIZE):
        units = []
        # Row unit
        units.append(tuple((_r, i) for i in range(GRID_SIZE) if i != _c))
        # Col unit
        units.append(tuple((i, _c) for i in range(GRID_SIZE) if i != _r))
        # Box unit
        br, bc = (_r // BOX_H) * BOX_H, (_c // BOX_W) * BOX_W
        units.append(tuple((i, j) for i in range(br, br + BOX_H)
                           for j in range(bc, bc + BOX_W) if (i, j) != (_r, _c)))
        _UNITS[_r][_c] = units

# ---------------------------------------------------------------------------
# Solver: constraint propagation + backtracking with MRV
# ---------------------------------------------------------------------------

def solve(grid):
    # Initialize candidates: sets of possible values for each cell
    candidates = [[None] * GRID_SIZE for _ in range(GRID_SIZE)]
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if grid[r][c] != 0:
                candidates[r][c] = None  # already filled
            else:
                candidates[r][c] = set(_ALL_VALUES)

    # Eliminate values based on initial clues
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if grid[r][c] != 0:
                val = grid[r][c]
                for pr, pc in _PEERS[r][c]:
                    if candidates[pr][pc] is not None:
                        candidates[pr][pc].discard(val)

    # Check for any empty candidates (unsolvable)
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if candidates[r][c] is not None and len(candidates[r][c]) == 0:
                return None

    def propagate():
        """Run constraint propagation until no more progress. Returns False if contradiction."""
        changed = True
        while changed:
            changed = False
            # Naked singles: cells with exactly one candidate
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    cands = candidates[r][c]
                    if cands is not None and len(cands) == 1:
                        val = next(iter(cands))
                        grid[r][c] = val
                        candidates[r][c] = None
                        changed = True
                        for pr, pc in _PEERS[r][c]:
                            peer_cands = candidates[pr][pc]
                            if peer_cands is not None:
                                if val in peer_cands:
                                    peer_cands.discard(val)
                                    if len(peer_cands) == 0:
                                        return False

            # Hidden singles: value that can only go in one place in a unit
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if candidates[r][c] is None:
                        continue
                    for unit in _UNITS[r][c]:
                        for val in list(candidates[r][c]):
                            # Check if val can go elsewhere in this unit
                            found_elsewhere = False
                            for ur, uc in unit:
                                if candidates[ur][uc] is not None and val in candidates[ur][uc]:
                                    found_elsewhere = True
                                    break
                            if not found_elsewhere:
                                # val must go here
                                candidates[r][c] = {val}
                                changed = True
                                break
                        if candidates[r][c] is not None and len(candidates[r][c]) == 1:
                            break
        return True

    def backtrack():
        check_deadline()

        if not propagate():
            return False

        # Find unfilled cell with minimum remaining values (MRV)
        best = None
        best_count = GRID_SIZE + 1
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                cands = candidates[r][c]
                if cands is not None:
                    if len(cands) < best_count:
                        best_count = len(cands)
                        best = (r, c)
                        if best_count == 1:
                            break
            if best_count == 1:
                break

        if best is None:
            return True  # all cells filled

        r, c = best
        for val in list(candidates[r][c]):
            # Save state
            old_grid = [row[:] for row in grid]
            old_cands = [[cell.copy() if cell is not None else None for cell in row] for row in candidates]

            # Place value
            grid[r][c] = val
            candidates[r][c] = None
            # Eliminate from peers
            contradiction = False
            for pr, pc in _PEERS[r][c]:
                peer_cands = candidates[pr][pc]
                if peer_cands is not None and val in peer_cands:
                    peer_cands.discard(val)
                    if len(peer_cands) == 0:
                        contradiction = True
                        break

            if not contradiction and backtrack():
                return True

            # Restore state
            for i in range(GRID_SIZE):
                for j in range(GRID_SIZE):
                    grid[i][j] = old_grid[i][j]
                    candidates[i][j] = old_cands[i][j]

        return False

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
