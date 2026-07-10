"""7x7 Gomoku search engine.

Minimax with alpha-beta pruning, iterative deepening,
move ordering, and time management.
"""

import time

from gomoku.board import Board
from gomoku.evaluate import evaluate

# Sentinel values for terminal positions
WIN_SCORE = 10_000_000


def get_best_move(board, ai_player, difficulty="medium", time_limit_ms=5000):
    """Find the best move using iterative-deepening minimax.

    Args:
        board: Board instance.
        ai_player: Board.BLACK or Board.WHITE.
        difficulty: "easy" | "medium" | "hard".
        time_limit_ms: Max search time in milliseconds.

    Returns:
        (row, col) of the chosen move, or None if no move possible.
    """
    empty = board.get_empty_cells()
    if not empty:
        return None

    # Only one legal move
    if len(empty) == 1:
        return empty[0]

    opponent = Board.WHITE if ai_player == Board.BLACK else Board.BLACK

    # --- Immediate win: take it ---
    for r, c in empty:
        board.make_move(r, c, ai_player)
        win = board.check_winner() == ai_player
        board.undo_move()
        if win:
            return (r, c)

    # --- Immediate block: stop opponent from winning ---
    for r, c in empty:
        board.make_move(r, c, opponent)
        opp_win = board.check_winner() == opponent
        board.undo_move()
        if opp_win:
            return (r, c)

    # --- Iterative deepening ---
    depth_limits = {"easy": 2, "medium": 4, "hard": 6}
    max_depth = depth_limits.get(difficulty, 4)

    start = time.perf_counter()
    best_move = empty[0]  # fallback

    for depth in range(1, max_depth + 1):
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > time_limit_ms * 0.7:
            break

        alpha = -WIN_SCORE * 2
        beta = WIN_SCORE * 2

        score, move = _minimax(
            board,
            depth,
            alpha,
            beta,
            True,  # ai_player is maximizing
            ai_player,
            opponent,
            start,
            time_limit_ms,
        )

        if move is not None:
            best_move = move

        # Found a forced win: no need to search deeper
        if score >= WIN_SCORE - 100:
            break

    return best_move


def _minimax(board, depth, alpha, beta, is_maximizing,
             ai_player, opponent, start_time, time_limit_ms):
    """Recursive minimax with alpha-beta pruning.

    Returns (score, move). move may be None at leaf/depth-0 nodes.
    """

    # --- Time check (every node) ---
    if time_limit_ms and start_time:
        if (time.perf_counter() - start_time) * 1000 > time_limit_ms:
            return 0, None

    # --- Terminal: winner ---
    winner = board.check_winner()
    if winner == ai_player:
        return WIN_SCORE + depth, None  # prefer faster wins
    if winner is not None:  # opponent won
        return -WIN_SCORE - depth, None

    # --- Terminal: draw ---
    if board.is_full():
        return 0, None

    # --- Leaf: evaluate ---
    if depth == 0:
        return evaluate(board, ai_player), None

    # --- Generate and order moves ---
    moves = board.get_empty_cells()
    current_player = ai_player if is_maximizing else opponent
    _order_moves(board, moves, current_player)

    if is_maximizing:
        best_score = -WIN_SCORE * 2
        best_move = None
        for move in moves:
            board.make_move(move[0], move[1], current_player)
            score, _ = _minimax(
                board, depth - 1, alpha, beta, False,
                ai_player, opponent, start_time, time_limit_ms,
            )
            board.undo_move()

            if score > best_score:
                best_score = score
                best_move = move

            alpha = max(alpha, best_score)
            if alpha >= beta:
                break
        return best_score, best_move

    else:
        best_score = WIN_SCORE * 2
        best_move = None
        for move in moves:
            board.make_move(move[0], move[1], current_player)
            score, _ = _minimax(
                board, depth - 1, alpha, beta, True,
                ai_player, opponent, start_time, time_limit_ms,
            )
            board.undo_move()

            if score < best_score:
                best_score = score
                best_move = move

            beta = min(beta, best_score)
            if alpha >= beta:
                break
        return best_score, best_move


def _order_moves(board, moves, player):
    """Sort moves in-place for better alpha-beta pruning efficiency.

    Strategy:
      1. Center-adjacent positions first (positional heuristic).
      2. Near existing pieces (to extend patterns).
    """
    size = board.size
    center = size // 2

    # Pre-compute adjacency scores for all cells
    adj_score = _build_adjacency_map(board)

    def key(move):
        r, c = move
        # Manhattan distance from center (smaller = better)
        dist = abs(r - center) + abs(c - center)
        # Adjacent to existing pieces (higher = better)
        adj = adj_score[r][c]
        # Combine: primary sort by adjacency, secondary by center distance
        return (-adj, dist)

    moves.sort(key=key)


def _build_adjacency_map(board):
    """Build a 2D grid where each cell counts adjacent occupied cells."""
    size = board.size
    adj = [[0] * size for _ in range(size)]
    for r in range(size):
        for c in range(size):
            if board.grid[r][c] == Board.EMPTY:
                count = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if board.in_bounds(nr, nc) and board.grid[nr][nc] != Board.EMPTY:
                            count += 1
                adj[r][c] = count
    return adj