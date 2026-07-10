"""7x7 Gomoku Board module
=========================
Board representation, move/undo, win detection.

Convention:
  EMPTY=0, BLACK=1, WHITE=2
  BLACK = AI (first move), WHITE = human (second move).
"""


class Board:
    """Gomoku board, default 7x7, 5-in-a-row to win."""

    EMPTY = 0
    BLACK = 1
    WHITE = 2

    def __init__(self, size=7, win_len=5):
        if win_len > size:
            raise ValueError(f"win_len({win_len}) must be <= size({size})")
        self.size = size
        self.win_len = win_len
        self.grid = [[self.EMPTY] * size for _ in range(size)]
        self._history = []  # [(row, col, player), ...]

    # ---- basic properties ----

    @property
    def move_count(self):
        return len(self._history)

    @property
    def last_move(self):
        """Last move as (row, col, player), or None if no moves."""
        return self._history[-1] if self._history else None

    @property
    def next_player(self):
        """Which player moves next."""
        return self.WHITE if self.move_count % 2 == 1 else self.BLACK

    # ---- coordinate helpers ----

    def in_bounds(self, row, col):
        return 0 <= row < self.size and 0 <= col < self.size

    def is_empty(self, row, col):
        return self.grid[row][col] == self.EMPTY

    def get_empty_cells(self):
        """Return list of all empty positions [(r,c), ...]."""
        return [
            (r, c)
            for r in range(self.size)
            for c in range(self.size)
            if self.grid[r][c] == self.EMPTY
        ]

    # ---- move / undo ----

    def make_move(self, row, col, player):
        """Place a piece. Caller must ensure the cell is empty."""
        self.grid[row][col] = player
        self._history.append((row, col, player))

    def undo_move(self):
        """Undo the last move."""
        if not self._history:
            return
        row, col, _ = self._history.pop()
        self.grid[row][col] = self.EMPTY

    # ---- win detection ----

    def check_winner(self):
        """Check if the last move created a win. Returns player or None."""
        if not self._history:
            return None
        row, col, player = self._history[-1]
        return self._check_at(row, col, player)

    def check_winner_global(self):
        """Full-board scan for win. Use when restoring from external state."""
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] != self.EMPTY:
                    result = self._check_at(r, c, self.grid[r][c])
                    if result is not None:
                        return result
        return None

    def _check_at(self, row, col, player):
        """Count consecutive pieces in 4 directions from (row, col)."""
        if player == self.EMPTY:
            return None
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        for dr, dc in directions:
            count = 1
            # positive direction
            r, c = row + dr, col + dc
            while self.in_bounds(r, c) and self.grid[r][c] == player:
                count += 1
                r += dr
                c += dc
            # negative direction
            r, c = row - dr, col - dc
            while self.in_bounds(r, c) and self.grid[r][c] == player:
                count += 1
                r -= dr
                c -= dc
            if count >= self.win_len:
                return player
        return None

    def is_full(self):
        return self.move_count >= self.size * self.size

    # ---- utilities ----

    def copy(self):
        """Deep copy."""
        new_board = Board(self.size, self.win_len)
        new_board.grid = [row[:] for row in self.grid]
        new_board._history = list(self._history)
        return new_board

    def from_grid(self, grid):
        """Restore board state from a 2D array (0=empty, 1=AI, 2=human)."""
        self.grid = [row[:] for row in grid]
        self._history = []
        blacks = []
        whites = []
        for r in range(self.size):
            for c in range(self.size):
                if self.grid[r][c] == self.BLACK:
                    blacks.append((r, c, self.BLACK))
                elif self.grid[r][c] == self.WHITE:
                    whites.append((r, c, self.WHITE))
        # interleave: black first
        for i in range(max(len(blacks), len(whites))):
            if i < len(blacks):
                self._history.append(blacks[i])
            if i < len(whites):
                self._history.append(whites[i])
        return self

    def __getitem__(self, key):
        return self.grid[key]

    def __str__(self):
        symbols = {self.EMPTY: ".", self.BLACK: "X", self.WHITE: "O"}
        lines = ["  " + " ".join(str(i) for i in range(self.size))]
        for r in range(self.size):
            row_str = (
                str(r)
                + " "
                + " ".join(symbols[self.grid[r][c]] for c in range(self.size))
            )
            lines.append(row_str)
        return "\n".join(lines)