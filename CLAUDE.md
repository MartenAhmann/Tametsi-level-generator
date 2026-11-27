# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A level generator for the puzzle game **Tametsi**. It randomly generates mine
layouts for a given board shape (a "template"), solves each one with a logic
solver, scores the solve for difficulty, and writes the best layouts to Tametsi
`.puz` files. There is no build step and no test framework; everything runs as
standalone Python scripts.

## Commands

External dependencies: `jinja2` (used by `writer.py`) and `Pillow` (used by
`render.py`, and by the GUI for its clone previews). Install them with
`pip install jinja2 Pillow`. There is no requirements file. Pillow is optional
for the GUI: without it the window still works, but the clone gallery and
previews are disabled.

```powershell
# Generate: search for a hard layout of a template, scored by a scoring method.
# Runs forever (multiprocessing), printing the best layout ("compressed" string) so far. Ctrl+C to stop.
python generator.py combination_lock seqnum 6

# Write: turn a template + compressed string + template args into a .puz file
# (also written to latest.puz). Note the quotes — the string contains shell-significant chars.
python writer.py combination_lock "*....*.**.?....***.?.....**.......*." 6

# Test: solve and score puzzle files under test/ to validate them.
python tester.py            # all files in test/ (uses test/index if present, else every .puz)
python tester.py -1         # just the latest generated puzzle (latest.puz in the repo root)
python tester.py 94 --verbose   # one puzzle by its test/index id, with full solver debug output

# GUI: tkinter front-end that runs generator.py + writer.py as subprocesses and
# can copy results into Tametsi's puzzles folder. For the 'clone' template it also
# offers a gallery dropdown of every test/ level (with its rendering) next to the
# path field. Needs Pillow for the gallery/previews.
python gui.py

# Render: draw a .puz level's board shape (real tile polygons + color regions,
# no text) to a PNG. No args renders every test/*.puz into "Tametsi Bonus Puzzle Images/".
python render.py                         # all of test/ -> "Tametsi Bonus Puzzle Images/"
python render.py --templates             # each board template -> "Template Images/"
python render.py test/D20.puz out.png    # a single file

# Visualize a solve in the browser: writes visualizer_data.js, then open visualizer.html
python visualizer.py latest.puz
```

## Core data model (shared across modules)

Every module passes puzzles around as the same three Python structures. Learn
these before editing anything:

- **board**: `list` of `[cell_id, what, neighbors]` where `what` is one of
  `'.'` (no mine), `'*'` (mine), `'?'` (secret — revealed hint shows `?`), and
  `neighbors` is a list of neighboring `cell_id`s.
- **revealed**: `list` of `cell_id`s revealed at the start.
- **constraints**: `list` of `[mine_count, [cell_id, ...]]` — one per column hint,
  color hint, and the board-wide total. These are the given clues.

