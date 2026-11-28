"""Level editor window for the Tametsi Level Generator.

A separate window (a tk.Toplevel) in which you build a custom board SHAPE on a
square grid and save it. Pick a block in the palette, then click (or drag) on the
grid to place it. You only draw the shape and mark which cells start revealed -
the generator places the mines later, when the saved shape is chosen in the
"Custom" category of the picker.

Pure tkinter: no Pillow needed to build or save a shape. Saving a preview
thumbnail is best-effort and simply skipped if the renderer is unavailable.
"""

import os

import tkinter as tk
from tkinter import ttk, messagebox

import custom_levels

# Grid shown in the editor. Shapes may use any part of it; coordinates are
# normalised to the origin on save, so the absolute offset does not matter.
GRID_COLS = 26
GRID_ROWS = 18
CELL_PX = 28

# Colors, roughly matching render.py's board palette.
BG = '#1e1e28'
GRID_LINE = '#343a46'
TILE = '#5a6575'
TILE_REVEALED = '#2a2f3a'
HOVER = '#8a94a6'

# Palette tools ("blocks").
TOOL_PLACE = 'place'
TOOL_REVEAL = 'reveal'
TOOL_ERASE = 'erase'


class LevelEditor(tk.Toplevel):
  """A window to build and save one custom board shape."""

  def __init__(self, master, on_saved=None):
    super().__init__(master)
    self.title('Level Editor')
    self.on_saved = on_saved  # called as on_saved(name, json_path) after a save

    # (x, y) -> revealed(bool) for every placed cell.
    self.cells = {}
    self.tool = tk.StringVar(value=TOOL_PLACE)
    self.name_var = tk.StringVar(value='')
    self.status_var = tk.StringVar(value='')

    self._last_cell = None  # for drag handling

    self._build()
    self._redraw()
    self._update_status()

    self.transient(master)
    self.minsize(GRID_COLS * CELL_PX // 2, 400)

  # -- Layout -----------------------------------------------------------------

  def _build(self):
    root = ttk.Frame(self, padding=10)
    root.pack(fill='both', expand=True)

    ttk.Label(
      root,
      text='Build a board shape: pick a block on the left, then click or drag on '
           'the grid. Only the shape is saved - the generator adds the mines.',
      wraplength=GRID_COLS * CELL_PX, justify='left',
    ).pack(anchor='w', pady=(0, 8))

    body = ttk.Frame(root)
    body.pack(fill='both', expand=True)

    # Palette on the left.
    palette = ttk.LabelFrame(body, text='Palette', padding=8)
    palette.pack(side='left', fill='y', padx=(0, 10))

    self._palette_entry(palette, 'Square tile', TOOL_PLACE, TILE,
                        'Place a tile on the clicked cell.')
    self._palette_entry(palette, 'Revealed start', TOOL_REVEAL, TILE_REVEALED,
                        'Mark a tile as starting revealed (erase to undo).')
    self._palette_entry(palette, 'Erase', TOOL_ERASE, BG,
                        'Remove the tile from the clicked cell.')

    # Grid canvas on the right.
    canvas_wrap = ttk.Frame(body)
    canvas_wrap.pack(side='left', fill='both', expand=True)
    self.canvas = tk.Canvas(
      canvas_wrap,
      width=GRID_COLS * CELL_PX, height=GRID_ROWS * CELL_PX,
      background=BG, highlightthickness=1, highlightbackground=GRID_LINE,
    )
    self.canvas.pack()
    self.canvas.bind('<Button-1>', self._on_press)
    self.canvas.bind('<B1-Motion>', self._on_drag)
    self.canvas.bind('<ButtonRelease-1>', lambda _e: setattr(self, '_last_cell', None))
    # Right-click always erases, whatever the current tool.
    self.canvas.bind('<Button-3>', self._on_right)
    self.canvas.bind('<B3-Motion>', self._on_right)

    # Bottom bar: name, save, clear, status.
    bar = ttk.Frame(root)
    bar.pack(fill='x', pady=(10, 0))
    ttk.Label(bar, text='Name:').pack(side='left')
    ttk.Entry(bar, textvariable=self.name_var, width=24).pack(side='left', padx=(4, 10))
    ttk.Button(bar, text='Save', command=self._on_save).pack(side='left')
    ttk.Button(bar, text='Clear', command=self._on_clear).pack(side='left', padx=(8, 0))
    ttk.Button(bar, text='Close', command=self.destroy).pack(side='right')
    ttk.Label(bar, textvariable=self.status_var).pack(side='right', padx=12)

  def _palette_entry(self, parent, label, value, swatch_color, hint):
    row = ttk.Frame(parent)
    row.pack(fill='x', pady=3)
    swatch = tk.Canvas(row, width=22, height=22, highlightthickness=1,
                       highlightbackground=GRID_LINE, background=BG)
    swatch.create_rectangle(3, 3, 19, 19, fill=swatch_color, outline=GRID_LINE)
    swatch.pack(side='left', padx=(0, 6))
    ttk.Radiobutton(row, text=label, value=value, variable=self.tool).pack(side='left')
    # A tooltip-free hint line beneath keeps it discoverable without extra deps.
    ttk.Label(parent, text=hint, foreground='#888', wraplength=150,
              justify='left').pack(anchor='w', pady=(0, 4))

  # -- Grid interaction -------------------------------------------------------

  def _cell_at(self, event):
    x = int(self.canvas.canvasx(event.x)) // CELL_PX
    y = int(self.canvas.canvasy(event.y)) // CELL_PX
    if 0 <= x < GRID_COLS and 0 <= y < GRID_ROWS:
      return (x, y)
    return None

  def _apply(self, cell, tool):
    if cell is None:
      return
    if tool == TOOL_PLACE:
      # Place an unrevealed tile; painting over a revealed one resets it.
      self.cells[cell] = False
    elif tool == TOOL_ERASE:
      self.cells.pop(cell, None)
    elif tool == TOOL_REVEAL:
      # Reveal only ever marks a tile revealed; it never un-reveals, so clicking
      # an already-revealed tile (or dragging over one) leaves it revealed.
      if cell in self.cells:
        self.cells[cell] = True
    self._redraw()
    self._update_status()

  def _on_press(self, event):
    cell = self._cell_at(event)
    self._last_cell = cell
    self._apply(cell, self.tool.get())

  def _on_drag(self, event):
    cell = self._cell_at(event)
    if cell is not None and cell != self._last_cell:
      self._last_cell = cell
      self._apply(cell, self.tool.get())

  def _on_right(self, event):
    cell = self._cell_at(event)
    if cell is not None and cell != self._last_cell:
      self._last_cell = cell
      self._apply(cell, TOOL_ERASE)

  def _redraw(self):
    self.canvas.delete('all')
    for i in range(GRID_COLS + 1):
      self.canvas.create_line(i * CELL_PX, 0, i * CELL_PX, GRID_ROWS * CELL_PX, fill=GRID_LINE)
    for j in range(GRID_ROWS + 1):
      self.canvas.create_line(0, j * CELL_PX, GRID_COLS * CELL_PX, j * CELL_PX, fill=GRID_LINE)
    for (x, y), revealed in self.cells.items():
      x0, y0 = x * CELL_PX + 1, y * CELL_PX + 1
      x1, y1 = x0 + CELL_PX - 2, y0 + CELL_PX - 2
      self.canvas.create_rectangle(
        x0, y0, x1, y1,
        fill=TILE_REVEALED if revealed else TILE, outline=BG, width=1)

  def _update_status(self):
    total = len(self.cells)
    revealed = sum(1 for r in self.cells.values() if r)
    self.status_var.set(f'{total} tiles, {revealed} revealed')

  # -- Actions ----------------------------------------------------------------

  def _on_clear(self):
    if self.cells and not messagebox.askyesno('Clear', 'Remove all tiles?', parent=self):
      return
    self.cells.clear()
    self._last_cell = None
    self._redraw()
    self._update_status()

  def _on_save(self):
    name = self.name_var.get().strip()
    if not custom_levels.is_valid_name(name):
      messagebox.showerror('Invalid name', 'Please enter a valid level name '
                           '(no \\ / : * ? " < > |).', parent=self)
      return
    if not self.cells:
      messagebox.showerror('Empty level', 'Place at least one tile first.', parent=self)
      return
    if all(self.cells.values()):
      messagebox.showerror(
        'All revealed',
        'At least one tile must stay unrevealed - the generator needs somewhere '
        'to place mines.', parent=self)
      return
    if os.path.isfile(custom_levels.shape_path(name)) and not messagebox.askyesno(
        'Overwrite', f'A custom level named "{name}" already exists. Overwrite it?',
        parent=self):
      return

    cells = [(x, y, revealed) for (x, y), revealed in self.cells.items()]
    try:
      path = custom_levels.save_shape(name, cells)
    except (OSError, ValueError) as error:
      messagebox.showerror('Save failed', str(error), parent=self)
      return

    self._save_thumbnail(name, path)

    if self.on_saved:
      self.on_saved(name, path)
    messagebox.showinfo('Saved', f'Custom level "{name}" saved.', parent=self)
    self.destroy()

  @staticmethod
  def _save_thumbnail(name, path):
    """Best-effort preview PNG; silently skipped if the renderer is unavailable."""
    try:
      import render
      render.ensure_custom_render(name, path)
    except Exception:  # noqa: BLE001 - a missing Pillow etc. just means no thumbnail
      pass
