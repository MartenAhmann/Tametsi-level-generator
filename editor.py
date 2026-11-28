"""Level editor window for the Tametsi Level Generator.

A separate window (a tk.Toplevel) in which you build a custom board SHAPE and
save it. Pick a block in the palette, then click (or drag) on the grid to place
it. You only draw the shape and mark which cells start revealed - the generator
places the mines later, when the saved shape is chosen in the "Custom" category
of the picker.

The tile shape can be square or hexagonal, chosen with the picker above the name
field. Square cells use (x, y) grid coordinates with 8-way adjacency; hexagonal
cells use axial (q, r) coordinates with 6-way adjacency. Both are saved through
custom_levels.save_shape and turned into a board by the 'custom' template.

Pure tkinter: no Pillow needed to build or save a shape. Saving a preview
thumbnail is best-effort and simply skipped if the renderer is unavailable.
"""

import os

import tkinter as tk
from tkinter import ttk

import custom_levels

# Square grid shown in the editor. Shapes may use any part of it; coordinates are
# normalised to the origin on save, so the absolute offset does not matter.
GRID_COLS = 26
GRID_ROWS = 18
CELL_PX = 28

# The canvas keeps the same pixel size in both tile shapes, so switching does not
# resize the window.
CANVAS_W = GRID_COLS * CELL_PX
CANVAS_H = GRID_ROWS * CELL_PX

# Hexagonal grid. HEX_R is the pointy-top hex circumradius (center to vertex) in
# screen pixels; the honeycomb that fits the canvas is computed from it.
SQRT3 = 3 ** 0.5
HEX_R = 20.0

