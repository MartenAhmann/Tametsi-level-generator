import os
import re
import sys
import random
import operator
import platform
import subprocess
import multiprocessing

from solver import Puzzle
from scorer import score
from templater import make_template, replace_cells


def score_candidate(board, revealed, constraints, compressed, score_method, verbose=False):
  replace_cells(board, revealed, constraints, compressed)
  puzzle = Puzzle(board, revealed, constraints, verbose=verbose, max_inexact_stages=1)
  result = puzzle.solve()
  return score(result, score_method), result


def random_compressed(num, probabilities):
  c = ''

  for index in range(num):
    r = random.random()
    if r <= probabilities[index][0]:
      c += '.'
    elif r <= probabilities[index][0] + probabilities[index][1]:
      c += '*'
    else:
      c += '?'

  return c


def iteration(template_method, score_method, *template_args, **template_kwargs):
  probabilities = [0.2, 0.5]  # First is for '.', second is for '*', and remainder is '?'
  data = make_template(template_method, *template_args, **template_kwargs)
  num = data['num']
  board = data['board']
  revealed = data['revealed']
  constraints = data['constraints']
  sanity_check = data.get('sanity_check', None)

  invert_sort = False  # True if lower scores are better
  if invert_sort:
    limit = float('inf')
    comp = operator.lt
  else:
    limit = 0
    comp = operator.gt

  threshold = limit
  round_num = 0
  scores = []

  while 1:
    prob_list = [probabilities] * num
    base = random_compressed(num, prob_list)

    while not sanity_check(base):
      base = random_compressed(num, prob_list)

    round_num += 1
    temp_threshold = score_candidate(board, revealed, constraints, base, score_method)[0]
    temp_best = base
    temp_result = None

    iteration = 0
    while 1:
      iteration += 1

      variants = {}

      for i in range(len(base)):
        for c in '.*?':
          if base[i] == c:
            continue

          v = base[:i] + c + base[i + 1:]

          if v not in variants and sanity_check(v):
            variants[v] = score_candidate(board, revealed, constraints, v, score_method)

      best = sorted(variants.items(), key=lambda x: x[1][0], reverse=invert_sort)[-1]

      if comp(best[1][0], temp_threshold):
        temp_best = best[0]
        temp_threshold = best[1][0]
        temp_result = best[1][1]

      else:
        break

    scores.append(temp_threshold)

    if len(scores) == 1 or comp(temp_threshold, 0.8 * threshold):
      probabilities[0] = (probabilities[0] + temp_best.count('.') / len(temp_best)) / 2
      probabilities[1] = (probabilities[1] + temp_best.count('*') / len(temp_best)) / 2

      output = 'Best of round {}: {} with score {}'.format(round_num, temp_best, temp_threshold)
      if comp(temp_threshold, limit):
        steps = ''.join(['T' if 'trivial' in step else 'E' if 'exact' in step else 'I' for step in temp_result['summary']])
        output += f' and steps {steps}'
      print(output)

    if comp(temp_threshold, threshold):
      probabilities[0] = temp_best.count('.') / len(temp_best)
      probabilities[1] = temp_best.count('*') / len(temp_best)
      threshold = temp_threshold
      print(' ^ Best so far!')


# ---------------------------------------------------------------------------
# Parallel helpers
#
# The solver is the slow part and is run thousands of times. Each solve is
# independent, so we hand them to several worker processes. Every worker rebuilds
# the template itself (so it has its own board, constraints and sanity_check and
# nothing has to be pickled across the fork), which also keeps this working on
# Windows, where processes are spawned rather than forked.
# ---------------------------------------------------------------------------

_WORKER = {}


def _worker_init(template_method, score_method, template_args):
  data = make_template(template_method, *template_args)
  revealed = data['revealed']
  unrevealed_ids = [cell[0] for cell in data['board'] if cell[0] not in set(revealed)]
  _WORKER.update(
    board=data['board'],
    revealed=revealed,
    constraints=data['constraints'],
    sanity_check=data.get('sanity_check', None),
    score_method=score_method,
    id_map={cell_id: index for index, cell_id in enumerate(unrevealed_ids)},
    num_unrevealed=data['num'] - len(revealed),
  )
  random.seed()  # give every process its own random stream


def _solve_one(candidate):
  """Score a single candidate. Used for the hill-climbing stage."""
  scored, result = score_candidate(
    _WORKER['board'], _WORKER['revealed'], _WORKER['constraints'], candidate, _WORKER['score_method'])
  return [scored, candidate, {'summary': result['summary']}]


