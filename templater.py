from functools import partial
from solver import Puzzle
from scorer import score
from loader import load, extract


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
          if neighbor_id:
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


def make_template(method, *args, **kwargs):
  methods = dict(
    combination_lock=combination_lock,
    cl_corner_bite=cl_corner_bite,
    holey=holey,
    l_shape_grid=partial(L_shape_grid, None),
    clone=partial(clone, None),
  )

  return methods[method](*args, **kwargs)


def render_template(method, compressed, *args, **kwargs):
  methods = dict(
    combination_lock=combination_lock_render,
    cl_corner_bite=cl_corner_bite_render,
    holey=holey_render,
    l_shape_grid=L_shape_grid,
    clone=clone,
  )

  return methods[method](compressed, *args, **kwargs)
