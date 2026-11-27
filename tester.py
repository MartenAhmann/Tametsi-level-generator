import os
import sys
import time

from loader import load
from scorer import score

# The "test" folder is resolved relative to this file, not to the console's current working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(BASE_DIR, 'test')


def read_index():
  """Return a list of (id, filename).

  The file test/index consists of lines of the form "[id] [filename]".
  Windows often hides file extensions, so test/index.txt is accepted too.
  If there is no index file at all, every .puz file in the test folder is numbered in order.
  """
  if not os.path.isdir(TEST_DIR):
    raise SystemExit(f'The folder "{TEST_DIR}" does not exist. Create a "test" folder there with the .puz files.')

  for index_name in ('index', 'index.txt'):
    index_path = os.path.join(TEST_DIR, index_name)
    if os.path.isfile(index_path):
      entries = []
      with open(index_path, encoding='utf-8-sig') as index:
        for line in index:
          line = line.strip()
          if not line or line.startswith('#'):
            continue
          parts = line.split(None, 1)  # filenames may contain spaces
          if len(parts) != 2:
            raise SystemExit(f'Invalid line in {index_path}: "{line}" (expected: "[id] [filename]")')
          entries.append((parts[0], parts[1].strip()))
      return entries

  names = sorted(name for name in os.listdir(TEST_DIR) if name.lower().endswith('.puz'))
  if not names:
    raise SystemExit(f'Neither an index file nor .puz files found in "{TEST_DIR}".')
  print(f'No index file found in "{TEST_DIR}", using all .puz files there.')
  return [(str(number), name) for number, name in enumerate(names, 1)]


def run(level_id=None, verbose=False):
  # a shorthand to make it easy to test the latest puzzle you generated
  if level_id == '-1':
    # writer.py writes latest.puz to the repo root (next to this file), so point there directly.
    files = [('latest.puz', os.path.join(BASE_DIR, 'latest.puz'))]

  else:
    files = []
    for id, name in read_index():
      files.append((name, os.path.join(TEST_DIR, name)))

      if level_id and id == level_id:
        files = [(name, os.path.join(TEST_DIR, name))]
        break

  print('filenames:', [filename for filename, _ in files])
  for index, (filename, path) in enumerate(files):
    if not os.path.isfile(path):
      print(f'{index + 1:3} {filename:20}: file not found ({path})')
      continue

    with open(path, encoding='utf-8') as level:
      puzzle, name, reverse_id_map = load(level.read(), verbose=verbose)

    st = time.time()
    result = puzzle.solve()
    et = time.time()

    if verbose:
      print('result:', result)
      print('')
      for step in result['summary']:
        print(' ', step)

    if verbose and not result['solved']:
      flagged = ','.join([reverse_id_map[cell_id] for cell_id in result['flagged']])
      revealed = ','.join([reverse_id_map[cell_id] for cell_id in result['revealed']])
      print(f'P:_:{flagged}:{revealed}:n')

    scored = score(result, 'seqnum')
    print(f'{index + 1:3} {filename:20}: {et - st:.3f} seconds, solved {result["solved"]}, score {scored:.3f} - {name}')


# python tester.py [puzzle_id [--verbose]]
# with no args, this runs the scorer on all puzzles defined in /test/index
# with a puzzle id, this runs the scorer on that one (defined in /test/index)
# python tester.py -1 tests latest.puz in the project folder
# --verbose enables a ton of debug print statements

# NOTE THAT YOU NEED TO CREATE /test and put puzzle files in there
# the file /test/index is optional and formatted like:
#   puzzle_id puzzle_filename
# without it, every .puz file in /test is tested

if __name__ == '__main__':
  args = [arg for arg in sys.argv[1:] if arg != '--verbose']
  run(args[-1] if args else None, verbose=('--verbose' in sys.argv))
