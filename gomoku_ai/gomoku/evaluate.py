"""7x7 Gomoku fast evaluation.

Precomputes all 5-cell windows at module load.
No check_winner_global — minimax already handles terminal detection.
"""

from gomoku.board import Board

# ---- Pattern scores ----
_PATTERN = {5: 1000000, 4: 100000, 3: 5000, 2: 200, 1: 10}

# ---- Precompute all 5-cell windows ----
# Each window is a tuple of 5 (row, col) pairs
_WINDOWS = []  # list of [(r0,c0),(r1,c1),(r2,c2),(r3,c3),(r4,c4)]

_SIZE = 7
_WLEN = 5

# Horizontal
for r in range(_SIZE):
    for c in range(_SIZE - _WLEN + 1):
        _WINDOWS.append(tuple((r, c + k) for k in range(_WLEN)))

# Vertical
for c in range(_SIZE):
    for r in range(_SIZE - _WLEN + 1):
        _WINDOWS.append(tuple((r + k, c) for k in range(_WLEN)))

# Diagonal \
for r in range(_SIZE - _WLEN + 1):
    for c in range(_SIZE - _WLEN + 1):
        _WINDOWS.append(tuple((r + k, c + k) for k in range(_WLEN)))

# Anti-diagonal /
for r in range(_SIZE - _WLEN + 1):
    for c in range(_WLEN - 1, _SIZE):
        _WINDOWS.append(tuple((r + k, c - k) for k in range(_WLEN)))


def evaluate(board, ai_player):
    """Evaluate board from ai_player perspective.

    Returns positive score if AI is winning, negative if opponent.
    """
    opponent = Board.WHITE if ai_player == Board.BLACK else Board.BLACK
    grid = board.grid
    score = 0
    ps = _PATTERN

    for win in _WINDOWS:
        # Count pieces of each color in this 5-cell window
        ai_cnt = 0
        opp_cnt = 0
        for r, c in win:
            v = grid[r][c]
            if v == ai_player:
                ai_cnt += 1
            elif v == opponent:
                opp_cnt += 1

        # Mixed window: skip (blocked for both)
        if ai_cnt and opp_cnt:
            continue

        if ai_cnt:
            score += ps[ai_cnt]
        elif opp_cnt:
            score -= ps[opp_cnt]

    return score