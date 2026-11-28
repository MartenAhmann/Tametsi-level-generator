"""Storage for custom board shapes built in the level editor.

A custom shape is a small JSON file in CUSTOM_DIR describing which cells of a
square grid are present and which start revealed. The 'custom' template in
templater.py turns such a file into a board (geometry + auto-derived row/column
line hints) that the generator then fills with mines, exactly like the 'clone'
template does for a .puz file. Only the SHAPE is stored here - never any mines.

This module has no heavy dependencies (no tkinter, Pillow or solver), so it can
be imported from the editor, the GUI, the renderer and the templater alike.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CUSTOM_DIR = os.path.join(BASE_DIR, 'custom')
SCHEMA_VERSION = 1
DEFAULT_TILE_SIZE = 10

# Names Windows refuses as files, even with an extension: open('CON.json', 'w')
# targets the console device, so a shape named this way would never persist.
_RESERVED_NAMES = (
  {'CON', 'PRN', 'AUX', 'NUL'}
  | {f'COM{d}' for d in range(1, 10)}
  | {f'LPT{d}' for d in range(1, 10)}
)


def shape_path(name):
  """Path of the JSON file for a custom shape called `name`."""
  return os.path.join(CUSTOM_DIR, name + '.json')


def render_path_for(name):
  """Path of the cached preview PNG for a custom shape called `name`."""
  return os.path.join(CUSTOM_DIR, name + '.png')


def is_valid_name(name):
  """A shape name must be a non-empty, filename-safe single path component."""
  name = (name or '').strip()
  if not name or name in ('.', '..'):
    return False
  if any(ch in name for ch in '\\/:*?"<>|'):
    return False
  # Reject Windows reserved device names (checked against the part before any dot).
  return name.split('.')[0].upper() not in _RESERVED_NAMES


def save_shape(name, cells, tile_size=DEFAULT_TILE_SIZE):
  """Write a custom shape to CUSTOM_DIR/<name>.json and return its path.

  `cells` is an iterable of (x, y, revealed[, color]) tuples: grid coordinates, a
  boolean, and an optional Tametsi color NAME (e.g. 'GREEN') or None for an
  unpainted tile. Coordinates are stored as given; the template normalises them
  to the origin when it builds the board, so the absolute offset does not matter.
  The `color` field is optional, so files written without it stay readable by
  older loaders (the schema version is unchanged).
  """
  if not is_valid_name(name):
    raise ValueError(f'invalid custom level name: {name!r}')

  os.makedirs(CUSTOM_DIR, exist_ok=True)
  out_cells = []
  for cell in cells:
    x, y, revealed = cell[0], cell[1], cell[2]
    color = cell[3] if len(cell) > 3 else None
    out_cells.append(dict(
      x=int(x), y=int(y), revealed=bool(revealed),
      color=(str(color) if color else None)))
  data = dict(
    version=SCHEMA_VERSION,
    shape='square',  # extension point: future tile shapes (hexagon, triangle, ...)
    tile_size=int(tile_size),
    cells=out_cells,
  )
  path = shape_path(name)
  with open(path, 'w', encoding='utf-8') as file:
    json.dump(data, file, indent=2)
  return path


def load_shape(path):
  """Read and lightly validate a custom shape file; return a normalised dict."""
  with open(path, encoding='utf-8') as file:
    data = json.load(file)

  cells = []
  for cell in data.get('cells', []):
    # `color` is optional and absent in older files, so default it to None.
    color = cell.get('color')
    cells.append(dict(
      x=int(cell['x']),
      y=int(cell['y']),
      revealed=bool(cell.get('revealed', False)),
      color=(str(color) if color else None),
    ))

  return dict(
    version=int(data.get('version', SCHEMA_VERSION)),
    shape=str(data.get('shape', 'square')),
    tile_size=int(data.get('tile_size', DEFAULT_TILE_SIZE)),
    cells=cells,
  )


def delete_shape(name):
  """Remove a custom shape's JSON file and its cached preview PNG, if present.

  Returns True if a shape file was actually removed. Missing files are ignored,
  so deleting an already-gone shape is a no-op rather than an error.
  """
  if not is_valid_name(name):
    raise ValueError(f'invalid custom level name: {name!r}')
  removed = False
  for path in (shape_path(name), render_path_for(name)):
    try:
      os.remove(path)
      if path == shape_path(name):
        removed = True
    except FileNotFoundError:
      pass
  return removed


def list_shapes():
  """Sorted list of (name, json_path) for every custom shape in CUSTOM_DIR."""
  if not os.path.isdir(CUSTOM_DIR):
    return []
  names = [f[:-len('.json')] for f in os.listdir(CUSTOM_DIR) if f.lower().endswith('.json')]
  return [(name, shape_path(name)) for name in sorted(names)]
