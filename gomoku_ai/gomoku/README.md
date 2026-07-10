# 7x7 Gomoku AI

2024 NUEDC E-topic modified: Tic-Tac-Toe -> Gomoku, 3x3 -> 7x7.
Game-playing algorithm only (no robot control).
Algorithm: Minimax + Alpha-Beta pruning + pattern-based evaluation.

## Quick Start

### GUI (recommended)
    python gui.py

### Console
    python play.py

## As a module
    from gomoku.ai import get_best_move
    row, col = get_best_move(grid, ai_player=1, difficulty='medium')

## Files
    board.py      Board representation, move/undo, win detection
    evaluate.py   Pattern-based scoring (5-cell windows x 4 dirs)
    search.py     Minimax + Alpha-Beta + iterative deepening
    ai.py         Public interface
    play.py       Console game
    gui.py        GUI game (tkinter)
    test_ai.py    Tests

## Difficulty
    easy    depth 2   < 0.01s
    medium  depth 4   ~0.05s
    hard    depth 6   1-3s

## Requirements
    Python 3.8+, no third-party packages (tkinter is built-in).
