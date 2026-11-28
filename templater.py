import os
from functools import partial
from solver import Puzzle
from scorer import score
from loader import load, extract
import custom_levels


# ---------------------------------------------------------------------------
# Template registry
#
# Each template is a pair: a make function `<x>(size, ...)` returning the
# internal dict used for generation, and a render function `<x>_render(
# compressed, size, ...)` returning the fields writer.py needs. Register the
# pair in ONE place - decorate the render function with @template(...) and the
# matching make function (same name without the `_render` suffix) is paired
# automatically. make_template / render_template and render.py's template
# previews all read this registry, so a new template needs no other wiring.
# ---------------------------------------------------------------------------

TEMPLATES = {}


def register_template(name, make, render, label=None, preview_args=None):
  """Register a template by name.

  `make(*args)` returns the internal dict (num, board, revealed, constraints,
  sanity_check); `render(compressed, *args)` returns the render fields. `label`
  is the display name used for the preview PNG; `preview_args` are the args
  render.py feeds the template to draw its board-shape preview (None means the
  template has no fixed shape and is skipped for previews, e.g. 'clone').
  """
  TEMPLATES[name] = dict(make=make, render=render, label=label or name, preview_args=preview_args)


def template(name, label=None, preview_args=None):
  """Decorator for the usual make/render pair. Put it on the `<x>_render`
  function; the matching make function `<x>` is looked up and paired
  automatically. A single combined function (make and render in one, chosen by
  whether `compressed` is given, as with l_shape_grid and clone) is registered
  with register_template(...) directly instead."""
  def decorate(render_fn):
    render_name = render_fn.__name__
    if not render_name.endswith('_render'):
      raise ValueError(f'@template expects a *_render function, got {render_name!r}')
    make_fn = globals()[render_name[:-len('_render')]]
    register_template(name, make_fn, render_fn, label=label, preview_args=preview_args)
    return render_fn
  return decorate


def combination_lock(size):
  board = []
  revealed = []
  constraints = []

  for y in range(size):
    constraints.append([0, list(range(size * y, size * y + size))])  # horizontal
    constraints.append([0, list(range(y, size * size + y, size))])  # vertical

    for x in range(size):
      cell_id = x + size * y

      neighbors = []
      for dy in range(-1, 2):
        for dx in range(-1, 2):
          if dx == dy == 0:
            continue
          elif x + dx < 0 or x + dx >= size:
            continue
          elif y + dy < 0 or y + dy >= size:
            continue

          neighbors.append(x + dx + size * (y + dy))

      board.append([cell_id, '', neighbors])

  constraints.append([0, list(range(size ** 2))])

  def sanity_check(compressed):  # takes a compressed string
    h, v = [0] * size, [0] * size
    for i in range(size):
      for j in range(size):
        h[i] += compressed[i * size + j] == '*'
        v[i] += compressed[i + j * size] == '*'

    return 0 in h or 0 in v or size in h or size in v

  return dict(
    num=size ** 2,
    board=board,
    revealed=revealed,
    constraints=constraints,
    sanity_check=sanity_check,
  )


