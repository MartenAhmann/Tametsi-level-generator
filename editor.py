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
BG = '#140023'
GRID_LINE = '#343a46'
TILE = '#7D7D7D'
TILE_REVEALED = '#333333'

# Tametsi's color-hint hues, as (name, hex). These mirror render.py's COLOR_MAP
# (kept here as hex strings so the editor needs no Pillow just to show swatches).
COLOR_HEXES = [
  ('RED', '#d64545'),
  ('ORANGE', '#e08a2e'),
  ('YELLOW', '#e3c53a'),
  ('GREEN', '#4fa65b'),
  ('BLUE', '#4a78d6'),
  ('INDIGO', '#3f4fa0'),
  ('VIOLET', '#8a4fd0'),
  ('PINK', '#d873b0'),
]
COLOR_HEX = dict(COLOR_HEXES)

# Palette tools ("blocks").
TOOL_PLACE = 'place'
TOOL_REVEAL = 'reveal'
TOOL_ERASE = 'erase'
TOOL_NOCOLOR = 'nocolor'
# Color tools are 'color:<NAME>' so one StringVar can hold every palette choice.
COLOR_TOOL_PREFIX = 'color:'


class LevelEditor(tk.Toplevel):
  """A window to build and save one custom board shape."""

  def __init__(self, master, on_saved=None, edit_name=None):
    super().__init__(master)
    self.title('Level Editor')
    self.on_saved = on_saved  # called as on_saved(name, json_path) after a save

    # (x, y) -> revealed(bool) for every placed cell.
    self.cells = {}
    # (x, y) -> color NAME, for the subset of placed cells that are painted.
    self.colors = {}
    self.tool = tk.StringVar(value=TOOL_PLACE)
    self.name_var = tk.StringVar(value='')
    self.status_var = tk.StringVar(value='')

    # Name of the shape being edited (if any). When the user saves under this
    # same name we overwrite silently; a different name saves a fresh shape.
    self.edit_name = edit_name

    self._last_cell = None  # for drag handling

    self._build()
    if edit_name is not None:
      self._load_for_edit(edit_name)
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
      text='Left click to place / right click to erase. Only the shape is saved, '
           'the generator adds the mines.',
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
                        'Mark a tile as starting revealed (right click to undo).')

    ttk.Separator(palette, orient='horizontal').pack(fill='x', pady=6)
    ttk.Label(palette, text='Colors').pack(anchor='w')
    grid = ttk.Frame(palette)
    grid.pack(fill='x', pady=(2, 0))
    for index, (name, hexcolor) in enumerate(COLOR_HEXES):
      self._color_entry(grid, name, hexcolor, index)
    # "No color" clears a tile's paint without removing the tile itself.
    self._color_entry(grid, 'No color', None, len(COLOR_HEXES), tool=TOOL_NOCOLOR)
    ttk.Label(palette,
              text='Paint a color on a tile (places one if the cell is empty). '
                   'Each color becomes a color hint in the generated puzzle.',
              foreground='#888', wraplength=160, justify='left').pack(
                anchor='w', pady=(6, 0))

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

  def _color_entry(self, parent, label, hexcolor, index, tool=None):
    """A compact swatch + radiobutton for a color (or the 'No color' clearer).

    Laid out in a two-column grid to keep the palette short. `tool` overrides the
    bound value (used for 'No color'); otherwise the value is 'color:<NAME>'.
    """
    value = tool if tool is not None else COLOR_TOOL_PREFIX + label
    row = ttk.Frame(parent)
    row.grid(row=index // 2, column=index % 2, sticky='w', padx=2, pady=1)
    swatch = tk.Canvas(row, width=16, height=16, highlightthickness=1,
                       highlightbackground=GRID_LINE, background=BG)
    swatch.create_rectangle(2, 2, 14, 14, fill=hexcolor or TILE, outline=GRID_LINE)
    swatch.pack(side='left', padx=(0, 4))
    ttk.Radiobutton(row, text=label, value=value, variable=self.tool).pack(side='left')

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
      # Place a plain, unrevealed tile: painting over a revealed or colored cell
      # resets it to a neutral tile.
      self.cells[cell] = False
      self.colors.pop(cell, None)
    elif tool == TOOL_ERASE:
      self.cells.pop(cell, None)
      self.colors.pop(cell, None)
    elif tool == TOOL_REVEAL:
      # Reveal only ever marks a tile revealed; it never un-reveals, so clicking
      # an already-revealed tile (or dragging over one) leaves it revealed.
      if cell in self.cells:
        self.cells[cell] = True
    elif tool == TOOL_NOCOLOR:
      # Strip the paint but leave the tile in place.
      self.colors.pop(cell, None)
    elif tool.startswith(COLOR_TOOL_PREFIX):
      # Painting a color places a tile first if the cell is empty, then tints it.
      if cell not in self.cells:
        self.cells[cell] = False
      self.colors[cell] = tool[len(COLOR_TOOL_PREFIX):]
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
      color = self.colors.get((x, y))
      if revealed:
        fill = TILE_REVEALED
      elif color:
        fill = COLOR_HEX.get(color, TILE)
      else:
        fill = TILE
      # A revealed tile stays dimmed (as it renders in the game); when it is also
      # painted, a colored border keeps its color group visible.
      if revealed and color:
        self.canvas.create_rectangle(
          x0, y0, x1, y1, fill=fill, outline=COLOR_HEX.get(color, BG), width=2)
      else:
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=BG, width=1)

  def _update_status(self):
    total = len(self.cells)
    revealed = sum(1 for r in self.cells.values() if r)
    colored = len(self.colors)
    self.status_var.set(f'{total} tiles, {revealed} revealed, {colored} colored')

  # -- Actions ----------------------------------------------------------------

  def _load_for_edit(self, name):
    """Preload an existing custom shape so it can be edited and re-saved."""
    try:
      data = custom_levels.load_shape(custom_levels.shape_path(name))
    except (OSError, ValueError) as error:
      messagebox.showerror('Load failed', str(error), parent=self)
      return
    cells = data.get('cells', [])
    # Keep the shape where it was drawn. Only shift it (as little as possible)
    # if it would otherwise fall outside the editor grid.
    xs = [c['x'] for c in cells]
    ys = [c['y'] for c in cells]
    dx = self._fit_offset(xs, GRID_COLS)
    dy = self._fit_offset(ys, GRID_ROWS)
    self.cells = {
      (c['x'] + dx, c['y'] + dy): bool(c['revealed']) for c in cells
    }
    self.colors = {
      (c['x'] + dx, c['y'] + dy): c['color'] for c in cells if c.get('color')
    }
    self.name_var.set(name)
    self.title(f'Level Editor - {name}')

  @staticmethod
  def _fit_offset(coords, limit):
    """Offset to add to `coords` so they all fall within 0..limit-1.

    Returns 0 when the coordinates already fit (keeping the original position);
    otherwise the smallest shift that brings them back on-grid."""
    if not coords:
      return 0
    lo, hi = min(coords), max(coords)
    if lo < 0:
      return -lo
    if hi > limit - 1:
      return -(hi - (limit - 1))
    return 0

  def _on_clear(self):
    if self.cells and not messagebox.askyesno('Clear', 'Remove all tiles?', parent=self):
      return
    self.cells.clear()
    self.colors.clear()
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
    # Saving under the same name we are editing just updates it; any other
    # existing name prompts before overwriting a different shape.
    if (name != self.edit_name
        and os.path.isfile(custom_levels.shape_path(name))
        and not messagebox.askyesno(
          'Overwrite', f'A custom level named "{name}" already exists. Overwrite it?',
          parent=self)):
      return

    cells = [(x, y, revealed, self.colors.get((x, y)))
             for (x, y), revealed in self.cells.items()]
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
