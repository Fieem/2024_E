"""7x7 Gomoku search engine.

Minimax + alpha-beta + iterative deepening.
Root-level evaluation ordering for maximal pruning.
Adjust depth limits for fast response on 7x7 boards.
"""

import time

from gomoku.board import Board
from gomoku.evaluate import evaluate

WIN_SCORE = 10_000_000

# Precomputed center-distance table
_DIST = [[abs(r - 3) + abs(c - 3) for c in range(7)] for r in range(7)]

# Depth limits tuned for Raspberry Pi 5: depth-4+ is Python-bound
_DEPTH = {"easy": 2, "medium": 3, "hard": 3}


def get_best_move(board, ai_player, difficulty="medium", time_limit_ms=5000):
    """Find best move using minimax search."""
    empty = board.get_empty_cells()
    if not empty:
        return None
    if len(empty) == 1:
        return empty[0]

    opponent = Board.WHITE if ai_player == Board.BLACK else Board.BLACK

    # --- Immediate win ---
    for r, c in empty:
        board.make_move(r, c, ai_player)
        if board.check_winner() == ai_player:
            board.undo_move()
            return (r, c)
        board.undo_move()

    # --- Immediate block ---
    for r, c in empty:
        board.make_move(r, c, opponent)
        if board.check_winner() == opponent:
            board.undo_move()
            return (r, c)
        board.undo_move()

    # --- Root-level ordering: evaluate all moves, sort by score ---
    root_scored = []
    for r, c in empty:
        board.make_move(r, c, ai_player)
        root_scored.append((evaluate(board, ai_player), r, c))
        board.undo_move()
    root_scored.sort(key=lambda x: -x[0])
    root_order = [(r, c) for _, r, c in root_scored]

    # --- Iterative deepening ---
    max_depth = _DEPTH.get(difficulty, 3)
    start = time.perf_counter()
    best_move = root_order[0]

    for depth in range(1, max_depth + 1):
        if (time.perf_counter() - start) * 1000 > time_limit_ms * 0.7:
            break
        score, move = _minimax(
            board, depth, -WIN_SCORE * 2, WIN_SCORE * 2,
            True, ai_player, opponent, start, time_limit_ms,
            root_order,
        )
        if move is not None:
            best_move = move
        if score >= WIN_SCORE - 100:
            break

    return best_move


def _minimax(board, depth, alpha, beta, is_maximizing,
             ai_player, opponent, start_time, time_limit_ms,
             root_order):
    """Recursive minimax. root_order used only at the top call level."""

    # Time check (every 512 nodes to reduce overhead)
    if time_limit_ms and start_time:
        if (time.perf_counter() - start_time) * 1000 > time_limit_ms:
            return 0, None

    winner = board.check_winner()
    if winner == ai_player:
        return WIN_SCORE + depth, None
    if winner is not None:
        return -WIN_SCORE - depth, None
    if board.is_full():
        return 0, None
    if depth == 0:
        return evaluate(board, ai_player), None

    current_player = ai_player if is_maximizing else opponent

    # Move generation with ordering
    if root_order is not None:
        grid = board.grid
        moves = [(r, c) for r, c in root_order if grid[r][c] == Board.EMPTY]
        root_order = None  # only use at this level
    else:
        moves = board.get_empty_cells()
        _order_fast(board, moves)

    if is_maximizing:
        best_score = -WIN_SCORE * 2
        best_move = moves[0]
        for move in moves:
            board.make_move(move[0], move[1], current_player)
            score, _ = _minimax(
                board, depth - 1, alpha, beta, False,
                ai_player, opponent, start_time, time_limit_ms, None,
            )
            board.undo_move()
            if score > best_score:
                best_score = score
                best_move = move
            if best_score > alpha:
                alpha = best_score
            if alpha >= beta:
                break
        return best_score, best_move
    else:
        best_score = WIN_SCORE * 2
        best_move = moves[0]
        for move in moves:
            board.make_move(move[0], move[1], current_player)
            score, _ = _minimax(
                board, depth - 1, alpha, beta, True,
                ai_player, opponent, start_time, time_limit_ms, None,
            )
            board.undo_move()
            if score < best_score:
                best_score = score
                best_move = move
            if best_score < beta:
                beta = best_score
            if alpha >= beta:
                break
        return best_score, best_move


def _order_fast(board, moves):
    """Sort moves in-place: adjacent-to-pieces first, then center."""
    grid = board.grid
    scored = []
    for r, c in moves:
        adj = 0
        for dr in (-1, 0, 1):
            nr = r + dr
            if nr < 0 or nr > 6:
                continue
            for nc in range(max(0, c - 1), min(6, c + 1) + 1):
                if grid[nr][nc]:
                    adj += 1
        scored.append((-adj, _DIST[r][c], r, c))
    scored.sort()
    moves[:] = [(x[2], x[3]) for x in scored]