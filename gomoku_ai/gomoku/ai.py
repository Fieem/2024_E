"""7x7 Gomoku AI -- unified interface.

Usage:
    from gomoku.ai import get_best_move

    # grid is a 7x7 list-of-lists: 0=empty, 1=AI, 2=human
    row, col = get_best_move(grid, ai_player=1, difficulty="medium")

    # Stateful interface (maintains board across turns):
    from gomoku.ai import GomokuAI
    ai = GomokuAI(difficulty="hard")
    ai.opponent_move(2, 3)           # register human move
    r, c = ai.get_move()             # get AI response
    ...                              # (robot places piece)
    ai.confirm_move()                # confirm placement
"""

from gomoku.board import Board
from gomoku.search import get_best_move as _search_best_move


# ---------------------------------------------------------------------------
# Functional interface (stateless)
# ---------------------------------------------------------------------------

def get_best_move(grid, ai_player=Board.BLACK, difficulty="medium",
                  time_limit_ms=5000):
    """Compute the best move given a board state.

    Args:
        grid: 7x7 nested list. 0=empty, 1=AI, 2=opponent.
        ai_player: 1 (Board.BLACK) or 2 (Board.WHITE).
        difficulty: "easy" | "medium" | "hard".
        time_limit_ms: max search time in ms.

    Returns:
        (row, col) tuple of the chosen move.
    """
    board = Board()
    board.from_grid(grid)
    return _search_best_move(board, ai_player, difficulty, time_limit_ms)


# ---------------------------------------------------------------------------
# Stateful interface
# ---------------------------------------------------------------------------

class GomokuAI:
    """Stateful Gomoku AI that maintains its own board.

    Typical usage in a game loop:
        ai = GomokuAI(difficulty="medium", ai_plays=Board.BLACK)

        # Human moves first? Or AI? Depends on ai_plays.
        if ai.is_ai_turn():
            r, c = ai.get_move()
            # ... robot places piece at (r,c) ...
            ai.confirm_move()

        while not ai.is_game_over():
            # Wait for human move (via vision system) ...
            human_r, human_c = vision_system.detect_move()
            ai.opponent_move(human_r, human_c)

            if ai.is_game_over():
                break

            r, c = ai.get_move()
            # ... robot places piece at (r,c) ...
            ai.confirm_move()
    """

    def __init__(self, difficulty="medium", ai_plays=Board.BLACK,
                 time_limit_ms=5000):
        self.board = Board()
        self.difficulty = difficulty
        self.ai_player = ai_plays
        self.opponent = Board.WHITE if ai_plays == Board.BLACK else Board.BLACK
        self.time_limit_ms = time_limit_ms
        self._pending_move = None   # move chosen but not yet confirmed

    # ---- turn management ----

    def is_ai_turn(self):
        """Should the AI move now?"""
        return self.board.next_player == self.ai_player

    def is_game_over(self):
        """Check if the game has ended."""
        return (self.board.check_winner() is not None or
                self.board.is_full())

    @property
    def winner(self):
        """Winner (Board.BLACK/Board.WHITE) or None."""
        return self.board.check_winner()

    # ---- move interface ----

    def opponent_move(self, row, col):
        """Register the opponent move (detected by vision)."""
        if not self.board.is_empty(row, col):
            raise ValueError(f"Cell ({row},{col}) is not empty")
        self.board.make_move(row, col, self.opponent)

    def get_move(self):
        """Compute and return the AI best move.

        The move is cached internally until confirm_move() is called.
        """
        move = _search_best_move(
            self.board, self.ai_player,
            self.difficulty, self.time_limit_ms,
        )
        self._pending_move = move
        return move

    def confirm_move(self):
        """Confirm the pending AI move (after robot has placed the piece)."""
        if self._pending_move is None:
            raise RuntimeError("No pending move. Call get_move() first.")
        self.board.make_move(self._pending_move[0], self._pending_move[1],
                             self.ai_player)
        self._pending_move = None

    def cancel_move(self):
        """Cancel the pending move (if something went wrong)."""
        self._pending_move = None

    # ---- utilities ----

    @property
    def grid(self):
        """Current board as 2D list (7x7)."""
        return self.board.grid

    def reset(self):
        """Reset the game."""
        self.board = Board()
        self._pending_move = None

    def __str__(self):
        return str(self.board)