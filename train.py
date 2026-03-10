"""
Autoresearch Sudoku solver.
Bitmask constraint propagation + backtracking with MRV heuristic.

Usage: uv run train.py
"""

import time
import copy

from prepare import TIME_BUDGET, GRID_SIZE, BOX_H, BOX_W, load_puzzles, evaluate_solver, check_deadline

# ---------------------------------------------------------------------------
# Precompute peer indices and unit indices using flat arrays
# ---------------------------------------------------------------------------

_N = GRID_SIZE
_ALL_BITS = (1 << _N) - 1  # 0xFFFF for 16 values: bits 0-15 represent values 1-16

# Popcount table for 16-bit values
_POPCOUNT = [0] * (1 << _N)
for _i in range(1, 1 << _N):
    _POPCOUNT[_i] = _POPCOUNT[_i >> 1] + (_i & 1)

# Lowest set bit value (1-indexed): _LSB_VAL[mask] gives the value (1-16) of the lowest set bit
_LSB_VAL = [0] * (1 << _N)
for _i in range(1, 1 << _N):
    _LSB_VAL[_i] = (_i & -_i).bit_length()

# Flat index: cell (r, c) -> r * N + c
# Peers for each flat cell index
_PEERS_FLAT = [None] * (_N * _N)
for _r in range(_N):
    for _c in range(_N):
        peers = set()
        for i in range(_N):
            if i != _c:
                peers.add(_r * _N + i)
            if i != _r:
                peers.add(i * _N + _c)
        br, bc = (_r // BOX_H) * BOX_H, (_c // BOX_W) * BOX_W
        for i in range(br, br + BOX_H):
            for j in range(bc, bc + BOX_W):
                if (i, j) != (_r, _c):
                    peers.add(i * _N + j)
        _PEERS_FLAT[_r * _N + _c] = tuple(peers)

# Units: all rows, columns, and boxes as tuples of flat indices
_ALL_UNITS = []
for _r in range(_N):
    _ALL_UNITS.append(tuple(_r * _N + _c for _c in range(_N)))
for _c in range(_N):
    _ALL_UNITS.append(tuple(_r * _N + _c for _r in range(_N)))
for _br in range(0, _N, BOX_H):
    for _bc in range(0, _N, BOX_W):
        _ALL_UNITS.append(tuple((_br + i) * _N + (_bc + j)
                                for i in range(BOX_H) for j in range(BOX_W)))

# For each cell, the 3 units it belongs to
_CELL_UNITS = [[] for _ in range(_N * _N)]
for _ui, _unit in enumerate(_ALL_UNITS):
    for _idx in _unit:
        _CELL_UNITS[_idx].append(_ui)

# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def solve(grid):
    N = _N
    total = N * N
    PEERS = _PEERS_FLAT
    UNITS = _ALL_UNITS
    POPCOUNT = _POPCOUNT
    LSB_VAL = _LSB_VAL
    ALL_BITS = _ALL_BITS

    # Flat arrays for grid values and candidate bitmasks
    vals = [0] * total
    cands = [0] * total
    for r in range(N):
        for c in range(N):
            idx = r * N + c
            v = grid[r][c]
            if v != 0:
                vals[idx] = v
                cands[idx] = 0
            else:
                vals[idx] = 0
                cands[idx] = ALL_BITS

    # Initial elimination from clues
    for idx in range(total):
        if vals[idx] != 0:
            bit = 1 << (vals[idx] - 1)
            for p in PEERS[idx]:
                cands[p] &= ~bit
    
    # Check for contradictions
    for idx in range(total):
        if vals[idx] == 0 and cands[idx] == 0:
            return None

    def assign(idx, val, vals, cands):
        """Assign val to cell idx, propagate. Returns False on contradiction."""
        bit = 1 << (val - 1)
        vals[idx] = val
        cands[idx] = 0
        for p in PEERS[idx]:
            if cands[p] & bit:
                cands[p] &= ~bit
                if vals[p] == 0 and cands[p] == 0:
                    return False
        return True

    def propagate(vals, cands):
        """Iterative constraint propagation. Returns False on contradiction."""
        changed = True
        while changed:
            changed = False
            # Naked singles
            for idx in range(total):
                c = cands[idx]
                if c != 0 and POPCOUNT[c] == 1:
                    val = LSB_VAL[c]
                    if not assign(idx, val, vals, cands):
                        return False
                    changed = True

            # Hidden singles
            for unit in UNITS:
                for v in range(N):
                    bit = 1 << v
                    place = -1
                    count = 0
                    for idx in unit:
                        if cands[idx] & bit:
                            count += 1
                            place = idx
                            if count > 1:
                                break
                    if count == 0:
                        found = False
                        for idx in unit:
                            if vals[idx] == v + 1:
                                found = True
                                break
                        if not found:
                            return False
                    elif count == 1:
                        if vals[place] == 0:
                            if not assign(place, v + 1, vals, cands):
                                return False
                            changed = True

            # Naked pairs: if two cells in a unit have exact same 2 candidates,
            # eliminate those candidates from all other cells in the unit
            for unit in UNITS:
                for i in range(len(unit)):
                    ci = cands[unit[i]]
                    if POPCOUNT[ci] != 2:
                        continue
                    for j in range(i + 1, len(unit)):
                        if cands[unit[j]] == ci:
                            # Found naked pair — eliminate from rest of unit
                            for k in range(len(unit)):
                                if k != i and k != j and cands[unit[k]] & ci:
                                    cands[unit[k]] &= ~ci
                                    if vals[unit[k]] == 0 and cands[unit[k]] == 0:
                                        return False
                                    if POPCOUNT[cands[unit[k]]] == 1:
                                        changed = True
                            break
        return True

    def backtrack(vals, cands):
        check_deadline()

        if not propagate(vals, cands):
            return False

        # Find unfilled cell with minimum remaining values (MRV)
        best = -1
        best_count = N + 1
        for idx in range(total):
            c = cands[idx]
            if c != 0:
                pc = POPCOUNT[c]
                if pc < best_count:
                    best_count = pc
                    best = idx
                    if pc == 2:
                        break

        if best == -1:
            return True  # all cells filled

        # Try each candidate value
        c = cands[best]
        while c:
            bit = c & (-c)
            val = bit.bit_length()
            c &= c - 1

            # Save state
            old_vals = vals[:]
            old_cands = cands[:]

            if assign(best, val, vals, cands) and backtrack(vals, cands):
                return True

            # Restore state
            vals[:] = old_vals
            cands[:] = old_cands

        return False

    if backtrack(vals, cands):
        for r in range(N):
            for c in range(N):
                grid[r][c] = vals[r * N + c]
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
