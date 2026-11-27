"""
Render a Tametsi .puz level to a PNG image of its board shape.

Each tile is drawn as its real polygon (the <POLY><POINTS> of the node),
positioned at the node's <POS>. Tiles are colored by their color hint group;
tiles without one get a neutral fill, pre-revealed tiles a dimmed fill. No text
or hint numbers are drawn - this is a plain picture of the shape and colors,
which is exactly what the 'clone' template reuses.

Used both as a command-line tool (render every test/*.puz) and by gui.py (to
show a thumbnail of each level in the clone picker).

Usage:
  python render.py                 # render every test/*.puz into test_renders/
  python render.py path/to/file.puz [out.png]
"""

import os
import sys

from PIL import Image, ImageDraw

from loader import extract

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(BASE_DIR, 'test')
RENDER_DIR = os.path.join(BASE_DIR, 'test_renders')

# Background and tile colors (roughly matching Tametsi's palette).
BACKGROUND = (30, 30, 40)
NEUTRAL_TILE = (90, 101, 117)
REVEALED_TILE = (42, 47, 58)

COLOR_MAP = {
  'RED': (214, 69, 69),
  'ORANGE': (224, 138, 46),
  'YELLOW': (227, 197, 58),
  'GREEN': (79, 166, 91),
  'BLUE': (74, 120, 214),
  'INDIGO': (63, 79, 160),
  'VIOLET': (138, 79, 208),
  'PINK': (216, 115, 176),
}

SUPERSAMPLE = 3  # draw big, then shrink down for smooth (anti-aliased) edges


def _floats(value):
  # extract() returns <POS> already split into a list, but <POINTS> as a string
  parts = value if isinstance(value, list) else value.split(',')
  return [float(p) for p in parts if p != '']


def build_polygons(data):
  """Turn extracted node data into (vertices, fill_color) pairs and a bounding box."""
  # node id -> color name (from the color hints)
  node_color = {}
  for color in data.get('colors', []):
    rgb = COLOR_MAP.get(str(color.get('color', '')).upper())
    if rgb is None:
      continue
    for cid in color['ids']:
      node_color[cid] = rgb

  polygons = []
  min_x = min_y = float('inf')
  max_x = max_y = float('-inf')

  for node in data['nodes']:
    pos = _floats(node['position'])
    pts = _floats(node['points'])
    if len(pos) < 2 or len(pts) < 6:  # need a center and at least a triangle
      continue

    cx, cy = pos[0], pos[1]
    verts = [(cx + pts[i], cy + pts[i + 1]) for i in range(0, len(pts) - 1, 2)]

    if node.get('revealed'):
      fill = REVEALED_TILE
    else:
      fill = node_color.get(node['id'], NEUTRAL_TILE)

    polygons.append((verts, fill))
    for vx, vy in verts:
      min_x, min_y = min(min_x, vx), min(min_y, vy)
      max_x, max_y = max(max_x, vx), max(max_y, vy)

  return polygons, (min_x, min_y, max_x, max_y)


def render_contents(contents, px=512):
  """Render puzzle file contents to a square PIL.Image of side `px`."""
  data = extract(contents)
  polygons, (min_x, min_y, max_x, max_y) = build_polygons(data)

  img = Image.new('RGB', (px, px), BACKGROUND)
  if not polygons:
    return img

  span_x = max(max_x - min_x, 1e-6)
  span_y = max(max_y - min_y, 1e-6)
  span = max(span_x, span_y)

  big = px * SUPERSAMPLE
  pad = big * 0.04
  scale = (big - 2 * pad) / span
  # center the shape in the square
  off_x = pad + (big - 2 * pad - span_x * scale) / 2
  off_y = pad + (big - 2 * pad - span_y * scale) / 2

  canvas = Image.new('RGB', (big, big), BACKGROUND)
  draw = ImageDraw.Draw(canvas)
  stroke = max(1, round(big / px))

  for verts, fill in polygons:
    scaled = [(off_x + (vx - min_x) * scale, off_y + (vy - min_y) * scale) for vx, vy in verts]
    draw.polygon(scaled, fill=fill, outline=BACKGROUND, width=stroke)

  return canvas.resize((px, px), Image.LANCZOS)


def render_file(puz_path, out_path=None, px=512):
  with open(puz_path, encoding='utf-8') as f:
    contents = f.read()
  img = render_contents(contents, px=px)
  if out_path:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
  return img


def list_test_puzzles():
  """Sorted list of (name, puz_path) for every .puz file in test/."""
  if not os.path.isdir(TEST_DIR):
    return []
  names = [f for f in os.listdir(TEST_DIR) if f.lower().endswith('.puz')]
  return [(os.path.splitext(f)[0], os.path.join(TEST_DIR, f)) for f in sorted(names)]


def render_path_for(name):
  """Where the cached PNG for a test puzzle called `name` lives."""
  return os.path.join(RENDER_DIR, name + '.png')


def ensure_render(name, puz_path, px=512):
  """Return the cached PNG path for a test puzzle, rendering it if needed/stale."""
  out = render_path_for(name)
  try:
    fresh = os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(puz_path)
  except OSError:
    fresh = False
  if not fresh:
    render_file(puz_path, out, px=px)
  return out


def render_all(px=512):
  puzzles = list_test_puzzles()
  os.makedirs(RENDER_DIR, exist_ok=True)
  for name, path in puzzles:
    out = render_path_for(name)
    try:
      render_file(path, out, px=px)
      print('rendered', out)
    except Exception as error:  # noqa: BLE001 - keep going, report the bad one
      print('FAILED', name, '-', error)
  return len(puzzles)


def main():
  if len(sys.argv) > 1:
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '.png'
    render_file(src, out)
    print('rendered', out)
  else:
    count = render_all()
    print(f'done: {count} puzzles -> {RENDER_DIR}')


if __name__ == '__main__':
  main()
