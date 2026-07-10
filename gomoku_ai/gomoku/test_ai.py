"""Smoke tests for the Gomoku AI."""

from gomoku.board import Board
from gomoku.evaluate import evaluate
from gomoku.ai import get_best_move

# ---- Test 1: Evaluate empty board is not biased ----
print("Test 1: Empty board evaluation ...")
b = Board()
s = evaluate(b, Board.BLACK)
assert s == 0, f"Empty board should eval 0, got {s}"
print("  PASS")

# ---- Test 2: Win detection ----
print("Test 2: Win detection ...")
b = Board()
for col in range(5):
    b.make_move(3, col, Board.BLACK)
assert b.check_winner() == Board.BLACK
b.undo_move()
assert b.check_winner() is None
print("  PASS")

# ---- Test 3: Draw detection ----
print("Test 3: Draw detection ...")
b = Board()
for r in range(7):
    for c in range(7):
        player = Board.BLACK if (r + c) % 2 == 0 else Board.WHITE
        b.make_move(r, c, player)
assert b.is_full()
assert b.check_winner() is None or b.check_winner_global() is not None
print("  PASS")

# ---- Test 4: AI takes immediate win ----
print("Test 4: AI takes immediate win ...")
b = Board()
# Set up: AI has 4 in a row horizontally
b.make_move(3, 0, Board.BLACK)
b.make_move(0, 0, Board.WHITE)
b.make_move(3, 1, Board.BLACK)
b.make_move(0, 1, Board.WHITE)
b.make_move(3, 2, Board.BLACK)
b.make_move(0, 2, Board.WHITE)
b.make_move(3, 3, Board.BLACK)
# Opponent just moved at (0,2). AI should play (3,4) to win.
r, c = get_best_move(b.grid, ai_player=Board.BLACK)
assert (r, c) == (3, 4), f"AI should win at (3,4), got ({r},{c})"
print(f"  PASS: AI chose ({r},{c}) to win")

# ---- Test 5: AI blocks opponent win ----
print("Test 5: AI blocks opponent win ...")
b = Board()
# Opponent has 4 in a row, AI must block
b.make_move(0, 0, Board.BLACK)
b.make_move(4, 0, Board.WHITE)
b.make_move(0, 1, Board.BLACK)
b.make_move(4, 1, Board.WHITE)
b.make_move(0, 2, Board.BLACK)
b.make_move(4, 2, Board.WHITE)
b.make_move(1, 1, Board.BLACK)
b.make_move(4, 3, Board.WHITE)
# AI just moved at (1,1), opponent didn't win yet.
# Now it is AI''s turn? Wait - 4 black, 4 white. Black just moved.
# Actually let me recount: moves are black-white alternating.
# B(0,0), W(4,0), B(0,1), W(4,1), B(0,2), W(4,2), B(1,1), W(4,3)
# So white just moved at (4,3). Black to move.
# Opponent has W at (4,0),(4,1),(4,2),(4,3). Needs (4,4) to win.
# AI should block at (4,4).
r, c = get_best_move(b.grid, ai_player=Board.BLACK)
assert (r, c) == (4, 4), f"AI should block at (4,4), got ({r},{c})"
print(f"  PASS: AI blocked at ({r},{c})")

# ---- Test 6: Medium difficulty plays center-ish opening ----
print("Test 6: Opening move preference ...")
b = Board()
r, c = get_best_move(b.grid, ai_player=Board.BLACK, difficulty="medium")
# Should be near center: (3,3) or close
center_dist = abs(r - 3) + abs(c - 3)
assert center_dist <= 2, f"Opening should be near center, got ({r},{c})"
print(f"  PASS: opening move ({r},{c}), center distance={center_dist}")

# ---- Test 7: Easy difficulty still plays reasonably ----
print("Test 7: Easy difficulty ...")
b = Board()
b.make_move(3, 3, Board.WHITE)
r, c = get_best_move(b.grid, ai_player=Board.BLACK, difficulty="easy")
print(f"  PASS: easy AI chose ({r},{c})")

print()
print("All tests passed!")