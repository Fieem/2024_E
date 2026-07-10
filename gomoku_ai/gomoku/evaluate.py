"""7x7 Gomoku pattern-based evaluation function.

Scans all 5-cell windows in 4 directions and scores
patterns of consecutive same-color pieces.
"""

from gomoku.board import Board

# Pattern scores for a 5-cell window containing only ONE color.
# Scales non-linearly: one 5 beats any number of 4s, etc.
PATTERN_SCORES = {
    5: 1000000,
    4: 100000,
    3: 5000,
    2: 200,
    1: 10,
}

# Center-position bonus matrix for 7x7 board.
# Encourages AI to control the center in the opening.
CENTER_WEIGHT_7 = [
    [0, 0, 0, 0, 0, 0, 0],
    [0, 2, 4, 6, 4, 2, 0],
    [0, 4, 8, 12, 8, 4, 0],
    [0, 6, 12, 20, 12, 6, 0],
    [0, 4, 8, 12, 8, 4, 0],
    [0, 2, 4, 6, 4, 2, 0],
    [0, 0, 0, 0, 0, 0, 0],
]

# Four scanning directions: horizontal, vertical, diagonal, anti-diagonal
DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]


def evaluate(board, ai_player):
    """Evaluate board position from ai_player perspective.

    Args:
        board: Board instance.
        ai_player: Board.BLACK or Board.WHITE.

    Returns:
        int: Score. Positive = good for AI, negative = good for opponent.
             +-1e7 means ai_player won/lost.
    """
    winner = board.check_winner_global()
    if winner == ai_player:
        return 10_000_000
    if winner is not None:
        return -10_000_000

    if board.is_full():
        return 0

    opponent = Board.WHITE if ai_player == Board.BLACK else Board.BLACK
    size = board.size
    win_len = board.win_len

    score = 0

    for dr, dc in DIRECTIONS:
        for r in range(size):
            for c in range(size):
                # Check if a win_len-cell window starting at (r,c) fits
                end_r = r + (win_len - 1) * dr
                end_c = c + (win_len - 1) * dc
                if not (0 <= end_r < size and 0 <= end_c < size):
                    continue

                ai_count = 0
                opp_count = 0
                for k in range(win_len):
                    cell = board.grid[r + k * dr][c + k * dc]
                    if cell == ai_player:
                        ai_count += 1
                    elif cell == opponent:
                        opp_count += 1

                # Mixed window: blocked for both sides, skip
                if ai_count > 0 and opp_count > 0:
                    continue

                if ai_count > 0:
                    score += PATTERN_SCORES[ai_count]
                elif opp_count > 0:
                    score -= PATTERN_SCORES[opp_count]

    # Add center-position bonus (weighted by ai_player pieces only)
    center_bonus = 0
    for r in range(size):
        for c in range(size):
            if board.grid[r][c] == ai_player:
                center_bonus += CENTER_WEIGHT_7[r][c]
    score += center_bonus * 3  # small multiplier so it doesn not dominate

    return score