"""
Autoresearch Sudoku solver.
Bitmask constraint propagation + backtracking with MRV heuristic.
Handles 9x9, 16x16, and 25x25 puzzles.

Usage: uv run train.py
"""

import time
import copy

from prepare import TIME_BUDGET, load_puzzles, evaluate_solver, check_deadline

# Per-puzzle timeout exception (caught inside solve, not by harness)
class _PuzzleTimeout(Exception):
    pass

# ---------------------------------------------------------------------------
# Per-size precomputed data cache
# ---------------------------------------------------------------------------

_cache = {}

def _get_data(grid_size, box_h, box_w):
    key = (grid_size, box_h, box_w)
    if key in _cache:
        return _cache[key]

    N = grid_size
    ALL_BITS = (1 << N) - 1

    # Peers for each flat cell index
    peers = [None] * (N * N)
    for r in range(N):
        for c in range(N):
            p = set()
            for i in range(N):
                if i != c:
                    p.add(r * N + i)
                if i != r:
                    p.add(i * N + c)
            br, bc = (r // box_h) * box_h, (c // box_w) * box_w
            for i in range(br, br + box_h):
                for j in range(bc, bc + box_w):
                    if (i, j) != (r, c):
                        p.add(i * N + j)
            peers[r * N + c] = tuple(p)

    # Units: all rows, columns, and boxes
    units = []
    for r in range(N):
        units.append(tuple(r * N + c for c in range(N)))
    for c in range(N):
        units.append(tuple(r * N + c for r in range(N)))
    for br in range(0, N, box_h):
        for bc in range(0, N, box_w):
            units.append(tuple((br + i) * N + (bc + j)
                               for i in range(box_h) for j in range(box_w)))

    data = (N, ALL_BITS, peers, units)
    _cache[key] = data
    return data

# ---------------------------------------------------------------------------
# Precomputed box-line intersection data cache
# ---------------------------------------------------------------------------
_bl_cache = {}

def _get_box_line_data(grid_size, box_h, box_w):
    key = (grid_size, box_h, box_w)
    if key in _bl_cache:
        return _bl_cache[key]
    N = grid_size
    _, _, _, units = _get_data(grid_size, box_h, box_w)
    # Row units: 0..N-1, Col units: N..2N-1, Box units: 2N..3N-1
    pairs = []
    for bi in range(2 * N, len(units)):
        box = set(units[bi])
        for li in range(2 * N):  # rows and columns
            line = set(units[li])
            inter = box & line
            if len(inter) >= 2:
                pairs.append((tuple(inter), tuple(box - inter), tuple(line - inter)))
    _bl_cache[key] = pairs
    return pairs

# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

def solve(grid, grid_size, box_h, box_w):
    N, ALL_BITS, PEERS, UNITS = _get_data(grid_size, box_h, box_w)
    BL_PAIRS = _get_box_line_data(grid_size, box_h, box_w)
    total = N * N

    # Per-puzzle timeout: 10s for 25x25, generous for smaller
    if grid_size >= 25:
        puzzle_deadline = time.time() + 10.0
    elif grid_size >= 16:
        puzzle_deadline = time.time() + 30.0
    else:
        puzzle_deadline = 0  # no per-puzzle limit for 9x9

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
        while True:
            # FAST PHASE: naked singles + hidden singles + naked pairs
            changed = True
            while changed:
                changed = False
                # Naked singles
                for idx in range(total):
                    c = cands[idx]
                    if c != 0 and c.bit_count() == 1:
                        val = (c & -c).bit_length()
                        if not assign(idx, val, vals, cands):
                            return False
                        changed = True

                # Hidden singles
                for unit in UNITS:
                    placed = 0
                    for idx in unit:
                        if vals[idx]:
                            placed |= 1 << (vals[idx] - 1)
                    need = ALL_BITS & ~placed
                    while need:
                        bit = need & (-need)
                        need &= need - 1
                        place = -1
                        count = 0
                        for idx in unit:
                            if cands[idx] & bit:
                                count += 1
                                place = idx
                                if count > 1:
                                    break
                        if count == 0:
                            return False
                        elif count == 1 and vals[place] == 0:
                            if not assign(place, bit.bit_length(), vals, cands):
                                return False
                            changed = True

                # Naked pairs + naked triples
                for unit in UNITS:
                    ulen = len(unit)
                    for i in range(ulen):
                        ci = cands[unit[i]]
                        if ci == 0:
                            continue
                        bc = ci.bit_count()
                        if bc == 2:
                            for j in range(i + 1, ulen):
                                if cands[unit[j]] == ci:
                                    for k in range(ulen):
                                        if k != i and k != j and cands[unit[k]] & ci:
                                            cands[unit[k]] &= ~ci
                                            if vals[unit[k]] == 0 and cands[unit[k]] == 0:
                                                return False
                                            if cands[unit[k]].bit_count() == 1:
                                                changed = True
                                    break
                        if bc == 2 or bc == 3:
                            for j in range(i + 1, ulen):
                                cj = cands[unit[j]]
                                if cj == 0:
                                    continue
                                combo = ci | cj
                                if combo.bit_count() > 3:
                                    continue
                                for m in range(j + 1, ulen):
                                    cm = cands[unit[m]]
                                    if cm == 0:
                                        continue
                                    triple = combo | cm
                                    if triple.bit_count() != 3:
                                        continue
                                    for k in range(ulen):
                                        if k != i and k != j and k != m and cands[unit[k]] & triple:
                                            cands[unit[k]] &= ~triple
                                            if vals[unit[k]] == 0 and cands[unit[k]] == 0:
                                                return False
                                            if cands[unit[k]].bit_count() == 1:
                                                changed = True

            # SLOW PHASE: hidden pairs + box-line reduction (only when fast phase exhausted)
            slow_changed = False

            # Hidden pairs
            for unit in UNITS:
                ulen = len(unit)
                placed = 0
                for k in range(ulen):
                    if vals[unit[k]]:
                        placed |= 1 << (vals[unit[k]] - 1)
                need = ALL_BITS & ~placed
                # Iterate over unplaced values
                need_list = []
                tmp = need
                while tmp:
                    b = tmp & (-tmp)
                    need_list.append(b)
                    tmp &= tmp - 1
                nl = len(need_list)
                for ai in range(nl):
                    bi = need_list[ai]
                    locs_i = 0
                    cnt_i = 0
                    for k in range(ulen):
                        if cands[unit[k]] & bi:
                            locs_i |= 1 << k
                            cnt_i += 1
                    if cnt_i != 2:
                        continue
                    for aj in range(ai + 1, nl):
                        bj = need_list[aj]
                        locs_j = 0
                        for k in range(ulen):
                            if cands[unit[k]] & bj:
                                locs_j |= 1 << k
                        if locs_j != locs_i:
                            continue
                        pair_bits = bi | bj
                        loc = locs_i
                        while loc:
                            lb = loc & (-loc)
                            k = lb.bit_length() - 1
                            loc &= loc - 1
                            if cands[unit[k]] & ~pair_bits:
                                cands[unit[k]] &= pair_bits
                                if cands[unit[k]] == 0:
                                    return False
                                slow_changed = True

            # Box-line reduction (pointing pairs / claiming)
            for inter, box_other, line_other in BL_PAIRS:
                for v in range(N):
                    bit = 1 << v
                    in_inter = False
                    for idx in inter:
                        if cands[idx] & bit:
                            in_inter = True
                            break
                    if not in_inter:
                        continue
                    in_box_other = False
                    for idx in box_other:
                        if cands[idx] & bit:
                            in_box_other = True
                            break
                    if not in_box_other:
                        for idx in line_other:
                            if cands[idx] & bit:
                                cands[idx] &= ~bit
                                if vals[idx] == 0 and cands[idx] == 0:
                                    return False
                                slow_changed = True
                    else:
                        in_line_other = False
                        for idx in line_other:
                            if cands[idx] & bit:
                                in_line_other = True
                                break
                        if not in_line_other:
                            for idx in box_other:
                                if cands[idx] & bit:
                                    cands[idx] &= ~bit
                                    if vals[idx] == 0 and cands[idx] == 0:
                                        return False
                                    slow_changed = True

            if not slow_changed:
                break
        return True

    _bt_count = [0]

    def backtrack(vals, cands):
        _bt_count[0] += 1
        if _bt_count[0] & 0xFF == 0:
            check_deadline()
            if puzzle_deadline and time.time() > puzzle_deadline:
                raise _PuzzleTimeout()

        if not propagate(vals, cands):
            return False

        # Find unfilled cell with minimum remaining values (MRV)
        best = -1
        best_count = N + 1
        for idx in range(total):
            c = cands[idx]
            if c != 0:
                pc = c.bit_count()
                if pc < best_count:
                    best_count = pc
                    best = idx
                    if pc == 2:
                        break

        if best == -1:
            return True  # all cells filled

        # Try each candidate value, ordered by LCV (least constraining first)
        c = cands[best]
        values = []
        while c:
            bit = c & (-c)
            val = bit.bit_length()
            c &= c - 1
            # Count peers that would lose this candidate
            cnt = 0
            peers_best = PEERS[best]
            for p in peers_best:
                if cands[p] & bit:
                    cnt += 1
            values.append((cnt, val))
        values.sort()

        for _, val in values:

            # Save state
            old_vals = vals[:]
            old_cands = cands[:]

            if assign(best, val, vals, cands) and backtrack(vals, cands):
                return True

            # Restore state
            vals[:] = old_vals
            cands[:] = old_cands

        return False

    try:
        if backtrack(vals, cands):
            for r in range(N):
                for c in range(N):
                    grid[r][c] = vals[r * N + c]
            return grid
    except _PuzzleTimeout:
        pass
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
        print(f"  Puzzle {r['label']:>12s}: {status} ({r['time']:.3f}s)" +
              (f" - {r['error']}" if r.get('error') else ""))

    # Per-tier summary
    print()
    print("--- Per-tier results ---")
    for tier_label, tr in results["tier_results"].items():
        print(f"  {tier_label:>5s}: {tr['puzzles_solved']:3d}/{tr['total_puzzles']} solved"
              f" ({tr['puzzles_attempted']:3d} attempted,"
              f" avg {tr['avg_time_per_solved']:.3f}s)")

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