def _trial_one(probabilities):
  """Produce one solved candidate, including the explode/retry loop.

  This mirrors the body of the trials loop below, but runs entirely inside a
  worker. It assumes higher scores are better (the default for gradient_ascent).
  """
  board = _WORKER['board']
  revealed = _WORKER['revealed']
  constraints = _WORKER['constraints']
  id_map = _WORKER['id_map']
  num_unrevealed = _WORKER['num_unrevealed']
  sanity_check = _WORKER['sanity_check']
  score_method = _WORKER['score_method']

  candidate = random_compressed(num_unrevealed, probabilities)
  attempts = 10
  scored, result = 0, None

  while attempts:
    attempts -= 1
    scored, result = score_candidate(board, revealed, constraints, candidate, score_method)
    if scored > 0:
      break

    result_known = result['revealed'].union(result['flagged'])
    boundary_question = set()
    boundary_unknown = set()
    all_unknown = set()

    for cell_id, what, neighbors in board:
      if cell_id in result['revealed'] and set(neighbors).difference(result_known):
        if what == '?':
          boundary_question.add(cell_id)
      elif cell_id not in result_known:
        all_unknown.add(cell_id)
        if set(neighbors).intersection(result_known):
          boundary_unknown.add(cell_id)

    exploded = list(candidate)
    if boundary_question:
      for cell_id in boundary_question:
        exploded[id_map[cell_id]] = '.'
    elif boundary_unknown:
      replacements = list(random_compressed(len(boundary_unknown), probabilities))
      for cell_id in boundary_unknown:
        exploded[id_map[cell_id]] = replacements.pop()
    else:
      replacements = list(random_compressed(len(all_unknown), probabilities))
      for cell_id in all_unknown:
        exploded[id_map[cell_id]] = replacements.pop()

    candidate = ''.join(exploded)
    if sanity_check and not sanity_check(candidate):
      continue

  return [scored, candidate, {'summary': result['summary'] if result else []}]


def _physical_cpu_count():
  """Best-effort count of PHYSICAL cores, ignoring SMT / Hyper-Threading.

  Pure CPU work like the solver gains little from the extra SMT threads, so the
  default uses the real cores. Falls back to a heuristic if detection fails.
  """
  # 1) psutil, if it happens to be installed
  try:
    import psutil
    count = psutil.cpu_count(logical=False)
    if count:
      return count
  except Exception:
    pass

  system = platform.system()
  try:
    if system == 'Linux':
      pairs = set()
      physical_id = None
      with open('/proc/cpuinfo') as cpuinfo:
        for line in cpuinfo:
          if line.startswith('physical id'):
            physical_id = line.split(':')[1].strip()
          elif line.startswith('core id'):
            pairs.add((physical_id, line.split(':')[1].strip()))
      if pairs:
        return len(pairs)

    elif system == 'Darwin':
      out = subprocess.run(['sysctl', '-n', 'hw.physicalcpu'], capture_output=True, text=True)
      if out.returncode == 0 and out.stdout.strip().isdigit():
        return int(out.stdout.strip())

    elif system == 'Windows':
      no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
      out = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         '(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum'],
        capture_output=True, text=True, creationflags=no_window)
      value = out.stdout.strip()
      if out.returncode == 0 and value.isdigit():
        return int(value)

      # older fallback: wmic (removed on the newest Windows, so guarded)
      out = subprocess.run(['wmic', 'cpu', 'get', 'NumberOfCores'],
                           capture_output=True, text=True, creationflags=no_window)
      numbers = [int(token) for token in out.stdout.split() if token.isdigit()]
      if numbers:
        return sum(numbers)
  except Exception:
    pass

  # 2) Heuristic: assume 2-way SMT when the logical count is an even number >= 4
  logical = os.cpu_count() or 1
  if logical >= 4 and logical % 2 == 0:
    return logical // 2
  return logical


def _resolve_jobs(jobs):
  if jobs is None:
    env = os.environ.get('TAMETSI_JOBS')
    jobs = int(env) if env and env.isdigit() else _physical_cpu_count()
  return max(1, int(jobs))


