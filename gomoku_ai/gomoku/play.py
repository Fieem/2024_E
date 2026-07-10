"""7x7 Gomoku -- Human vs AI interactive game.

Run:   python play.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gomoku.board import Board
from gomoku.ai import get_best_move


# ------------------------------------------------------------
# Board rendering (auto-detects Unicode support)
# ------------------------------------------------------------

_UNICODE_OK = None


def _check_unicode():
    global _UNICODE_OK
    if _UNICODE_OK is not None:
        return _UNICODE_OK
    try:
        # Probe: try to encode a box-drawing char for stdout
        "\u2500".encode(sys.stdout.encoding or "ascii")
        _UNICODE_OK = True
    except (UnicodeEncodeError, LookupError):
        _UNICODE_OK = False
    return _UNICODE_OK


def render(board, last_ai_move=None):
    """Draw the board, auto-selecting Unicode or ASCII."""
    if _check_unicode():
        _render_unicode(board, last_ai_move)
    else:
        _render_ascii(board, last_ai_move)


def _render_unicode(board, last_ai_move=None):
    """7x7 board with box-drawing characters."""
    size = board.size
    print()
    print("    0   1   2   3   4   5   6")
    # Top border
    top = "\u250c" + "\u2500\u2500\u2500\u252c" * 6 + "\u2500\u2500\u2500\u2510"
    print("  " + top)
    for r in range(size):
        cells = []
        for c in range(size):
            cell = board.grid[r][c]
            if cell == Board.BLACK:
                ch = "X"
            elif cell == Board.WHITE:
                ch = "O"
            else:
                ch = " "
            if last_ai_move and (r, c) == last_ai_move:
                ch = "(" + ch + ")"
            cells.append(" " + ch + " ")
        print(str(r) + " \u2502" + "\u2502".join(cells) + "\u2502")
        if r < size - 1:
            mid = "\u251c" + "\u2500\u2500\u2500\u253c" * 6 + "\u2500\u2500\u2500\u2524"
            print("  " + mid)
    # Bottom border
    bot = "\u2514" + "\u2500\u2500\u2500\u2534" * 6 + "\u2500\u2500\u2500\u2518"
    print("  " + bot)
    print()


def _render_ascii(board, last_ai_move=None):
    """Fallback pure-ASCII board."""
    size = board.size
    print()
    print("    0   1   2   3   4   5   6")
    for r in range(size):
        row_str = str(r) + "  "
        for c in range(size):
            cell = board.grid[r][c]
            if cell == Board.BLACK:
                ch = "X"
            elif cell == Board.WHITE:
                ch = "O"
            else:
                ch = "."
            if last_ai_move and (r, c) == last_ai_move:
                ch = "(" + ch + ")"
            row_str += " " + ch + "  "
        print(row_str)
    print()


# ------------------------------------------------------------
# Game logic
# ------------------------------------------------------------

def play():
    """Main game loop."""
    print("=" * 50)
    print("  7x7 Gomoku -- Human vs AI")
    print("=" * 50)

    # ---- Choose side ----
    print()
    print("Who goes first?")
    print("  1. You  (play as Black, 'X')")
    print("  2. AI   (you play as White, 'O')")
    choice = input("Choice [1/2] (default 1): ").strip()
    human_first = choice != "2"
    human_player = Board.BLACK if human_first else Board.WHITE
    ai_player = Board.WHITE if human_first else Board.BLACK

    # ---- Choose difficulty ----
    print()
    print("AI difficulty:")
    print("  1. Easy   (near-instant)")
    print("  2. Medium (default)")
    print("  3. Hard   (may take a few seconds)")
    diff_choice = input("Choice [1/2/3] (default 2): ").strip()
    difficulty = {"1": "easy", "2": "medium", "3": "hard"}.get(diff_choice, "medium")
    time_limit = {"easy": 1000, "medium": 3000, "hard": 8000}[difficulty]

    # ---- Init ----
    board = Board()
    last_ai = None
    human_symbol = "X (Black)" if human_first else "O (White)"

    print()
    print("You: " + human_symbol + "  |  AI: " + difficulty +
          "  |  First: " + ("You" if human_first else "AI"))
    print("Enter moves as 'row,col' (e.g. 3,3).  Type 'quit' to exit.")
    print()

    render(board)

    # ---- Game loop ----
    while True:
        # --- AI turn ---
        ai_should_play = (
            board.next_player == ai_player
            and not board.is_full()
            and board.check_winner() is None
        )
        if ai_should_play:
            print("AI is thinking...", end="", flush=True)
            move = get_best_move(
                board.grid, ai_player=ai_player,
                difficulty=difficulty, time_limit_ms=time_limit,
            )
            if move is None:
                print(" no moves available!")
                break
            board.make_move(move[0], move[1], ai_player)
            last_ai = move
            print(" played (" + str(move[0]) + "," + str(move[1]) + ")")
            render(board, last_ai)

            if board.check_winner() == ai_player:
                print("AI wins!")
                break
            if board.is_full():
                print("Draw!")
                break

        # --- Human turn ---
        human_should_play = (
            board.next_player == human_player
            and not board.is_full()
            and board.check_winner() is None
        )
        if not human_should_play:
            break

        while True:
            inp = input("Your move (row,col): ").strip()
            if inp.lower() in ("quit", "exit", "q"):
                print("Bye.")
                return
            try:
                parts = inp.replace(" ", "").split(",")
                if len(parts) != 2:
                    raise ValueError
                r, c = int(parts[0]), int(parts[1])
                if not board.in_bounds(r, c):
                    print("  Out of bounds. Row/col must be 0-" +
                          str(board.size - 1) + ".")
                    continue
                if not board.is_empty(r, c):
                    print("  That cell is already occupied.")
                    continue
                break
            except (ValueError, IndexError):
                print("  Invalid format. Use 'row,col' (e.g. 3,3).")
                continue

        board.make_move(r, c, human_player)
        render(board)

        if board.check_winner() == human_player:
            print("You win!")
            break
        if board.is_full():
            print("Draw!")
            break


if __name__ == "__main__":
    play()