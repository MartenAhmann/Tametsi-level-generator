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
  python render.py                 # render every test/*.puz into "Tametsi Bonus Puzzle Images/"
  python render.py --templates     # render each board template into "Template Images/"
  python render.py path/to/file.puz [out.png]
"""

import os
import sys

from PIL import Image, ImageDraw

from loader import extract

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(BASE_DIR, 'test')
RENDER_DIR = os.path.join(BASE_DIR, 'Tametsi Bonus Puzzle Images')
TEMPLATE_IMG_DIR = os.path.join(BASE_DIR, 'Template Images')

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
  # extract() returns <POS> already split into a list, but <POINTS> as a string.
  # Template render functions (templater.py) hand positions over as tuples.
  parts = value if isinstance(value, (list, tuple)) else value.split(',')
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
  return render_data(extract(contents), px=px)


def render_data(data, px=512):
  """Render already-parsed node/color data (as from extract() or a template
  render function) to a square PIL.Image of side `px`."""
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


def _template_datas():
  """(name, render-data) pairs for each board-shape template.

  The mine layout does not affect the rendered shape - render.py draws only the
  tiles and their color regions - so we hand each template render function an
  all-'.' (no mines) layout purely to obtain its node geometry and color groups.
  """
  import templater  # local import: this pulls in the solver, only needed here

  datas = []

  # combination_lock: a plain size x size square grid.
  size = 6
  datas.append(('Combination Lock',
                templater.combination_lock_render('.' * (size * size), size)))

  # cl_corner_bite: the same square grid with one pre-revealed corner.
  size = 6
  datas.append(('CL Corner Bite',
                templater.cl_corner_bite_render('.' * (size * size), size)))

  # holey: a (2*size+1) square grid with a regular pattern of revealed holes.
  size = 3
  grid = 2 * size + 1
  datas.append(('Holey',
                templater.holey_render('.' * (grid * grid), size)))

  # l_shape_grid: a recursive L shape with four color regions.
  size, depth = 2, 2
  template = templater.L_shape_grid(None, size, depth)
  unrevealed = len(template['board']) - len(template['revealed'])
  datas.append(('L-Shape Grid',
                templater.L_shape_grid('.' * unrevealed, size, depth)))

  return datas


def render_templates(px=512):
  os.makedirs(TEMPLATE_IMG_DIR, exist_ok=True)
  datas = _template_datas()
  for name, data in datas:
    out = os.path.join(TEMPLATE_IMG_DIR, name + '.png')
    try:
      render_data(data, px=px).save(out)
      print('rendered', out)
    except Exception as error:  # noqa: BLE001 - keep going, report the bad one
      print('FAILED', name, '-', error)
  return len(datas)


def main():
  if len(sys.argv) > 1 and sys.argv[1] == '--templates':
    count = render_templates()
    print(f'done: {count} templates -> {TEMPLATE_IMG_DIR}')
  elif len(sys.argv) > 1:
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + '.png'
    render_file(src, out)
    print('rendered', out)
  else:
    count = render_all()
    print(f'done: {count} puzzles -> {RENDER_DIR}')


if __name__ == '__main__':
  main()
