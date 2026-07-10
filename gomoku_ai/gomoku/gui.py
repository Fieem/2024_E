"""7x7 Gomoku -- GUI game (tkinter).

Run:   python gui.py
"""

import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import messagebox

from gomoku.board import Board
from gomoku.ai import get_best_move


# ---- Constants ----
CELL = 64           # cell size in px
PAD = 16            # padding around grid
R = CELL // 2 - 4   # piece radius
GRID_SIZE = 7

# Colors
BG = "#DEB887"          # wooden board
LINE = "#8B6914"        # grid lines
BLACK_PIECE = "#222222"
WHITE_PIECE = "#F5F5F5"
WHITE_BORDER = "#333333"
HIGHLIGHT = "#FFD700"
TEXT_COLOR = "#333333"


class GomokuGUI:
    def __init__(self):
        self.board = Board()
        self.human_player = Board.BLACK
        self.ai_player = Board.WHITE
        self.difficulty = "medium"
        self.time_limit = 3000
        self.last_ai = None
        self.game_over = False
        self.ai_thinking = False

        self._build_ui()

    # ----------------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------------
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("7x7 Gomoku")
        self.root.resizable(False, False)
        self.root.configure(bg="#F0E6D3")

        # ---- Top control bar ----
        ctrl = tk.Frame(self.root, bg="#F0E6D3", pady=8)
        ctrl.pack()

        # Who first
        tk.Label(ctrl, text="First:", bg="#F0E6D3", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 4))
        self.first_var = tk.StringVar(value="human")
        tk.Radiobutton(ctrl, text="You", variable=self.first_var, value="human",
                       bg="#F0E6D3", font=("Segoe UI", 10),
                       command=self._on_first_change).pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(ctrl, text="AI", variable=self.first_var, value="ai",
                       bg="#F0E6D3", font=("Segoe UI", 10),
                       command=self._on_first_change).pack(side=tk.LEFT, padx=2)

        tk.Label(ctrl, text="   ", bg="#F0E6D3").pack(side=tk.LEFT)

        # Difficulty
        tk.Label(ctrl, text="Level:", bg="#F0E6D3", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(0, 4))
        self.diff_var = tk.StringVar(value="medium")
        for label, val in [("Easy","easy"), ("Med","medium"), ("Hard","hard")]:
            tk.Radiobutton(ctrl, text=label, variable=self.diff_var, value=val,
                           bg="#F0E6D3", font=("Segoe UI", 10),
                           command=self._on_diff_change).pack(side=tk.LEFT, padx=2)

        tk.Label(ctrl, text="   ", bg="#F0E6D3").pack(side=tk.LEFT)

        self.newgame_btn = tk.Button(ctrl, text="New Game", font=("Segoe UI", 10, "bold"),
                                     bg="#5B8C5A", fg="white", relief=tk.FLAT,
                                     padx=14, pady=4, cursor="hand2",
                                     command=self._new_game)
        self.newgame_btn.pack(side=tk.LEFT)

        # ---- Canvas board ----
        canvas_w = GRID_SIZE * CELL + PAD * 2
        canvas_h = GRID_SIZE * CELL + PAD * 2
        self.canvas = tk.Canvas(self.root, width=canvas_w, height=canvas_h,
                                bg=BG, highlightthickness=0, cursor="hand2")
        self.canvas.pack(pady=(8, 0))
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)

        # ---- Status bar ----
        self.status = tk.Label(self.root, text="Your turn (X)", font=("Segoe UI", 11),
                               bg="#F0E6D3", fg=TEXT_COLOR, pady=6)
        self.status.pack()

        self._draw_grid()
        self.root.update()

        # If AI goes first
        if self.human_player == Board.WHITE:
            self._ai_move()

    # ----------------------------------------------------------------
    # Drawing
    # ----------------------------------------------------------------
    def _draw_grid(self):
        self.canvas.delete("grid")
        for i in range(GRID_SIZE):
            x = PAD + i * CELL
            self.canvas.create_line(PAD, x, PAD + (GRID_SIZE - 1) * CELL, x,
                                    fill=LINE, width=1, tags="grid")
            self.canvas.create_line(x, PAD, x, PAD + (GRID_SIZE - 1) * CELL,
                                    fill=LINE, width=1, tags="grid")
        # Star points (center + four corners of center square)
        for r, c in [(3, 3)]:
            cx = PAD + c * CELL
            cy = PAD + r * CELL
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                                    fill=LINE, outline="", tags="grid")

    def _draw_pieces(self):
        self.canvas.delete("piece")
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                cell = self.board.grid[r][c]
                if cell == Board.EMPTY:
                    continue
                cx = PAD + c * CELL
                cy = PAD + r * CELL
                if cell == Board.BLACK:
                    self.canvas.create_oval(cx - R, cy - R, cx + R, cy + R,
                                            fill=BLACK_PIECE, outline="#444",
                                            width=2, tags="piece")
                else:
                    self.canvas.create_oval(cx - R, cy - R, cx + R, cy + R,
                                            fill=WHITE_PIECE, outline=WHITE_BORDER,
                                            width=2, tags="piece")

    def _draw_highlight(self, row, col):
        self.canvas.delete("highlight")
        if row is None:
            return
        cx = PAD + col * CELL
        cy = PAD + row * CELL
        self.canvas.create_oval(cx - R - 3, cy - R - 3, cx + R + 3, cy + R + 3,
                                outline=HIGHLIGHT, width=3, tags="highlight")

    def _draw_hover(self, row, col, active):
        self.canvas.delete("hover")
        if not active or self.ai_thinking or self.game_over:
            return
        if row is None or not self.board.is_empty(row, col):
            return
        cx = PAD + col * CELL
        cy = PAD + row * CELL
        player = self.board.next_player
        color = "#AAA" if player == Board.BLACK else "#DDD"
        self.canvas.create_oval(cx - R + 2, cy - R + 2, cx + R - 2, cy + R - 2,
                                fill=color, outline="", stipple="gray50", tags="hover")

    def refresh(self):
        self._draw_grid()
        self._draw_pieces()
        self._draw_highlight(self.last_ai[0] if self.last_ai else None,
                             self.last_ai[1] if self.last_ai else None)

    # ----------------------------------------------------------------
    # Interaction
    # ----------------------------------------------------------------
    def _on_motion(self, event):
        r = (event.y - PAD + CELL // 2) // CELL
        c = (event.x - PAD + CELL // 2) // CELL
        if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
            self._draw_hover(r, c, True)
        else:
            self._draw_hover(None, None, False)

    def _on_click(self, event):
        if self.ai_thinking or self.game_over:
            return
        if self.board.next_player != self.human_player:
            return

        r = (event.y - PAD + CELL // 2) // CELL
        c = (event.x - PAD + CELL // 2) // CELL
        if not (0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE):
            return
        if not self.board.is_empty(r, c):
            return

        self._draw_hover(None, None, False)
        self.board.make_move(r, c, self.human_player)
        self.refresh()

        if self.board.check_winner() == self.human_player:
            self._end_game("You win!")
            return
        if self.board.is_full():
            self._end_game("Draw")
            return

        self._ai_move()

    def _ai_move(self):
        if self.game_over:
            return
        self.ai_thinking = True
        self.status.config(text="AI thinking...")
        self.canvas.config(cursor="watch")

        def run():
            move = get_best_move(
                self.board.grid, ai_player=self.ai_player,
                difficulty=self.difficulty, time_limit_ms=self.time_limit,
            )
            self.root.after(0, lambda: self._ai_done(move))

        threading.Thread(target=run, daemon=True).start()

    def _ai_done(self, move):
        self.ai_thinking = False
        self.canvas.config(cursor="hand2")
        if move is None or self.game_over:
            return
        self.board.make_move(move[0], move[1], self.ai_player)
        self.last_ai = move
        self.refresh()

        if self.board.check_winner() == self.ai_player:
            self._end_game("AI wins!")
            return
        if self.board.is_full():
            self._end_game("Draw")
            return

        who = "X" if self.human_player == Board.BLACK else "O"
        self.status.config(text="Your turn (" + who + ")")

    def _end_game(self, msg):
        self.game_over = True
        self.status.config(text=msg, fg="#C0392B")
        self._draw_hover(None, None, False)

    # ----------------------------------------------------------------
    # Settings callbacks
    # ----------------------------------------------------------------
    def _on_first_change(self):
        self._new_game()

    def _on_diff_change(self):
        self.difficulty = self.diff_var.get()
        self.time_limit = {"easy": 1000, "medium": 3000, "hard": 8000}[self.difficulty]

    def _new_game(self):
        self.board = Board()
        self.last_ai = None
        self.game_over = False
        self.ai_thinking = False
        self.human_player = Board.BLACK if self.first_var.get() == "human" else Board.WHITE
        self.ai_player = Board.WHITE if self.human_player == Board.BLACK else Board.BLACK
        self.difficulty = self.diff_var.get()
        self.time_limit = {"easy": 1000, "medium": 3000, "hard": 8000}[self.difficulty]

        self.refresh()
        self.status.config(text="Your turn (X)" if self.human_player == Board.BLACK else "Your turn (O)",
                           fg=TEXT_COLOR)
        self.canvas.config(cursor="hand2")

        if self.human_player == Board.WHITE:
            self._ai_move()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    GomokuGUI().run()