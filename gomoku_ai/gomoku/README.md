# 7x7 Gomoku AI -- User Guide

## Background

2024 NUEDC E-topic "Tic-Tac-Toe Game Device", modified by instructor:
- Tic-Tac-Toe -> Gomoku (5-in-a-row to win)
- 3x3 board -> 7x7 board
- All other requirements unchanged

This program handles ONLY the game-playing algorithm (computing AI moves).
It does NOT include robot arm control.

Algorithm: Minimax tree search + Alpha-Beta pruning + pattern-based evaluation.
Not deep learning. No training data needed. Every move is explainable.

---

## Requirements

- Python 3.8 or newer
- NO third-party packages needed (GUI uses built-in tkinter)
- Works on Windows / Linux / macOS / Raspberry Pi 5

---

## How to Run

### Option 1: GUI (recommended)

```bash
python gui.py
```

What you will see:
- Top bar: choose who goes first (You/AI) and difficulty (Easy/Med/Hard)
- Center: 7x7 wooden board -- click an intersection to place a piece
- Bottom: status messages (whose turn, AI thinking, result)

Controls:
- Click an empty spot to place your piece
- Hover over the board to see a transparent preview piece
- A gold ring marks the AI's most recent move
- Click "New Game" to restart

Default: You play as Black (X) going first, Medium difficulty.

If you get "No module named gomoku", run this first:
```bash
# Windows
set PYTHONPATH=path\to\extracted\folder

# Linux / Mac / Raspberry Pi
export PYTHONPATH=path/to/extracted/folder
```

### Option 2: Console

```bash
python play.py
```

On startup you will be asked:
1. Who goes first? (1=You, 2=AI; default 1)
2. Difficulty? (1=Easy, 2=Medium, 3=Hard; default 2)

The console board uses . for empty, X for you, O for AI:
```
    0   1   2   3   4   5   6
0   .   .   .   .   .   .   .
1   .   .   .   .   .   .   .
2   .   .   O   .   .   .   .
3   .   .   .   X   .   .   .
4   .   .   .   .   .   .   .
5   .   .   .   .   .   .   .
6   .   .   .   .   .   .   .
```

Enter moves as: row,col (e.g. 3,3). Type quit to exit.

---

## Calling the AI from Your Code

If you need to integrate the AI into your Raspberry Pi main controller:

```python
import sys
sys.path.insert(0, r"D:\your\path\here")  # adjust to your path

from gomoku.ai import get_best_move

# grid: 7x7 list-of-lists
# 0 = empty, 1 = AI piece, 2 = opponent piece

grid = [[0]*7 for _ in range(7)]

# Example: opponent just played at the center
grid[3][3] = 2

# Ask AI to respond
row, col = get_best_move(grid, ai_player=1, difficulty="medium")
print(f"AI plays: ({row}, {col})")
```

Parameters:

| Parameter | Meaning | Values |
|-----------|---------|--------|
| grid | Current board state | 7x7 nested list |
| ai_player | Which side is AI | 1 = Black (first), 2 = White (second) |
| difficulty | AI strength | "easy" / "medium" / "hard" |
| time_limit_ms | Search time limit (ms) | Default 5000 |

Returns: (row, col) tuple.

---

## Algorithm Overview

```
Input: board state
  |
  +-- Can AI win immediately? --> Yes, play winning move
  +-- Can opponent win next turn? --> Yes, block it
  |
  +-- Iterative deepening search
        |
        +-- Try "I play A, opponent plays B, I play C, ..."
        +-- Score each final position
        +-- Choose move leading to best score
```

| Difficulty | Lookahead | Time per move |
|-----------|-----------|---------------|
| Easy | 2 moves | < 0.01s |
| Medium | 4 moves | ~0.05s |
| Hard | 6 moves | 1-3s |

---

## File Structure

```
gomoku/
  README.md       This file
  gui.py          GUI game (double-click or terminal)
  play.py         Console game
  ai.py           AI public interface
  board.py        Board logic (moves, undo, win detection)
  evaluate.py     Pattern scoring
  search.py       Minimax + Alpha-Beta search
  __init__.py     Package marker
  test_ai.py      Tests
```

---

## FAQ

**Q: Can I change the board size (e.g. 15x15)?**
A: Yes, modify size=7 in Board() constructor in board.py, but search time will
increase significantly. You may need to reduce max_depth in search.py.

**Q: Can I make the AI stronger?**
A: Increase the max_depth for "hard" in search.py (line: "hard": 6 -> 8).
Expect longer thinking time.

**Q: Does this run on Raspberry Pi?**
A: Yes. Hard difficulty takes about 1-3 seconds per move on Pi 5.