@template('combination_lock', label='Combination Lock', preview_args=(6,))
def combination_lock_render(compressed, size):
  template = combination_lock(size)
  num, board = template['num'], template['board']
  revealed, constraints = template['revealed'], template['constraints']

  tile_size = 10
  points = '-{s},-{s},{s},-{s},{s},{s},-{s},{s}'.format(s=0.96 * tile_size / 2)

  nodes = []
  columns = []

  for i in range(num):
    board[i][1] = compressed[i]
    nodes.append(dict(
      id=i,
      neighbors=board[i][2],
      position=((i % size) * tile_size, (i // size) * tile_size),
      has_mine=compressed[i] == '*',
      secret=compressed[i] == '?',
      points=points,
    ))

  for j in range(size):
    # horizontal column hints
    constraints[2 * j][0] = sum([compressed[i] == '*' for i in constraints[2 * j][1]])
    columns.append(dict(
      ids=constraints[2 * j][1],
      text_location=(-tile_size, j * tile_size),
    ))

    # vertical column hints
    constraints[2 * j + 1][0] = sum([compressed[i] == '*' for i in constraints[2 * j + 1][1]])
    columns.append(dict(
      ids=constraints[2 * j + 1][1],
      text_location=(j * tile_size, -tile_size),
    ))

  constraints[-1][0] = compressed.count('*')

  result = Puzzle(board, revealed, constraints).solve()
  scored = score(result, 'seqnum')
  title = f'Combination Lock {size}x{size} with score {scored}'
  tile_text = 'CLX'

  return dict(
    title=title,
    tile_text=tile_text,
    nodes=nodes,
    columns=columns,
    score=scored,
  )


def cl_corner_bite(size):
  board = []
  revealed = [0]
  constraints = []

  for y in range(size):
    constraints.append([0, list(range(size * y, size * y + size))])  # horizontal
    constraints.append([0, list(range(y, size * size + y, size))])  # vertical

    for x in range(size):
      cell_id = x + size * y

      neighbors = []
      for dy in range(-1, 2):
        for dx in range(-1, 2):
          if dx == dy == 0:
            continue
          elif x + dx < 0 or x + dx >= size:
            continue
          elif y + dy < 0 or y + dy >= size:
            continue

          neighbors.append(x + dx + size * (y + dy))

      board.append([cell_id, '', neighbors])

  constraints.append([0, list(range(size ** 2))])

  def sanity_check(compressed):  # takes a compressed string
    return compressed[0] == '.'

  return dict(
    num=size ** 2,
    board=board,
    revealed=revealed,
    constraints=constraints,
    sanity_check=sanity_check,
  )


@template('cl_corner_bite', label='CL Corner Bite', preview_args=(6,))
def cl_corner_bite_render(compressed, size):
  template = cl_corner_bite(size)
  num, board = template['num'], template['board']
  revealed, constraints = template['revealed'], template['constraints']

  # the generator's compressed string leaves out the revealed cells; writer.py may pass the full string
  if len(compressed) != num:
    remaining = iter(compressed)
    compressed = ''.join('.' if i in revealed else next(remaining) for i in range(num))

  tile_size = 10
  points = '-{s},-{s},{s},-{s},{s},{s},-{s},{s}'.format(s=0.96 * tile_size / 2)

  nodes = []
  columns = []

  for i in range(num):
    board[i][1] = compressed[i]
    nodes.append(dict(
      id=i,
      neighbors=board[i][2],
      position=((i % size) * tile_size, (i // size) * tile_size),
      has_mine=compressed[i] == '*',
      secret=compressed[i] == '?',
      revealed=i in revealed,
      points=points,
    ))

  for j in range(size):
    # horizontal column hints
    constraints[2 * j][0] = sum([compressed[i] == '*' for i in constraints[2 * j][1]])
    columns.append(dict(
      ids=constraints[2 * j][1],
      text_location=(-tile_size, j * tile_size),
    ))

    # vertical column hints
    constraints[2 * j + 1][0] = sum([compressed[i] == '*' for i in constraints[2 * j + 1][1]])
    columns.append(dict(
      ids=constraints[2 * j + 1][1],
      text_location=(j * tile_size, -tile_size),
    ))

  constraints[-1][0] = compressed.count('*')

  result = Puzzle(board, revealed, constraints).solve()
  scored = score(result, 'seqnum')
  title = f'CL Corner Bite {size}x{size} with score {scored}'
  tile_text = 'CoB'

  return dict(
    title=title,
    tile_text=tile_text,
    nodes=nodes,
    columns=columns,
    score=scored,
  )


def holey(size):
  """
  #####
  # # #
  #####
  # # #
  #####
  """
  size = 2 * size + 1

  board = []
  revealed = []
  constraints = []

  pos_to_id = lambda x, y: x + size * y

  for y in range(size):
    if y % 2 == 0:
      constraints.append([0, list(range(size * y, size * y + size))])  # horizontal solid
      constraints.append([0, list(range(y, size * size + y, size))])  # vertical solid

    for x in range(size):
      cell_id = pos_to_id(x, y)

      neighbors = []
      for dy in range(-1, 2):
        for dx in range(-1, 2):
          if dx == dy == 0:
            continue
          elif x + dx < 0 or x + dx >= size:
            continue
          elif y + dy < 0 or y + dy >= size:
            continue

          neighbors.append(pos_to_id(x + dx, y + dy))

      board.append([cell_id, '', neighbors])

      if x % 2 == 1 and y % 2 == 1:
        board[-1][1] = '.'
        revealed.append(cell_id)

  board.sort(key=lambda c: c[0] in revealed)  # praise be to Python's stable sort
  constraints.append([0, sorted(set(range(size ** 2)).difference(set(revealed)))])

  def sanity_check(compressed):  # takes a compressed string
    return True

  num = size ** 2  # total number of cells, revealed ones included (like the other templates)
  return dict(
    num=num,
    board=board,
    revealed=revealed,
    constraints=constraints,
    sanity_check=sanity_check,
  )


@template('holey', label='Holey', preview_args=(3,))
def holey_render(compressed, size):
  template = holey(size)
  board = template['board']
  revealed, constraints = template['revealed'], template['constraints']
  size = 2 * size + 1

  tile_size = 10
  points = '-{s},-{s},{s},-{s},{s},{s},-{s},{s}'.format(s=0.96 * tile_size / 2)

  nodes = []
  columns = []
  mapped = dict()

  for i in range(size ** 2):
    c = compressed[i] if i < len(compressed) else '.'
    board[i][1] = c
    mapped[board[i][0]] = c

    nodes.append(dict(
      id=board[i][0],
      neighbors=board[i][2],
      position=((board[i][0] % size) * tile_size, (board[i][0] // size) * tile_size),
      has_mine=c == '*',
      secret=c == '?',
      revealed=board[i][0] in revealed,
      points=points,
    ))

  for j in range(size // 2 + 1):
    # horizontal column hints
    constraints[2 * j][0] = sum([mapped[i] == '*' for i in constraints[2 * j][1]])
    columns.append(dict(
      ids=constraints[2 * j][1],
      text_location=(-tile_size, 2 * j * tile_size),
    ))

    # vertical column hints
    constraints[2 * j + 1][0] = sum([mapped[i] == '*' for i in constraints[2 * j + 1][1]])
    columns.append(dict(
      ids=constraints[2 * j + 1][1],
      text_location=(2 * j * tile_size, -tile_size),
    ))

  constraints[-1][0] = compressed.count('*')

  result = Puzzle(board, revealed, constraints).solve()
  scored = score(result, 'seqnum')
  title = f'Holey {size}x{size} with score {scored}'
  tile_text = 'HOL'

  return dict(
    title=title,
    tile_text=tile_text,
    nodes=nodes,
    columns=columns,
    score=scored,
  )


def L_shape_grid(compressed, size, depth):
  """
    33
    13
  2114
  2244
  """
  size, depth = int(size), int(depth)
  side_length = 2 * size * 2 ** depth
  points = '-{s},-{s},{s},-{s},{s},{s},-{s},{s}'.format(s=0.96 / 2)
  cindex = 0

  board = []
  revealed = []
  constraints = []
  nodes = []
  columns = []
  colors = [
    dict(ids=[], color='RED', is_dark=False),
    dict(ids=[], color='ORANGE', is_dark=False),
    dict(ids=[], color='GREEN', is_dark=False),
    dict(ids=[], color='BLUE', is_dark=False),
  ]

  id_map = dict()
  for y in range(side_length):
    for x in range(side_length):
      if x < side_length // 2 - 1 and y < side_length // 2 - 1:
        continue
      else:
        id_map[(x, y)] = len(id_map)

  pos_to_id = lambda x, y: id_map.get((x, y))

  for y in range(side_length):
    for x in range(side_length):
      if x < side_length // 2 - 1 and y < side_length // 2 - 1:
        continue

      cell_id = pos_to_id(x, y)
      neighbors = []

      for dy in range(-1, 2):
        for dx in range(-1, 2):
          if dx == dy == 0:
            continue

          neighbor_id = pos_to_id(x + dx, y + dy)
          if neighbor_id is not None:  # id 0 is a real cell - don't drop it (0 is falsy)
            neighbors.append(neighbor_id)

      if x < side_length // 2 and y < side_length // 2:
        what = '.'
        revealed.append(cell_id)
      else:
        what = compressed[cindex] if compressed else ''
        cindex += 1

        temp_x, temp_y, threshold = x, y, side_length // 4

        for i in range(depth):
          if threshold <= temp_x < 3 * threshold and threshold <= temp_y < 3 * threshold:
            if i == depth - 1:
              colors[0]['ids'].append(cell_id)
            else:
              temp_x -= threshold
              temp_y -= threshold

          elif temp_x < threshold * 2:
            if i == depth - 1:
              colors[1]['ids'].append(cell_id)
            else:
              temp_x, temp_y = temp_y - threshold * 2, threshold * 2 - temp_x - 1

          elif temp_y < threshold * 2:
            if i == depth - 1:
              colors[2]['ids'].append(cell_id)
            else:
              temp_x, temp_y = threshold * 2 - temp_y - 1, temp_x - threshold * 2

          else:
            if i == depth - 1:
              colors[3]['ids'].append(cell_id)
            else:
              temp_x -= threshold * 2
              temp_y -= threshold * 2

          threshold //= 2

      board.append([cell_id, what, neighbors])

      if compressed:
        nodes.append(dict(
          id=cell_id,
          neighbors=neighbors,
          position=(x, y),
          has_mine=what == '*',
          secret=what == '?',
          revealed=cell_id in revealed,
          points=points,
        ))

  constraints.append([sum([c[1] == '*' for c in board]), [c[0] for c in board if c[0] not in revealed]])

  for color in colors:
    constraints.append([sum(board[n][1] == '*' for n in color['ids']), color['ids']])

  # Total number of cells, revealed ones included (like the other templates).
  # The excluded corner is a (side/2 - 1) square, not side/2, so count the board
  # directly instead of a closed-form guess - otherwise the generator sizes its
  # candidate strings wrong and replace_cells() raises a KeyError.
  num = len(board)
  board.sort(key=lambda c: c[0] in revealed)  # praise be to Python's stable sort

  if not compressed:
    return dict(
      num=num,
      board=board,
      revealed=revealed,
      constraints=constraints,
    )
  else:
    result = Puzzle(board, revealed, constraints).solve()
    scored = score(result, 'seqnum')
    title = f'L-shape {size}-{depth} with score {scored}'
    tile_text = 'L'

    return dict(
      title=title,
      tile_text=tile_text,
      nodes=nodes,
      columns=columns,
      colors=colors,
      score=scored,
    )


def _simple_render(template, compressed, title_fmt, size, tile_text):
  """Shared render body for the grid/tiling templates below.

  Fills the board from the compressed string, recomputes every constraint count,
  builds the render nodes (a single polygon shape, or a per-cell one via
  `points_of`), solves for the score and returns the render dict. The template's
  make function stashes the geometry (`coords`, `points`/`points_of`), line hints
  (`columns`) and color groups (`colors`), so make and render never diverge.
  """
  num, board = template['num'], template['board']
  revealed, constraints = template['revealed'], template['constraints']
  coords = template['coords']
  points = template.get('points')
  points_of = template.get('points_of')
  columns, colors = template['columns'], template['colors']

  # the generator's compressed string leaves out revealed cells; writer.py may
  # pass the full string. These templates have no revealed cells, but guard anyway.
  if len(compressed) != num:
    remaining = iter(compressed)
    compressed = ''.join('.' if i in revealed else next(remaining) for i in range(num))

  revealed_set = set(revealed)
  nodes = []
  for i in range(num):
    board[i][1] = compressed[i]
    nodes.append(dict(
      id=i,
      neighbors=board[i][2],
      position=coords[i],
      has_mine=compressed[i] == '*',
      secret=compressed[i] == '?',
      revealed=i in revealed_set,
      points=points if points is not None else points_of[i],
    ))

  for constraint in constraints:
    constraint[0] = sum(compressed[k] == '*' for k in constraint[1])

  result = Puzzle(board, revealed, constraints).solve()
  scored = score(result, 'seqnum')

  return dict(
    title=title_fmt.format(size=size, score=scored),
    tile_text=tile_text,
    nodes=nodes,
    columns=columns,
    colors=colors,
    score=scored,
  )


def _line_hint_collector():
  """A deduplicating collector for optional line hints.

  Returns (constraints, columns, place): `place(ids, location)` records a line
  hint (a [0, ids] constraint plus a column at that text_location) unless an
  earlier hint already claimed that spot, so two numbers are never stacked.
  Shared by the masked-grid helper and the hexagon template - their geometries
  differ, but the overlap-suppression bookkeeping is the same. Locations are
  rounded so near-identical spots (hex float coords) collide; integer grid
  coords are unaffected.
  """
  constraints = []
  columns = []
  used = set()

  def place(ids, location):
    key = (round(location[0], 1), round(location[1], 1))
    if key in used:  # another line already put a number here
      return
    used.add(key)
    constraints.append([0, ids])
    columns.append(dict(ids=ids, text_location=location))

  return constraints, columns, place


def _grid_line_hints(id_of, tile_size):
  """Row and column line hints for a masked square grid, without overlaps.

  `id_of` maps (x, y) -> cell id. Returns (constraints, columns): a line hint for
  each row and each column that has cells, except any whose number would land
  where another hint already sits (which happens along diagonal / staircase
  edges, e.g. the re-entrant corners of 'cross' or the slopes of 'diamond').
  Unlike combination_lock, these row/column counts are therefore offered only
  where they fit - optional, not mandatory on every line - so the numbers are
  never stacked on top of each other.
  """
  xs = [x for x, _y in id_of]
  ys = [y for _x, y in id_of]
  width, height = max(xs) + 1, max(ys) + 1

  constraints, columns, place = _line_hint_collector()

  for y in range(height):
    cells = [x for x in range(width) if (x, y) in id_of]
    if cells:
      place([id_of[(x, y)] for x in cells], ((min(cells) - 1) * tile_size, y * tile_size))
  for x in range(width):
    cells = [y for y in range(height) if (x, y) in id_of]
    if cells:
      place([id_of[(x, y)] for y in cells], (x * tile_size, (min(cells) - 1) * tile_size))

  return constraints, columns


def _masked_square_grid(keep, side, tile_size=10):
  """Shared construction for the masked square-grid templates (cross, diamond).

  `keep(x, y)` selects which cells of a `side` x `side` grid are present; ids are
  assigned row-major. Returns (id_of, board, coords, points, constraints,
  columns): king-move (8-way) adjacency among the present cells, a square tile
  shape, and the optional non-overlapping row/column line hints. The caller adds
  its own color groups and the board total to `constraints`.
  """
  id_of = {}
  for y in range(side):
    for x in range(side):
      if keep(x, y):
        id_of[(x, y)] = len(id_of)
  num = len(id_of)

  points = '-{s},-{s},{s},-{s},{s},{s},-{s},{s}'.format(s=0.96 * tile_size / 2)

  board = [None] * num
  coords = {}
  for (x, y), cid in id_of.items():
    neighbors = []
    for dy in range(-1, 2):
      for dx in range(-1, 2):
        if dx == dy == 0:
          continue
        nb = id_of.get((x + dx, y + dy))
        if nb is not None:
          neighbors.append(nb)
    board[cid] = [cid, '', neighbors]
    coords[cid] = (x * tile_size, y * tile_size)

  constraints, columns = _grid_line_hints(id_of, tile_size)
  return id_of, board, coords, points, constraints, columns


def octagons(size):
  """A size x size grid of octagons with small square 'connector' tiles filling
  the diagonal gaps - the truncated-square (4.8.8) tiling that is Tametsi's
  signature octagon look (cf. the Girih, Windmill and Satellite bonus levels).
  The square connectors are tinted in concentric color rings."""
  n = int(size)
  num_oct = n * n
  num = num_oct + (n - 1) * (n - 1)
  oct_id = lambda i, j: j * n + i
  sq_id = lambda i, j: num_oct + j * (n - 1) + i

  # Geometry: octagons (squares with cut corners) on a grid of spacing D, with a
  # small diamond connector in each diagonal gap. The corner cut is smaller than
  # a regular octagon's (~0.586 a), so the octagons read as rounded squares and
  # the connectors stay small - matching Tametsi's own octagon levels. Every tile
  # is inset by `shrink` so neighbors are separated by a thin seam (like the
  # square tiles in the other templates) instead of touching edge to edge, which
  # looks like one solid block in game.
  a = 1.0            # octagon half-width; spacing D places octagons a seam apart
  cut = 0.59         # corner cut; smaller cut -> squarer octagons, smaller connectors
  h = a - cut        # half-length of each flat edge
  D = 2 * a
  shrink = 0.97
  sa, sh, sc = a * shrink, h * shrink, cut * shrink
  oct_points = '{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{}'.format(
    sh, -sa, sa, -sh, sa, sh, sh, sa, -sh, sa, -sa, sh, -sa, -sh, -sh, -sa)
  sq_points = '{},{},{},{},{},{},{},{}'.format(0, -sc, sc, 0, 0, sc, -sc, 0)

  board = [None] * num
  coords = {}
  points_of = {}

  for j in range(n):
    for i in range(n):
      cid = oct_id(i, j)
      neighbors = []
      if i > 0:
        neighbors.append(oct_id(i - 1, j))
      if i < n - 1:
        neighbors.append(oct_id(i + 1, j))
      if j > 0:
        neighbors.append(oct_id(i, j - 1))
      if j < n - 1:
        neighbors.append(oct_id(i, j + 1))
      for gi in (i - 1, i):
        for gj in (j - 1, j):
          if 0 <= gi < n - 1 and 0 <= gj < n - 1:
            neighbors.append(sq_id(gi, gj))
      board[cid] = [cid, '', neighbors]
      coords[cid] = (i * D, j * D)
      points_of[cid] = oct_points

  for j in range(n - 1):
    for i in range(n - 1):
      cid = sq_id(i, j)
      neighbors = [oct_id(i, j), oct_id(i + 1, j), oct_id(i, j + 1), oct_id(i + 1, j + 1)]
      board[cid] = [cid, '', neighbors]
      coords[cid] = (i * D + a, j * D + a)
      points_of[cid] = sq_points

  revealed = []
  constraints = []
  columns = []

  # octagon rows and columns as line hints
  for j in range(n):
    ids = [oct_id(i, j) for i in range(n)]
    constraints.append([0, ids])
    columns.append(dict(ids=ids, text_location=(-D, j * D)))
  for i in range(n):
    ids = [oct_id(i, j) for j in range(n)]
    constraints.append([0, ids])
    columns.append(dict(ids=ids, text_location=(i * D, -D)))

  # concentric color rings over the diamond connectors
  ring_colors = ['GREEN', 'BLUE', 'RED']
  groups = {}
  mid = (n - 2) / 2.0
  for j in range(n - 1):
    for i in range(n - 1):
      ring = int(round(max(abs(i - mid), abs(j - mid))))
      groups.setdefault(ring_colors[ring % len(ring_colors)], []).append(sq_id(i, j))
  colors = []
  for col in ring_colors:
    if groups.get(col):
      constraints.append([0, groups[col]])
      colors.append(dict(ids=groups[col], color=col, is_dark=False))

  constraints.append([0, list(range(num))])  # total

  def sanity_check(compressed):  # takes a compressed string
    return True

  return dict(
    num=num,
    board=board,
    revealed=revealed,
    constraints=constraints,
    sanity_check=sanity_check,
    coords=coords,
    points_of=points_of,
    columns=columns,
    colors=colors,
  )


@template('octagons', label='Octagons', preview_args=(6,))
def octagons_render(compressed, size):
  return _simple_render(octagons(size), compressed,
                        'Octagons {size}x{size} with score {score}', size, 'OCT')


def cross(size):
  """A plus/cross of square tiles: a 3*size by 3*size grid with the four
  size x size corners removed. The four arms and the center square are tinted in
  five colors - a 4-fold-symmetric design in the spirit of the bonus levels."""
  n = int(size)
  side = 3 * n

  def keep(x, y):
    return (n <= x < 2 * n) or (n <= y < 2 * n)

  # Row/column hints are optional and placed without overlap (full rows + columns
  # are mandatory only for combination_lock).
  id_of, board, coords, points, constraints, columns = _masked_square_grid(keep, side)
  num = len(id_of)
  revealed = []

  # five color regions: four arms + center
  groups = {'RED': [], 'GREEN': [], 'BLUE': [], 'ORANGE': [], 'VIOLET': []}
  for (x, y), cid in id_of.items():
    in_col = n <= x < 2 * n
    in_row = n <= y < 2 * n
    if in_col and in_row:
      groups['VIOLET'].append(cid)   # center
    elif in_col and y < n:
      groups['RED'].append(cid)      # top arm
    elif in_col:
      groups['GREEN'].append(cid)    # bottom arm
    elif x < n:
      groups['BLUE'].append(cid)     # left arm
    else:
      groups['ORANGE'].append(cid)   # right arm
  colors = []
  for col in ['RED', 'GREEN', 'BLUE', 'ORANGE', 'VIOLET']:
    constraints.append([0, groups[col]])
    colors.append(dict(ids=groups[col], color=col, is_dark=False))

  constraints.append([0, list(range(num))])  # total

  def sanity_check(compressed):  # takes a compressed string
    return True

  return dict(
    num=num,
    board=board,
    revealed=revealed,
    constraints=constraints,
    sanity_check=sanity_check,
    coords=coords,
    points=points,
    columns=columns,
    colors=colors,
  )


@template('cross', label='Cross', preview_args=(3,))
def cross_render(compressed, size):
  return _simple_render(cross(size), compressed,
                        'Cross {size} with score {score}', size, 'CRS')


def diamond(size):
  """A diamond of square tiles: every grid cell within Manhattan distance `size`
  of the center is kept, giving a 45-degree-rotated square silhouette. Tinted in
  concentric diamond rings - a target in the spirit of the bonus levels."""
  n = int(size)
  side = 2 * n + 1
  cx = cy = n

  def keep(x, y):
    return abs(x - cx) + abs(y - cy) <= n

  # Row/column hints are optional and placed without overlap (full rows + columns
  # are mandatory only for combination_lock).
  id_of, board, coords, points, constraints, columns = _masked_square_grid(keep, side)
  num = len(id_of)
  revealed = []

  # concentric diamond rings cycling through a handful of colors
  ring_colors = ['ORANGE', 'BLUE', 'GREEN']
  groups = {}
  for (x, y), cid in id_of.items():
    ring = abs(x - cx) + abs(y - cy)
    groups.setdefault(ring_colors[ring % len(ring_colors)], []).append(cid)
  colors = []
  for col in ring_colors:
    if groups.get(col):
      constraints.append([0, groups[col]])
      colors.append(dict(ids=groups[col], color=col, is_dark=False))

  constraints.append([0, list(range(num))])  # total

  def sanity_check(compressed):  # takes a compressed string
    return True

  return dict(
    num=num,
    board=board,
    revealed=revealed,
    constraints=constraints,
    sanity_check=sanity_check,
    coords=coords,
    points=points,
    columns=columns,
    colors=colors,
  )


@template('diamond', label='Diamond', preview_args=(6,))
def diamond_render(compressed, size):
  return _simple_render(diamond(size), compressed,
                        'Diamond {size} with score {score}', size, 'DIA')


def hexagon(size):
  """A big hexagon tiled with regular hexagons - the honeycomb look of Tametsi's
  hex levels. `size` is the radius: all hexes within hex-distance `size` of the
  center are kept, giving 3*size*(size+1)+1 cells. Adjacency is the 6-way hex
  neighborhood (axial coordinates). Line hints run along all three hex axes (the
  rows and the two diagonals), and concentric hexagonal rings are tinted in a few
  colors - a honeycomb target in the spirit of the bonus levels."""
  n = int(size)
  R = 10.0           # hex circumradius (center to vertex)
  shrink = 0.93      # inset so neighbors show a thin seam instead of touching
  sqrt3 = 3 ** 0.5

  # Axial coordinates (q, r); a cell is kept when its hex-distance from the
  # center is <= n. Cube distance = (|q| + |r| + |q + r|) / 2.
  dist = lambda q, r: (abs(q) + abs(r) + abs(q + r)) // 2
  cells = [(q, r) for q in range(-n, n + 1) for r in range(-n, n + 1)
           if dist(q, r) <= n]
  cells.sort(key=lambda qr: (qr[1], qr[0]))  # row-major (by r, then q) -> ids 0..num-1
  id_of = {qr: i for i, qr in enumerate(cells)}
  num = len(id_of)

  # Pointy-top hex: vertices top and bottom, flat edges left and right.
  pixel = lambda q, r: (sqrt3 * R * (q + r / 2.0), 1.5 * R * r)
  s = R * shrink
  hx = sqrt3 / 2 * s
  points = '{},{},{},{},{},{},{},{},{},{},{},{}'.format(
    0, s, -hx, s / 2, -hx, -s / 2, 0, -s, hx, -s / 2, hx, s / 2)

  board = [None] * num
  coords = {}
  directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
  for (q, r), cid in id_of.items():
    neighbors = []
    for dq, dr in directions:
      nb = id_of.get((q + dq, r + dr))
      if nb is not None:  # id 0 is a real cell - don't drop it (0 is falsy)
        neighbors.append(nb)
    board[cid] = [cid, '', neighbors]
    coords[cid] = pixel(q, r)

  revealed = []
  constraints, columns, place = _line_hint_collector()

  # Three line families, one hint per line, placed just beyond one end *along the
  # line* so the number always lands outside the board. Overlaps at shared corners
  # are skipped by `place`, so no two numbers are ever stacked.
  by_r, by_q, by_s = {}, {}, {}
  for (q, r) in cells:
    by_r.setdefault(r, []).append((q, r))
    by_q.setdefault(q, []).append((q, r))
    by_s.setdefault(q + r, []).append((q, r))

  for group in sorted(by_r.values()):            # rows (constant r): left end
    group.sort()
    q0, r0 = group[0]
    place([id_of[c] for c in group], pixel(q0 - 1, r0))
  for group in sorted(by_q.values()):            # diagonal (constant q): top end
    group.sort(key=lambda c: c[1])
    q0, r0 = group[0]
    place([id_of[c] for c in group], pixel(q0, r0 - 1))
  for group in sorted(by_s.values()):            # diagonal (constant q+r): upper end
    group.sort(key=lambda c: c[1])
    q0, r0 = group[0]                             # min r on the line -> max q
    place([id_of[c] for c in group], pixel(q0 + 1, r0 - 1))

  # Concentric hexagonal rings, cycling through a few colors (like the diamond).
  ring_colors = ['GREEN', 'BLUE', 'VIOLET']
  groups = {}
  for (q, r), cid in id_of.items():
    groups.setdefault(ring_colors[dist(q, r) % len(ring_colors)], []).append(cid)
  colors = []
  for col in ring_colors:
    if groups.get(col):
      constraints.append([0, groups[col]])
      colors.append(dict(ids=groups[col], color=col, is_dark=False))

  constraints.append([0, list(range(num))])  # total

  def sanity_check(compressed):  # takes a compressed string
    return True

  return dict(
    num=num,
    board=board,
    revealed=revealed,
    constraints=constraints,
    sanity_check=sanity_check,
    coords=coords,
    points=points,
    columns=columns,
    colors=colors,
  )


@template('hexagon', label='Hexagon', preview_args=(3,))
def hexagon_render(compressed, size):
  return _simple_render(hexagon(size), compressed,
                        'Hexagon {size} with score {score}', size, 'HEX')


def clone(compressed, filename):
  contents = None
  with open(filename, encoding='utf-8') as f:
    contents = f.read()

  puzzle, name, reverse_id_map = load(contents)
  board = puzzle.board
  revealed = puzzle.revealed
  constraints = puzzle.og_constraints

  num = len(board)
  board.sort(key=lambda c: c[0] in revealed)  # praise be to Python's stable sort

  if not compressed:
    return dict(
      num=num,
      board=board,
      revealed=revealed,
      constraints=constraints,
    )
  else:
    replace_cells(board, revealed, constraints, compressed)
    puzzle = Puzzle(board, revealed, constraints)
    result = puzzle.solve()
    scored = score(result, 'seqnum')
    title = f'Cloned "{name}" with score {scored}'
    tile_text = 'CLO'

    data = extract(contents)
    num_revealed = 0
    for index, node in enumerate(data['nodes']):
      if index in revealed:
        node['revealed'] = True
        num_revealed += 1
      else:
        node['has_mine'] = compressed[index - num_revealed] == '*'
        node['secret'] = compressed[index - num_revealed] == '?'

    return dict(
      title=title,
      tile_text=tile_text,
      score=scored,
      nodes=data['nodes'],
      columns=data['columns'],
      colors=data['colors'],
    )


def custom(compressed, filename):
  """A hand-built board shape from the level editor (see custom_levels.py).

  Like `clone`, this is a single combined function: the make path (no compressed
  string) returns the board geometry plus auto-derived, non-overlapping row/column
  line hints so the generator can actually solve it, and the render path (a
  compressed string given) fills the cells in, solves for the score and returns
  the render fields. Only the SHAPE (plus which cells start revealed) is stored;
  the generator alone places the mines.

  v1 handles the square grid. The stored `shape` field is the extension point for
  future tile shapes - add another geometry branch here and the rest of the
  pipeline (generator, writer, picker) is unchanged.
  """
  shape = custom_levels.load_shape(filename)
  tile_size = shape['tile_size']

  cells = [(cell['x'], cell['y']) for cell in shape['cells']]
  if not cells:
    raise ValueError(f'custom shape has no cells: {filename}')
  revealed_coords = {(c['x'], c['y']) for c in shape['cells'] if c['revealed']}

  # Normalise to the origin; the absolute offset in the editor does not matter.
  min_x = min(x for x, _ in cells)
  min_y = min(y for _, y in cells)
  keep_set = {(x - min_x, y - min_y) for x, y in cells}
  rev_set = {(x - min_x, y - min_y) for x, y in revealed_coords}
  side = max(max(x for x, _ in keep_set), max(y for _, y in keep_set)) + 1

  # Reuse the masked-square-grid builder (8-way adjacency, square tiles, optional
  # non-overlapping row/column line hints) that 'cross' and 'diamond' use.
  id_of, board, coords, points, constraints, columns = _masked_square_grid(
    lambda x, y: (x, y) in keep_set, side, tile_size)
  num = len(id_of)
  revealed = sorted(id_of[coord] for coord in rev_set)
  colors = []

  constraints.append([0, list(range(num))])  # total

  if not compressed:
    # sanity_check is optional for gradient_ascent; revealed cells are already
    # kept out of the candidate string, so a trivial check is enough here.
    def sanity_check(_compressed):
      return True

    return dict(
      num=num,
      board=board,
      revealed=revealed,
      constraints=constraints,
      sanity_check=sanity_check,
      coords=coords,
      points=points,
      columns=columns,
      colors=colors,
    )

  # No ':' in the title - writer.py turns the title into a filename and a colon
  # is illegal on Windows.
  name = os.path.splitext(os.path.basename(filename))[0]
  return _simple_render(
    dict(num=num, board=board, revealed=revealed, constraints=constraints,
         coords=coords, points=points, columns=columns, colors=colors),
    compressed, 'Custom {size} with score {score}', name, 'CUS')


def replace_cells(board, revealed, constraints, compressed):
  # compressed only describes the cells that are NOT revealed, in board order
  mapped = dict()
  revealed_ids = set(revealed)
  unrevealed_cells = [cell for cell in board if cell[0] not in revealed_ids]

  for cell, what in zip(unrevealed_cells, compressed):
    cell[1] = what
    mapped[cell[0]] = what

  for cell in board:
    if cell[0] in revealed_ids:
      cell[1] = '.'
      mapped[cell[0]] = '.'

  for constraint in constraints:
    constraint[0] = sum([mapped[i] == '*' for i in constraint[1]])


# l_shape_grid and clone are single combined functions (make when compressed is
# None, render otherwise), so they are registered directly rather than via the
# @template decorator above.
register_template('l_shape_grid', partial(L_shape_grid, None), L_shape_grid,
                  label='L-Shape Grid', preview_args=(2, 2))
register_template('clone', partial(clone, None), clone, label='Clone')
register_template('custom', partial(custom, None), custom, label='Custom')


def make_template(method, *args, **kwargs):
  return TEMPLATES[method]['make'](*args, **kwargs)


def render_template(method, compressed, *args, **kwargs):
  return TEMPLATES[method]['render'](compressed, *args, **kwargs)


def check_template(name, *args):
  """Validate a template's structure and sample its solvability.

  Checks that cell ids are a contiguous 0..num-1 range, that every neighbor link
  is in range and symmetric, that constraints and revealed reference real cells,
  that the render builds, and that a few light (low-mine) layouts actually solve.
  Prints a short report and returns the list of problems (empty if all good).
  """
  import random

  if not args:
    args = TEMPLATES[name]['preview_args']
  if args is None:
    # e.g. 'clone' has no fixed shape / default args, so it can't be checked blind
    print(f"{name}: no default check args - pass them explicitly "
          f"(e.g. 'python templater.py --check {name} <args>')")
    return [f'{name} has no preview_args; supply args to --check']
  data = make_template(name, *args)
  num = data['num']
  board = data['board']
  revealed = data['revealed']
  constraints = data['constraints']

  problems = []
  id_set = set(cell[0] for cell in board)
  if sorted(id_set) != list(range(num)):
    problems.append(f'cell ids are not a contiguous 0..{num - 1} range')
  by_id = {cell[0]: cell for cell in board}
  for cid, _what, neighbors in board:
    for nb in neighbors:
      if nb not in id_set:
        problems.append(f'cell {cid} has out-of-range neighbor {nb}')
      elif cid not in by_id[nb][2]:
        problems.append(f'neighbor link {cid} -> {nb} is not symmetric')
  for _count, group in constraints:
    for cid in group:
      if cid not in id_set:
        problems.append(f'constraint references unknown cell {cid}')
  if not set(revealed) <= id_set:
    problems.append('revealed contains unknown cell ids')

  try:
    render_template(name, '.' * num, *args)
  except Exception as error:  # noqa: BLE001 - report instead of crashing
    problems.append(f'render failed: {error}')

  solved, sample = 0, 12
  random.seed(0)
  for _ in range(sample):
    compressed = ''.join(random.choice('.....*') for _ in range(num - len(revealed)))
    replace_cells(board, revealed, constraints, compressed)
    result = Puzzle(board, revealed, constraints, max_inexact_stages=1).solve()
    if score(result, 'seqnum') >= 0:
      solved += 1

  print(f'{name}{args}: {num} cells, {len(constraints)} constraints, '
        f'solved {solved}/{sample} sampled layouts')
  for problem in problems:
    print('  PROBLEM:', problem)
  if not problems:
    print('  structure OK')
  return problems


if __name__ == '__main__':
  import sys

  argv = sys.argv[1:]
  if argv and argv[0] == '--check':
    rest = argv[1:]
    if rest:
      check_args = tuple(int(a) if a.isdigit() else a for a in rest[1:])
      sys.exit(1 if check_template(rest[0], *check_args) else 0)
    # no name given: check every template that has a fixed previewable shape
    bad = False
    for template_name, entry in TEMPLATES.items():
      if entry['preview_args'] is not None:
        bad = bool(check_template(template_name)) or bad
    sys.exit(1 if bad else 0)
  else:
    print('usage: python templater.py --check [<template> [args...]]')
    print('templates:', ', '.join(TEMPLATES))