# Colors, roughly matching render.py's board palette.
BG = '#140023'
GRID_LINE = '#343a46'
TILE = '#7D7D7D'
TILE_REVEALED = '#333333'
SELECT_LINE = '#4a78d6'  # highlight for the selected tile-shape thumbnail

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

    # Current tile shape ('square' or 'hexagon').
    self.shape_type = custom_levels.SHAPE_SQUARE

    # (x, y) -> revealed(bool) for every placed cell. Keys are (x, y) grid coords
    # for square tiles, or axial (q, r) hex coords for hexagonal tiles.
    self.cells = {}
    # cell key -> color NAME, for the subset of placed cells that are painted.
    self.colors = {}
    self.tool = tk.StringVar(value=TOOL_PLACE)
    self.name_var = tk.StringVar(value='')
    self.status_var = tk.StringVar(value='')

    # Name of the shape being edited (if any). When the user saves under this
    # same name we overwrite silently; a different name saves a fresh shape.
    self.edit_name = edit_name

    self._last_cell = None  # for drag handling

    # The set of valid hex cells (axial q, r) that fit the canvas, and the pixel
    # origin they are drawn from. Computed once up front (it is cheap).
    self.hex_cells = set()
    self.hex_origin = (0.0, 0.0)
    self._build_hex_grid()

    self._build()
    if edit_name is not None:
      self._load_for_edit(edit_name)
    self._refresh_shape_thumbs()
    self._refresh_place_entry()
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

    # Keep handles to the "place" entry so its swatch and label can follow the
    # current tile shape (square tile vs. hexagon tile).
    self.place_swatch, self.place_radio = self._palette_entry(
      palette, 'Square tile', TOOL_PLACE, TILE,
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

    # Tile-shape picker at the bottom of the palette (above the name field).
    self._build_shape_picker(palette)

    # Grid canvas on the right.
    canvas_wrap = ttk.Frame(body)
    canvas_wrap.pack(side='left', fill='both', expand=True)
    self.canvas = tk.Canvas(
      canvas_wrap,
      width=CANVAS_W, height=CANVAS_H,
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
    radio = ttk.Radiobutton(row, text=label, value=value, variable=self.tool)
    radio.pack(side='left')
    # A tooltip-free hint line beneath keeps it discoverable without extra deps.
    ttk.Label(parent, text=hint, foreground='#888', wraplength=150,
              justify='left').pack(anchor='w', pady=(0, 4))
    return swatch, radio

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

  def _build_shape_picker(self, parent):
    """Two clickable thumbnails (square / hexagon) that choose the tile shape."""
    ttk.Separator(parent, orient='horizontal').pack(fill='x', pady=6)
    ttk.Label(parent, text='Tile shape').pack(anchor='w')
    row = ttk.Frame(parent)
    row.pack(anchor='w', pady=(4, 0))

    self.shape_thumbs = {}
    for kind, label in ((custom_levels.SHAPE_SQUARE, 'Square'),
                        (custom_levels.SHAPE_HEXAGON, 'Hexagon')):
      cell = ttk.Frame(row)
      cell.pack(side='left', padx=(0, 10))
      thumb = tk.Canvas(cell, width=46, height=46, background=BG,
                        highlightthickness=1, highlightbackground=GRID_LINE,
                        cursor='hand2')
      thumb.pack()
      thumb.bind('<Button-1>', lambda _e, k=kind: self._set_shape(k))
      lbl = ttk.Label(cell, text=label, cursor='hand2')
      lbl.pack()
      lbl.bind('<Button-1>', lambda _e, k=kind: self._set_shape(k))
      self.shape_thumbs[kind] = thumb

    ttk.Label(parent,
              text='Choose a square or hexagonal board. Switching shapes clears '
                   'the current drawing.',
              foreground='#888', wraplength=160, justify='left').pack(
                anchor='w', pady=(4, 0))

  # -- Dialogs ----------------------------------------------------------------

  def _modal(self, title, message, buttons, default_index=0):
    """A small modal dialog centered over the editor (not the screen).

    The native tk message boxes ignore the parent position on some systems and
    pop up at the monitor center, so we draw our own and place it over the editor
    with the usual withdraw -> compute-from-parent -> deiconify dance. `buttons`
    is a list of (label, value); returns the chosen value (the last button's
    value if the window is just closed). Coordinates are not clamped to >= 0, so
    a secondary monitor at negative coordinates still works."""
    result = {'value': buttons[-1][1]}
    dlg = tk.Toplevel(self)
    dlg.withdraw()
    dlg.title(title)
    dlg.transient(self)
    dlg.resizable(False, False)

    frame = ttk.Frame(dlg, padding=16)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text=message, wraplength=320, justify='left').pack(
      anchor='w', pady=(0, 14))
    btn_row = ttk.Frame(frame)
    btn_row.pack(anchor='e')

    def choose(value):
      result['value'] = value
      dlg.destroy()

    widgets = []
    for label, value in buttons:
      button = ttk.Button(btn_row, text=label, command=lambda v=value: choose(v))
      button.pack(side='left', padx=(8, 0))
      widgets.append(button)

    dlg.protocol('WM_DELETE_WINDOW', lambda: choose(buttons[-1][1]))
    dlg.bind('<Return>', lambda _e: choose(buttons[default_index][1]))
    dlg.bind('<Escape>', lambda _e: choose(buttons[-1][1]))

    dlg.update_idletasks()
    self.update_idletasks()  # make sure the editor's own geometry is current
    width = dlg.winfo_reqwidth()
    height = dlg.winfo_reqheight()
    px = self.winfo_rootx() + (self.winfo_width() - width) // 2
    py = self.winfo_rooty() + (self.winfo_height() - height) // 2
    dlg.geometry(f'{width}x{height}+{px}+{py}')
    dlg.deiconify()
    dlg.grab_set()
    widgets[default_index].focus_set()
    self.wait_window(dlg)
    return result['value']

  def _ask_yes_no(self, title, message):
    """Modal Yes/No question centered over the editor; returns True/False."""
    return self._modal(title, message, [('Yes', True), ('No', False)])

  def _show_message(self, title, message):
    """Modal information/error dialog centered over the editor."""
    self._modal(title, message, [('OK', None)])

  # -- Tile-shape switching ---------------------------------------------------

  def _set_shape(self, kind):
    if kind == self.shape_type:
      return
    if self.cells and not self._ask_yes_no(
        'Switch tile shape',
        'Switching the tile shape clears the current drawing. Continue?'):
      return
    self.shape_type = kind
    self.cells.clear()
    self.colors.clear()
    self._last_cell = None
    self._refresh_shape_thumbs()
    self._refresh_place_entry()
    self._redraw()
    self._update_status()

  def _refresh_shape_thumbs(self):
    for kind, thumb in getattr(self, 'shape_thumbs', {}).items():
      self._draw_shape_thumb(thumb, kind, kind == self.shape_type)

  @staticmethod
  def _draw_shape_thumb(canvas, kind, selected):
    canvas.delete('all')
    canvas.config(highlightbackground=SELECT_LINE if selected else GRID_LINE,
                  highlightthickness=2 if selected else 1)
    cx = cy = 23
    if kind == custom_levels.SHAPE_SQUARE:
      canvas.create_rectangle(cx - 14, cy - 14, cx + 14, cy + 14,
                              fill=TILE, outline=GRID_LINE)
    else:
      r = 16
      hw = SQRT3 / 2 * r
      canvas.create_polygon(
        [cx, cy - r, cx + hw, cy - r / 2, cx + hw, cy + r / 2,
         cx, cy + r, cx - hw, cy + r / 2, cx - hw, cy - r / 2],
        fill=TILE, outline=GRID_LINE)

  def _refresh_place_entry(self):
    """Redraw the 'place' tool swatch + label to match the current tile shape."""
    swatch = self.place_swatch
    swatch.delete('all')
    if self.shape_type == custom_levels.SHAPE_HEXAGON:
      cx = cy = 11
      r = 9
      hw = SQRT3 / 2 * r
      swatch.create_polygon(
        [cx, cy - r, cx + hw, cy - r / 2, cx + hw, cy + r / 2,
         cx, cy + r, cx - hw, cy + r / 2, cx - hw, cy - r / 2],
        fill=TILE, outline=GRID_LINE)
      self.place_radio.config(text='Hexagon tile')
    else:
      swatch.create_rectangle(3, 3, 19, 19, fill=TILE, outline=GRID_LINE)
      self.place_radio.config(text='Square tile')

  # -- Hex geometry -----------------------------------------------------------

  def _build_hex_grid(self):
    """Compute the set of hex cells (axial q, r) whose tiles fit the canvas."""
    hw = SQRT3 / 2 * HEX_R          # half tile width
    ox = hw + 3
    oy = HEX_R + 3
    self.hex_origin = (ox, oy)
    cells = set()
    max_r = int(CANVAS_H / (1.5 * HEX_R)) + 2
    max_c = int(CANVAS_W / (SQRT3 * HEX_R)) + 2
    for r in range(-1, max_r + 1):
      # Lower rows shift right by r/2 columns, so q must reach negative to fill
      # the left edge; the bounds test keeps only tiles fully inside the canvas.
      for q in range(-max_r - 1, max_c + 1):
        cx = ox + SQRT3 * HEX_R * (q + r / 2.0)
        cy = oy + 1.5 * HEX_R * r
        if (cx - hw >= 1 and cx + hw <= CANVAS_W - 1 and
            cy - HEX_R >= 1 and cy + HEX_R <= CANVAS_H - 1):
          cells.add((q, r))
    self.hex_cells = cells

  def _hex_center(self, q, r):
    ox, oy = self.hex_origin
    return (ox + SQRT3 * HEX_R * (q + r / 2.0), oy + 1.5 * HEX_R * r)

  @staticmethod
  def _hex_poly(cx, cy, scale):
    """Flat list of the 6 pointy-top hex vertices around (cx, cy)."""
    r = HEX_R * scale
    hw = SQRT3 / 2 * r
    return [cx, cy - r, cx + hw, cy - r / 2, cx + hw, cy + r / 2,
            cx, cy + r, cx - hw, cy + r / 2, cx - hw, cy - r / 2]

  @staticmethod
  def _hex_round(qf, rf):
    """Round fractional axial coords to the nearest hex cell (cube rounding)."""
    xf, zf = qf, rf
    yf = -xf - zf
    rx, ry, rz = round(xf), round(yf), round(zf)
    dx, dy, dz = abs(rx - xf), abs(ry - yf), abs(rz - zf)
    if dx > dy and dx > dz:
      rx = -ry - rz
    elif dy > dz:
      ry = -rx - rz
    else:
      rz = -rx - ry
    return int(rx), int(rz)

  # -- Grid interaction -------------------------------------------------------

  def _cell_at(self, event):
    if self.shape_type == custom_levels.SHAPE_HEXAGON:
      return self._hex_cell_at(event)
    return self._square_cell_at(event)

  def _square_cell_at(self, event):
    x = int(self.canvas.canvasx(event.x)) // CELL_PX
    y = int(self.canvas.canvasy(event.y)) // CELL_PX
    if 0 <= x < GRID_COLS and 0 <= y < GRID_ROWS:
      return (x, y)
    return None

  def _hex_cell_at(self, event):
    ox, oy = self.hex_origin
    px = self.canvas.canvasx(event.x) - ox
    py = self.canvas.canvasy(event.y) - oy
    qf = (SQRT3 / 3 * px - 1.0 / 3 * py) / HEX_R
    rf = (2.0 / 3 * py) / HEX_R
    cell = self._hex_round(qf, rf)
    return cell if cell in self.hex_cells else None

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
    if self.shape_type == custom_levels.SHAPE_HEXAGON:
      self._redraw_hex()
    else:
      self._redraw_square()

  def _redraw_square(self):
    self.canvas.delete('all')
    for i in range(GRID_COLS + 1):
      self.canvas.create_line(i * CELL_PX, 0, i * CELL_PX, GRID_ROWS * CELL_PX, fill=GRID_LINE)
    for j in range(GRID_ROWS + 1):
      self.canvas.create_line(0, j * CELL_PX, GRID_COLS * CELL_PX, j * CELL_PX, fill=GRID_LINE)
    for (x, y), revealed in self.cells.items():
      x0, y0 = x * CELL_PX + 1, y * CELL_PX + 1
      x1, y1 = x0 + CELL_PX - 2, y0 + CELL_PX - 2
      color = self.colors.get((x, y))
      fill = self._fill_for(revealed, color)
      # A revealed tile stays dimmed (as it renders in the game); when it is also
      # painted, a colored border keeps its color group visible.
      if revealed and color:
        self.canvas.create_rectangle(
          x0, y0, x1, y1, fill=fill, outline=COLOR_HEX.get(color, BG), width=2)
      else:
        self.canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=BG, width=1)

  def _redraw_hex(self):
    self.canvas.delete('all')
    # Grid outline for every placeable hex, like the square grid lines.
    for (q, r) in self.hex_cells:
      cx, cy = self._hex_center(q, r)
      self.canvas.create_polygon(self._hex_poly(cx, cy, 1.0),
                                 fill=BG, outline=GRID_LINE, width=1)
    # Placed tiles, inset slightly so the seams show.
    for (q, r), revealed in self.cells.items():
      if (q, r) not in self.hex_cells:
        continue
      cx, cy = self._hex_center(q, r)
      color = self.colors.get((q, r))
      fill = self._fill_for(revealed, color)
      if revealed and color:
        self.canvas.create_polygon(self._hex_poly(cx, cy, 0.92),
                                   fill=fill, outline=COLOR_HEX.get(color, BG), width=2)
      else:
        self.canvas.create_polygon(self._hex_poly(cx, cy, 0.92),
                                   fill=fill, outline=BG, width=1)

  @staticmethod
  def _fill_for(revealed, color):
    if revealed:
      return TILE_REVEALED
    if color:
      return COLOR_HEX.get(color, TILE)
    return TILE

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
      self._show_message('Load failed', str(error))
      return
    kind = data.get('shape', custom_levels.SHAPE_SQUARE)
    if kind not in custom_levels.SHAPES:
      kind = custom_levels.SHAPE_SQUARE
    self.shape_type = kind
    cells = data.get('cells', [])
    if kind == custom_levels.SHAPE_HEXAGON:
      self._load_hex_cells(cells)
    else:
      self._load_square_cells(cells)
    self.name_var.set(name)
    self.title(f'Level Editor - {name}')

  def _load_square_cells(self, cells):
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

  def _load_hex_cells(self, cells):
    # A hex shape saved here reloads into the same honeycomb, so it usually fits
    # as stored; translate it onto the grid only if it would fall off.
    coords = [(c['x'], c['y']) for c in cells]
    dq, dr = self._hex_fit_offset(coords)
    self.cells = {
      (c['x'] + dq, c['y'] + dr): bool(c['revealed']) for c in cells
    }
    self.colors = {
      (c['x'] + dq, c['y'] + dr): c['color'] for c in cells if c.get('color')
    }

  def _hex_fit_offset(self, coords):
    """Axial (dq, dr) that brings `coords` onto the editor's honeycomb, if needed."""
    if not coords or all(c in self.hex_cells for c in coords):
      return (0, 0)
    load_r = min(r for _q, r in coords)
    load_q = min(q for q, r in coords if r == load_r)
    grid_r = min(r for _q, r in self.hex_cells)
    grid_q = min(q for q, r in self.hex_cells if r == grid_r)
    return (grid_q - load_q, grid_r - load_r)

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
    if self.cells and not self._ask_yes_no('Clear', 'Remove all tiles?'):
      return
    self.cells.clear()
    self.colors.clear()
    self._last_cell = None
    self._redraw()
    self._update_status()

  def _on_save(self):
    name = self.name_var.get().strip()
    if not custom_levels.is_valid_name(name):
      self._show_message(
        'Invalid name',
        'Please enter a valid level name (no \\ / : * ? " < > |).')
      return
    if not self.cells:
      self._show_message('Empty level', 'Place at least one tile first.')
      return
    if all(self.cells.values()):
      self._show_message(
        'All revealed',
        'At least one tile must stay unrevealed - the generator needs somewhere '
        'to place mines.')
      return
    # Saving under the same name we are editing just updates it; any other
    # existing name prompts before overwriting a different shape.
    if (name != self.edit_name
        and os.path.isfile(custom_levels.shape_path(name))
        and not self._ask_yes_no(
          'Overwrite',
          f'A custom level named "{name}" already exists. Overwrite it?')):
      return

    cells = [(x, y, revealed, self.colors.get((x, y)))
             for (x, y), revealed in self.cells.items()]
    try:
      path = custom_levels.save_shape(name, cells, shape=self.shape_type)
    except (OSError, ValueError) as error:
      self._show_message('Save failed', str(error))
      return

    self._save_thumbnail(name, path)

    if self.on_saved:
      self.on_saved(name, path)
    self._show_message('Saved', f'Custom level "{name}" saved.')
    self.destroy()

  @staticmethod
  def _save_thumbnail(name, path):
    """Best-effort preview PNG; silently skipped if the renderer is unavailable."""
    try:
      import render
      render.ensure_custom_render(name, path)
    except Exception:  # noqa: BLE001 - a missing Pillow etc. just means no thumbnail
      pass