The **"compressed" string** is the generator's/writer's compact layout format: a
string of `.`, `*`, `?` characters. **Critical and non-obvious:** it describes
only the *unrevealed* cells, in board order — not the whole board. Helpers in
`templater.py` (`replace_cells`, and each template's `_render`) map it back onto
the full board, inserting `.` for revealed cells.

## Architecture / data flow

`generator.py` → `templater.py` → `solver.py` → `scorer.py`, then `writer.py` +
`leveltemplate.xml` emit the `.puz` file.

- **`solver.py`** — the heart of the project (and the genuinely hard part; see
  `TametsiSolver_explanation.md`). The `Puzzle(board, revealed, constraints,
  max_inexact_stages=-1)` class solves by deriving chains of inequalities
  (each a set of cells with a min/max mine count). Cell sets are encoded as
  Python bigints (one bit per cell) so union/intersection/difference are `|`,
  `&`, `& ~`. "Exact" inequalities (min == max) are derived first each round;
  "inexact" ones only when exact ones make no progress, and are purged
  aggressively. `max_inexact_stages` caps consecutive inexact rounds (the
  generator uses `1`). `solve()` returns `{solved, revealed, flagged, summary}`,
  where `summary` is the per-round record the scorer consumes.

- **`templater.py`** — defines board shapes. Each template is a *pair* of
  functions registered in `make_template` and `render_template`:
  - `<name>(size, ...)` returns the internal `dict(num, board, revealed,
    constraints, sanity_check)` used for generation. `sanity_check(compressed)`
    rejects degenerate layouts cheaply before solving.
  - `<name>_render(compressed, size, ...)` fills the board from the compressed
    string, solves it for the score, and returns the fields
    (`nodes`, `columns`, `colors`, `title`, `tile_text`, `score`) that the
    Jinja template needs.
  Existing templates: `combination_lock`, `cl_corner_bite`, `holey`,
  `l_shape_grid`, and `clone` (reuses the shape of an existing `.puz` via
  `loader.load` + `loader.extract`). To add a template, write both functions and
  register them in **both** dicts.

- **`scorer.py`** — `score(result, method)` returns `-1` for unsolved puzzles,
  else a non-negative difficulty score. Methods: `seqnum` (default everywhere)
  and `lognum`. Both read `result['summary']`, classifying each step as
  `trivial` / `exact` / `inexact`.

- **`generator.py`** — the search. `gradient_ascent` (the default `__main__`
  entry point) is a parallel hill-climb: worker processes each rebuild the
  template from scratch (nothing is pickled across the fork, so it works on
  Windows' spawn) and score candidates. `iteration` is an older single-process
  variant. Worker count comes from `TAMETSI_JOBS` env var, else a best-effort
  *physical* core count.

- **`loader.py`** — `load(contents)` parses a `.puz` file into a `Puzzle`;
  `extract(contents)` pulls raw node/column/color data for re-rendering (used by
  `clone`). Parsing is done with **regex, not an XML parser** — keep it that way.

- **`writer.py`** — renders `leveltemplate.xml` (Jinja2) with the fields from
  `render_template`. Puzzle IDs are the Unix timestamp, so IDs must be unique —
  rapid successive writes need >1s apart (the GUI enforces this).

- **`render.py`** — draws a `.puz` level to a PNG image of its board shape, using
  `loader.extract` for the node data. Each tile is its real polygon (the node's
  `<POLY><POINTS>` offset by `<POS>`), colored by its color-hint group (neutral
  if none, dimmed if pre-revealed); no text or hint numbers are drawn — only the
  shape + colors, which is exactly what `clone` reuses. Uses Pillow, supersampled
  then downscaled for smooth edges. `render_all()` writes
  `Tametsi Bonus Puzzle Images/<name>.png` for every `test/*.puz`; `ensure_render`
  caches by mtime. The GUI imports this module for its clone gallery thumbnails and
  preview. `Tametsi Bonus Puzzle Images/` is checked into the repo — run
  `python render.py` to rebuild it. **Note:** `test/` now holds only `index.txt`
  (the `.puz` files moved to `Tametsi Bonus puzzles/`), so `render.py` with no
  args and `tester.py` currently find no puzzles there until `test/` is
  repopulated; both still point at `test/` by design.
  - `render_contents(contents)` just parses with `loader.extract` and calls
    `render_data(data)`, which does the actual drawing from an already-parsed
    `{nodes, colors}` dict. That lets `render_templates()` (CLI `--templates`)
    draw the board-shape templates — it feeds each template's `_render` function
    an all-`.` layout (mines don't affect the shape) to get its node geometry,
    then writes `Template Images/<name>.png` for `combination_lock`,
    `cl_corner_bite`, `holey`, and `l_shape_grid`. `clone` is skipped (it has no
    fixed shape — it copies an input `.puz`). `Template Images/` is checked into
    the repo. `_floats` accepts tuple positions because template `_render`
    functions emit positions as tuples, not the lists `extract` returns.

## Conventions

- **Indentation is 2 spaces** throughout (not PEP 8's 4). Match it.
- **English only.** All code and GUI text — comments, docstrings, variable and
  function names, printed output, error messages, and anything shown in the
  tkinter GUI — must be written in English.
- The `.puz` XML format is documented field-by-field in `puzzle_format.md`; read
  it before touching `leveltemplate.xml` or the loader/writer.
- The repo **is** a git repository. Generated/user-local files are gitignored:
  `puzzles/`, `latest.puz`, `gui_config.json`, `visualizer_data.js`, `*.soln`,
  and the `game_puzzles` symlink.
- `test/`, `puzzles/`, `published/`, `Tametsi Bonus puzzles/`, and `game_puzzles/`
  (a symlink to Tametsi's install dir) hold `.puz` data, not code.
  - `Tametsi Bonus puzzles/` is the curated set of bonus levels (the `.puz` files
    that used to live in `test/`), checked into the repo.
  - `test/` now holds only `index.txt` — a single comment line documenting the
    `[id] [filename]` entry format (`#`-prefixed lines are comments that
    `tester.py` skips). Add real entries (and the `.puz` files) here to use it.
  - `Tametsi Bonus Puzzle Images/` holds generated PNG previews of the bonus
    levels; `Template Images/` holds generated PNG previews of the board-shape
    templates. Both are produced by `render.py` and checked into the repo.