def gradient_ascent(template_method, score_method, *template_args, jobs=None, **template_kwargs):
  data = make_template(template_method, *template_args, **template_kwargs)
  num = data['num']
  board = data['board']
  revealed = data['revealed']
  constraints = data['constraints']
  sanity_check = data.get('sanity_check', None)

  # positions in a candidate string only cover the unrevealed cells
  unrevealed_ids = [cell[0] for cell in board if cell[0] not in set(revealed)]
  id_map = {cell_id: index for index, cell_id in enumerate(unrevealed_ids)}
  starting_probabilities = [0.5, 0.25]  # First is for '.', second is for '*', and remainder is '?'

  trials = 50
  best_of = 10

  invert_sort = False  # True if lower scores are better
  if not invert_sort:
    limit = 0
    comp = operator.gt
  else:
    limit = float('inf')
    comp = operator.lt

  round_num = 0
  best_score = 0
  num_unrevealed = num - len(revealed)
  probabilities = [starting_probabilities[:] for _ in range(num_unrevealed)]

  # Spread the independent solves across worker processes (see helpers above).
  jobs = _resolve_jobs(jobs)
  init_args = (template_method, score_method, template_args)
  if jobs > 1:
    pool = multiprocessing.Pool(jobs, initializer=_worker_init, initargs=init_args)
    parallel_map = pool.map
    print(f'Using {jobs} worker processes.')
  else:
    _worker_init(*init_args)  # set up the shared state for in-process use
    parallel_map = lambda func, items: [func(item) for item in items]

  while 1:
    round_num += 1

    # Trials: each worker produces one solved candidate (random start + explode loop).
    solved = parallel_map(_trial_one, [probabilities] * trials)

    top = sorted(solved, key=lambda x: x[0], reverse=invert_sort)[-best_of:]

    if comp(top[-1][0], 0.8 * best_score):
      # iteration stage - 1-char changes
      base_variant = top[-1]

      while 1:
        base_candidate = base_variant[1]

        # All single-character changes, in the same order as before, solved in parallel.
        variant_strings = []
        for index in range(num_unrevealed):
          for char in ['.', '?', '*']:
            if char == base_candidate[index]:
              continue
            variant_strings.append(base_candidate[:index] + char + base_candidate[index + 1:])

        variants = parallel_map(_solve_one, variant_strings)
        best_variant = sorted(variants, key=lambda x: x[0], reverse=invert_sort)[-1]
        if not comp(best_variant[0], base_variant[0]):
          break
        base_variant = best_variant

      output = f'Best of round {round_num}: {base_variant[1]} with score {base_variant[0]}'
      if comp(base_variant[0], limit):
        output = output + ' and steps ' + ''.join(['T' if 'trivial' in step else 'E' if 'exact' in step else 'I' for step in base_variant[2]['summary']])
      print(output)

      score_total = sum([_[0] for _ in top])
      for index in range(num_unrevealed):
        probabilities[index][0] = sum([s * (c[index] == '.') for s, c, r in top]) / score_total
        probabilities[index][1] = sum([s * (c[index] == '*') for s, c, r in top]) / score_total

      # print('new probabilities:', '; '.join('{:.3f},{:.3f}'.format(*p) for p in probabilities))

    if comp(top[-1][0], best_score):
      best_score = top[-1][0]
      print(' ^ Best so far!')

    if sum([p in [[0, 0], [0, 1], [1, 0]] for p in probabilities]) > 0.8 * len(probabilities):
      print('\n<restarting>\n')
      best_score = 0
      probabilities = [starting_probabilities[:] for _ in range(num_unrevealed)]


# python generator <template_name> <scoring_method> [arg1] [arg2] [...]

# there are two generation algorithms, 'iteration' and 'gradient_ascent';
# gradient_ascent is the default since it tends to produce better results faster
# both take a template name and scoring method, plus args for the template
# template name is one of those defined in templater.py
# scoring method is one of those defined in scorer.py

if __name__ == '__main__':
  print('argv:', sys.argv)  # useful for piping to a file and remembering what the command was

  # iteration('combination_lock', 'seqnum', size)
  # gradient_ascent('combination_lock', 'seqnum', size)
  # gradient_ascent('cl_corner_bite', 'seqnum', size)
  # gradient_ascent('holey', 'seqnum', size)
  # gradient_ascent('l_shape_grid', 'seqnum', *sys.argv[1:])
  args = [int(arg) if re.fullmatch(r'\d+', arg) else arg for arg in sys.argv[1:]]

  try:
    gradient_ascent(*args)
  except KeyboardInterrupt:
    print('^C interrupted!')
