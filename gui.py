"""
Tametsi Level Generator - desktop window

Start:  python gui.py

Runs generator.py in the background, collects the best patterns it finds
(only levels with a score above 0), creates the .puz file with writer.py and,
if you like, copies it straight into Tametsi's 'puzzles' folder.
Afterwards you only have to restart Tametsi.
"""

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

try:
  import tkinter as tk
  from tkinter import ttk, filedialog, messagebox
except ImportError:  # the core (without the window) stays importable
  tk = None

# Rendering is optional: without Pillow the clone picker falls back to a plain
# name dropdown and no previews, but the rest of the window still works.
try:
  import render
  from PIL import Image, ImageTk
  HAVE_RENDER = True
except Exception:  # noqa: BLE001 - any import trouble just disables the previews
  render = None
  Image = ImageTk = None
  HAVE_RENDER = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'gui_config.json')

THUMB_PX = 104     # thumbnail size in the clone picker gallery
PREVIEW_PX = 150   # size of the preview next to the file field

# Grid-based templates shown at the top of the picker. Each maps the internal
# generator name to (display label, size hint, template-image file name). The
# image files live in render.TEMPLATE_IMG_DIR ('Template Images'). 'clone' is
# not listed here: it is chosen by picking one of the bonus levels below the
# separator in the picker (each reuses that level's shape).
GRID_TEMPLATES = {
  'combination_lock': ('Combination Lock', 'n x n grid', 'Combination Lock.png'),
  'cl_corner_bite': ('CL Corner Bite', 'n x n grid, one corner revealed', 'CL Corner Bite.png'),
  'holey': ('Holey', 'size n gives a (2n+1) x (2n+1) grid', 'Holey.png'),
  'l_shape_grid': ('L-Shape Grid', 'recursive L shape, uses size + depth', 'L-Shape Grid.png'),
  'octagons': ('Octagons', 'n x n octagons with diamond connectors', 'Octagons.png'),
  'cross': ('Cross', 'plus shape, size n gives a 3n x 3n cross', 'Cross.png'),
  'diamond': ('Diamond', 'diamond of radius n ((2n+1) wide)', 'Diamond.png'),
}

# Templates that take a second 'depth' argument in addition to the size. For all
# others the depth box stays hidden and only the size is passed through.
DEPTH_TEMPLATES = {'l_shape_grid'}

# Example line printed by the generator:  Best of round 3: ....*..*?... with score 18 and steps TETE
BEST_RE = re.compile(r'Best of round (\d+): (\S+) with score (-?[\d.]+)')

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)  # no console window on Windows


def kill_process_tree(proc):
  """Kill a subprocess AND every process it spawned.

  The generator (generator.py -> gradient_ascent) starts a multiprocessing
  worker pool, so there are several child processes. Calling proc.terminate()
  would only end the top generator.py process and leave the pool workers running
  in the background, eating CPU. We therefore kill the whole process tree.
  """
  if proc is None or proc.poll() is not None:  # nothing (still) running
    return

  if os.name == 'nt':
    # taskkill walks the child tree; /T includes the worker pool, /F forces it.
    try:
      subprocess.run(
        ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
        creationflags=NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
      )
      return
    except OSError:
      pass  # fall through to the direct-kill fallback below
  else:
    # POSIX: the child runs in its own session (see start()), so one signal to
    # the process group reaches the generator and all of its workers.
    try:
      os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
      return
    except (ProcessLookupError, PermissionError, OSError):
      pass

  # Fallback: at least end the direct child if the tree kill was unavailable.
  try:
    proc.kill()
  except OSError:
    pass


# ----------------------------------------------------------------------------
# Core (no window)
# ----------------------------------------------------------------------------

class GeneratorRunner:
  """Starts generator.py as a subprocess and reports its output through a queue."""

  def __init__(self, template, size, events, depth=None):
    self.template = template
    self.size = size  # grid size, or the template file path for 'clone'
    self.depth = depth  # extra arg for templates that need one (e.g. l_shape_grid)
    self.events = events
    self.proc = None
    self.stopped = False

  def start(self):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    cmd = [sys.executable, '-u', 'generator.py', self.template, 'seqnum', str(self.size)]
    if self.depth is not None:
      cmd.append(str(self.depth))
    self.proc = subprocess.Popen(
      cmd,
      cwd=BASE_DIR,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      env=env,
      creationflags=NO_WINDOW,
      # POSIX: own session/process group so stop() can signal the whole tree.
      # (Ignored on Windows, where taskkill /T handles the tree instead.)
      start_new_session=(os.name != 'nt'),
    )
    threading.Thread(target=self._read, daemon=True).start()

  def _read(self):
    for raw in self.proc.stdout:
      line = raw.decode('utf-8', errors='replace').rstrip()
      if not line:
        continue
      self.events.put(('line', line))
      match = BEST_RE.search(line)
      if match:
        self.events.put(('result', int(match.group(1)), match.group(2), float(match.group(3))))
    self.proc.wait()
    self.events.put(('done', self.proc.returncode, self.stopped))

  def running(self):
    return self.proc is not None and self.proc.poll() is None

  def stop(self):
    self.stopped = True
    kill_process_tree(self.proc)  # ends generator.py AND its worker pool


_last_write = 0.0


def write_puzzle(template, pattern, size, depth=None):
  """Calls writer.py and returns the path of the generated .puz file."""
  global _last_write

  # The puzzle ID is the Unix time in seconds and has to be unique.
  wait = 1.1 - (time.time() - _last_write)
  if wait > 0:
    time.sleep(wait)

  cmd = [sys.executable, 'writer.py', template, pattern, str(size)]
  if depth is not None:
    cmd.append(str(depth))
  proc = subprocess.run(
    cmd,
    cwd=BASE_DIR,
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    creationflags=NO_WINDOW,
  )
  _last_write = time.time()

  if proc.returncode != 0:
    tail = '\n'.join(proc.stderr.strip().splitlines()[-4:])
    raise RuntimeError(f'writer.py failed:\n{tail}')

  names = [line.strip() for line in proc.stdout.splitlines() if line.strip().endswith('.puz')]
  if not names:
    raise RuntimeError('writer.py did not print a file name.')

  path = os.path.join(BASE_DIR, names[-1])
  if not os.path.isfile(path):
    raise RuntimeError(f'File not found: {path}')
  return path


def puzzles_dir_of(game_dir):
  """Tametsi's 'puzzles' folder (the user may enter either the game folder or the puzzles folder)."""
  game_dir = game_dir.strip().strip('"')
  if not game_dir:
    return ''
  if os.path.basename(os.path.normpath(game_dir)).lower() == 'puzzles':
    return game_dir
  return os.path.join(game_dir, 'puzzles')


def copy_to_game(path, game_dir):
  target_dir = puzzles_dir_of(game_dir)
  os.makedirs(target_dir, exist_ok=True)

  name = os.path.basename(path)
  dest = os.path.join(target_dir, name)
  if os.path.exists(dest):  # never overwrite anything
    stem, ext = os.path.splitext(name)
    dest = os.path.join(target_dir, f'{stem}_{time.strftime("%H%M%S")}{ext}')

  shutil.copy2(path, dest)
  return dest


def guess_game_dir():
  candidates = [
    r'C:\Program Files (x86)\Steam\steamapps\common\Tametsi',
    r'C:\Program Files\Steam\steamapps\common\Tametsi',
    r'D:\SteamLibrary\steamapps\common\Tametsi',
    os.path.expanduser('~/.steam/steam/steamapps/common/Tametsi'),
    os.path.expanduser('~/.local/share/Steam/steamapps/common/Tametsi'),
    os.path.expanduser('~/Library/Application Support/Steam/steamapps/common/Tametsi'),
  ]
  for candidate in candidates:
    if os.path.isdir(candidate):
      return candidate
  return ''


def load_config():
  try:
    with open(CONFIG_PATH, encoding='utf-8') as file:
      return json.load(file)
  except (OSError, ValueError):
    return {}


def save_config(config):
  try:
    with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
      json.dump(config, file, indent=2)
  except OSError:
    pass


# ----------------------------------------------------------------------------
# Window
# ----------------------------------------------------------------------------

class App:
  def __init__(self, root):
    self.root = root
    root.title('Tametsi Level Generator')
    root.minsize(760, 560)

    self.events = queue.Queue()
    self.runner = None
    self.run_info = None  # (template, size or file, depth or None) of the current/last run
    self.results = []  # dicts with round, pattern, score
    self.started_at = 0.0
    self.limit_seconds = 0
    self.target_score = 0
    self.stop_reason = ''

    config = load_config()

    self.template_var = tk.StringVar(value=config.get('template', 'combination_lock'))
    self.size_var = tk.IntVar(value=config.get('size', 2))
    self.depth_var = tk.IntVar(value=config.get('depth', 1))
    self.file_var = tk.StringVar(value=config.get('clone_file', ''))
    self.minutes_var = tk.IntVar(value=config.get('minutes', 0))
    self.target_var = tk.IntVar(value=config.get('target', 0))
    self.game_dir_var = tk.StringVar(value=config.get('game_dir') or guess_game_dir())
    self.copy_var = tk.BooleanVar(value=config.get('copy', True))
    self.status_var = tk.StringVar(value='Ready.')
    self.choice_var = tk.StringVar(value='')  # label of the current selection

    # Picker state
    self._thumb_cache = {}    # png path -> PhotoImage for the gallery (kept to avoid GC)
    self._preview_image = None
    self._picker = None       # the open gallery window, if any

    self._build()
    root.protocol('WM_DELETE_WINDOW', self.on_close)
    root.after(200, self.poll)

  def _build(self):
    pad = dict(padx=8, pady=4)
    main = ttk.Frame(self.root, padding=10)
    main.pack(fill='both', expand=True)

    settings = ttk.LabelFrame(main, text='Settings', padding=8)
    settings.pack(fill='x')
    settings.columnconfigure(3, weight=1)

    # The level/template is chosen in a visual picker (templates at the top, then
    # a separator, then the Tametsi bonus levels) instead of a dropdown.
    ttk.Label(settings, text='Level template:').grid(row=0, column=0, sticky='w', **pad)
    self.choose_button = ttk.Button(settings, text='Choose…', command=self.open_picker)
    self.choose_button.grid(row=0, column=1, sticky='w', **pad)
    self.choice_label = ttk.Label(settings, textvariable=self.choice_var)
    self.choice_label.grid(row=0, column=2, columnspan=2, sticky='w', **pad)

    ttk.Label(settings, text='Size:').grid(row=1, column=0, sticky='w', **pad)
    self.size_spin = ttk.Spinbox(settings, from_=2, to=30, textvariable=self.size_var, width=6)
    self.size_spin.grid(row=1, column=1, sticky='w', **pad)
    # The size hint and the depth control share row 1, columns 2-3: update_hint()
    # shows the depth box only for templates in DEPTH_TEMPLATES and the hint
    # otherwise, so the two never overlap.
    self.size_hint_label = ttk.Label(settings, text='Large grids get very slow.')
    self.size_hint_label.grid(row=1, column=2, columnspan=2, sticky='w', **pad)
    self.depth_label = ttk.Label(settings, text='Depth:')
    self.depth_spin = ttk.Spinbox(settings, from_=1, to=6, textvariable=self.depth_var, width=6)

    ttk.Label(settings, text='Time limit (min):').grid(row=2, column=0, sticky='w', **pad)
    self.minutes_spin = ttk.Spinbox(settings, from_=0, to=600, textvariable=self.minutes_var, width=6)
    self.minutes_spin.grid(row=2, column=1, sticky='w', **pad)
    ttk.Label(settings, text='0 = no limit, stop manually.').grid(
      row=2, column=2, columnspan=2, sticky='w', **pad)

    ttk.Label(settings, text='Target score:').grid(row=3, column=0, sticky='w', **pad)
    self.target_spin = ttk.Spinbox(settings, from_=0, to=100000, textvariable=self.target_var, width=6)
    self.target_spin.grid(row=3, column=1, sticky='w', **pad)
    ttk.Label(settings, text='Stops automatically once this score is reached (0 = off).').grid(
      row=3, column=2, columnspan=2, sticky='w', **pad)

    # Preview of the current selection (template shape or clone level).
    self.preview = ttk.Label(settings)
    self.preview.grid(row=0, column=4, rowspan=4, padx=8, pady=4, sticky='n')

    game = ttk.LabelFrame(main, text='Tametsi', padding=8)
    game.pack(fill='x', pady=(8, 0))
    game.columnconfigure(1, weight=1)

    ttk.Label(game, text='Game folder:').grid(row=0, column=0, sticky='w', **pad)
    ttk.Entry(game, textvariable=self.game_dir_var).grid(row=0, column=1, sticky='ew', **pad)
    ttk.Button(game, text='Browse…', command=self.browse).grid(row=0, column=2, **pad)
    ttk.Checkbutton(
      game, text='Automatically copy finished levels to the "puzzles" folder',
      variable=self.copy_var).grid(row=1, column=0, columnspan=3, sticky='w', **pad)

    controls = ttk.Frame(main)
    controls.pack(fill='x', pady=(8, 0))
    self.start_button = ttk.Button(controls, text='Start generating', command=self.on_start)
    self.start_button.pack(side='left')
    self.stop_button = ttk.Button(controls, text='Stop', command=self.on_stop, state='disabled')
    self.stop_button.pack(side='left', padx=(8, 0))
    ttk.Label(controls, textvariable=self.status_var).pack(side='left', padx=16)

    results = ttk.LabelFrame(main, text='Levels found (best first)', padding=8)
    results.pack(fill='both', expand=True, pady=(8, 0))
    results.columnconfigure(0, weight=1)
    results.rowconfigure(0, weight=1)

    self.tree = ttk.Treeview(results, columns=('score', 'round', 'pattern'), show='headings', height=7)
    self.tree.heading('score', text='Score')
    self.tree.heading('round', text='Round')
    self.tree.heading('pattern', text='Pattern')
    self.tree.column('score', width=80, anchor='e', stretch=False)
    self.tree.column('round', width=70, anchor='e', stretch=False)
    self.tree.column('pattern', width=480)
    self.tree.grid(row=0, column=0, sticky='nsew')
    scroll = ttk.Scrollbar(results, orient='vertical', command=self.tree.yview)
    scroll.grid(row=0, column=1, sticky='ns')
    self.tree.configure(yscrollcommand=scroll.set)

    self.write_button = ttk.Button(
      results, text='Create selected level', command=self.on_write, state='disabled')
    self.write_button.grid(row=1, column=0, sticky='w', pady=(8, 0))

    log_frame = ttk.LabelFrame(main, text='Output', padding=8)
    log_frame.pack(fill='both', expand=True, pady=(8, 0))
    log_frame.columnconfigure(0, weight=1)
    log_frame.rowconfigure(0, weight=1)
    self.log = tk.Text(log_frame, height=6, wrap='none', state='disabled')
    self.log.grid(row=0, column=0, sticky='nsew')
    log_scroll = ttk.Scrollbar(log_frame, orient='vertical', command=self.log.yview)
    log_scroll.grid(row=0, column=1, sticky='ns')
    self.log.configure(yscrollcommand=log_scroll.set)

    self.update_hint()

  # -- Helpers ----------------------------------------------------------------

  def update_hint(self):
    template = self.template_var.get()

    # With 'clone' the file defines the shape, otherwise the size does.
    clone = template == 'clone'
    if clone:
      path = self.file_var.get().strip().strip('"')
      base = os.path.basename(path) if path else '(no file chosen)'
      if base.lower().endswith('.puz'):
        base = base[:-len('.puz')]
      self.choice_var.set(f'Level: {base}')
    else:
      info = GRID_TEMPLATES.get(template)
      self.choice_var.set(f'{info[0]} — {info[1]}' if info else template)

    self.size_spin.configure(state='disabled' if clone else 'normal')

    # Show the depth box (in place of the size hint) only for templates that
    # take a depth argument, and only when we are not cloning.
    wants_depth = not clone and template in DEPTH_TEMPLATES
    if wants_depth:
      self.size_hint_label.grid_remove()
      self.depth_label.grid(row=1, column=2, sticky='e', padx=8, pady=4)
      self.depth_spin.grid(row=1, column=3, sticky='w', padx=8, pady=4)
    else:
      self.depth_label.grid_remove()
      self.depth_spin.grid_remove()
      self.size_hint_label.grid()

    self.update_preview()

  def log_line(self, text):
    self.log.configure(state='normal')
    self.log.insert('end', text + '\n')
    lines = int(self.log.index('end-1c').split('.')[0])
    if lines > 500:
      self.log.delete('1.0', f'{lines - 500}.0')
    self.log.see('end')
    self.log.configure(state='disabled')

  def set_running(self, running):
    state_run = 'disabled' if running else 'normal'
    self.start_button.configure(state=state_run)
    self.stop_button.configure(state='normal' if running else 'disabled')
    self.choose_button.configure(state=state_run)
    for widget in (self.size_spin, self.depth_spin, self.minutes_spin, self.target_spin):
      widget.configure(state=state_run)
    if not running:
      self.update_hint()  # re-disables the size box again when a clone is selected

  def browse(self):
    folder = filedialog.askdirectory(title='Choose Tametsi folder', initialdir=self.game_dir_var.get() or None)
    if folder:
      self.game_dir_var.set(folder)

  # -- Picker / preview -------------------------------------------------------

  def update_preview(self):
    """Show a rendering of the current selection (template shape or clone level)."""
    if not HAVE_RENDER:
      return
    img = None
    try:
      template = self.template_var.get()
      if template == 'clone':
        path = self.file_var.get().strip().strip('"')
        if path and os.path.isfile(path) and path.lower().endswith('.puz'):
          img = render.render_file(path, px=PREVIEW_PX)
      else:
        info = GRID_TEMPLATES.get(template)
        if info:
          png = os.path.join(render.TEMPLATE_IMG_DIR, info[2])
          if os.path.isfile(png):
            img = Image.open(png)
            img.thumbnail((PREVIEW_PX, PREVIEW_PX), Image.LANCZOS)
    except Exception:  # noqa: BLE001 - a bad/missing file just means no preview
      img = None
    if img is None:
      self.preview.configure(image='')
      self._preview_image = None
      return
    self._preview_image = ImageTk.PhotoImage(img)
    self.preview.configure(image=self._preview_image)

  def _thumb(self, png_path):
    """Cached gallery thumbnail (PhotoImage) for a pre-rendered PNG, or None."""
    if png_path in self._thumb_cache:
      return self._thumb_cache[png_path]
    photo = None
    try:
      if os.path.isfile(png_path):
        img = Image.open(png_path)
        img.thumbnail((THUMB_PX, THUMB_PX), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
    except Exception:  # noqa: BLE001 - skip thumbnails that fail to load
      photo = None
    self._thumb_cache[png_path] = photo
    return photo

  def open_picker(self):
    """A gallery of the board templates (top) and, below a separator, every
    Tametsi bonus level. Picking a template selects it (size still applies);
    picking a bonus level clones that level's shape."""
    if not HAVE_RENDER:
      messagebox.showinfo(
        'Pillow needed',
        'The visual picker needs Pillow. Install it with "pip install Pillow".')
      return
    if self._picker is not None and self._picker.winfo_exists():
      self._picker.lift()
      return

    win = tk.Toplevel(self.root)
    self._picker = win
    # Build the window hidden, then show it already centered, so it never flashes
    # at the top-left corner of the screen before being moved.
    win.withdraw()
    win.title('Choose a level or template')
    win.transient(self.root)
    win.protocol('WM_DELETE_WINDOW', lambda: self._close_picker())

    canvas = tk.Canvas(win, borderwidth=0, highlightthickness=0)
    scroll = ttk.Scrollbar(win, orient='vertical', command=canvas.yview)
    frame = ttk.Frame(canvas, padding=6)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side='left', fill='both', expand=True)
    scroll.pack(side='right', fill='y')
    window_id = canvas.create_window((0, 0), window=frame, anchor='nw')

    frame.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window_id, width=e.width))

    def on_wheel(event):
      canvas.yview_scroll(int(-event.delta / 120), 'units')
    canvas.bind_all('<MouseWheel>', on_wheel)
    win.bind('<Destroy>', lambda e: canvas.unbind_all('<MouseWheel>') if e.widget is win else None)

    columns = 4
    for i in range(columns):
      frame.columnconfigure(i, weight=1)

    row = 0

    # Templates at the top.
    row = self._picker_header(frame, row, 'Templates (size adjustable)', columns)
    template_cells = []
    for name, (label, _hint, img_file) in GRID_TEMPLATES.items():
      png = os.path.join(render.TEMPLATE_IMG_DIR, img_file)
      template_cells.append(
        (label, self._thumb(png), lambda n=name: self.select_template(n)))
    row = self._picker_cells(frame, row, template_cells, columns)

    # Separator, then the Tametsi bonus levels below it.
    ttk.Separator(frame, orient='horizontal').grid(
      row=row, column=0, columnspan=columns, sticky='ew', pady=10)
    row += 1

    row = self._picker_header(frame, row, 'Tametsi bonus levels', columns)
    bonus = render.list_bonus_puzzles()
    if not bonus:
      ttk.Label(frame, text='No bonus levels were found.').grid(
        row=row, column=0, columnspan=columns, pady=6)
    else:
      bonus_cells = []
      for name, puz_path in bonus:
        png = render.ensure_render(name, puz_path)
        bonus_cells.append(
          (name, self._thumb(png),
           lambda n=name, p=puz_path: self.select_bonus(n, p)))
      self._picker_cells(frame, row, bonus_cells, columns)

    self._center_picker(win, 600, 560)
    win.deiconify()  # now show it, already centered

  def _center_picker(self, win, width, height):
    """Place `win` centered over the main window, on whichever monitor it is on.

    winfo_rootx/rooty are virtual-desktop coordinates, so they stay correct on a
    secondary monitor (where they can be negative or large); we must not clamp
    them to 0, which would snap the window back onto the primary screen.
    """
    self.root.update_idletasks()
    x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
    y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
    win.geometry(f'{width}x{height}+{x}+{y}')

  def _picker_header(self, frame, row, text, columns):
    """Place a bold section header spanning all columns; return the next row."""
    label = ttk.Label(frame, text=text, font=('TkDefaultFont', 11, 'bold'))
    label.grid(row=row, column=0, columnspan=columns, sticky='w', padx=4, pady=(4, 2))
    return row + 1

  def _picker_cells(self, frame, start_row, cells, columns):
    """Grid (label, photo, callback) cells; return the next free row."""
    for index, (label, photo, callback) in enumerate(cells):
      cell = ttk.Frame(frame, padding=4)
      cell.grid(row=start_row + index // columns, column=index % columns,
                sticky='n', padx=4, pady=6)

      img_label = ttk.Label(cell, image=photo if photo else '', cursor='hand2')
      img_label.image = photo  # keep a reference
      img_label.pack()
      text_label = ttk.Label(cell, text=label, wraplength=THUMB_PX + 20,
                             justify='center', cursor='hand2')
      text_label.pack()

      for widget in (img_label, text_label):
        widget.bind('<Button-1>', lambda _e, cb=callback: cb())

    rows = (len(cells) + columns - 1) // columns
    return start_row + rows

  def select_template(self, name):
    self.template_var.set(name)
    self.file_var.set('')
    self.update_hint()
    self._close_picker()

  def select_bonus(self, name, puz_path):
    self.template_var.set('clone')
    self.file_var.set(os.path.abspath(puz_path))
    self.update_hint()
    self._close_picker()

  def _close_picker(self):
    if self._picker is not None:
      try:
        self._picker.destroy()
      except tk.TclError:
        pass
      self._picker = None

  def save_settings(self):
    save_config(dict(
      template=self.template_var.get(),
      size=self._int(self.size_var, 5),
      depth=self._int(self.depth_var, 1),
      clone_file=self.file_var.get(),
      minutes=self._int(self.minutes_var, 0),
      target=self._int(self.target_var, 0),
      game_dir=self.game_dir_var.get(),
      copy=self.copy_var.get(),
    ))

  @staticmethod
  def _int(var, default):
    try:
      return int(var.get())
    except (tk.TclError, ValueError):
      return default

  def refresh_tree(self):
    selected = self.tree.selection()
    self.tree.delete(*self.tree.get_children())
    order = sorted(range(len(self.results)), key=lambda i: -self.results[i]['score'])
    for index in order:
      result = self.results[index]
      pattern = result['pattern']
      shown = pattern if len(pattern) <= 70 else pattern[:67] + '…'
      score = f"{result['score']:g}"
      self.tree.insert('', 'end', iid=str(index), values=(score, result['round'], shown))

    if selected and self.tree.exists(selected[0]):
      self.tree.selection_set(selected[0])
    elif order:
      self.tree.selection_set(str(order[0]))
    self.write_button.configure(state='normal' if self.results else 'disabled')

  # -- Actions ----------------------------------------------------------------

  def on_start(self):
    template = self.template_var.get()

    if template == 'clone':
      # with 'clone' the file path replaces the size
      size = self.file_var.get().strip().strip('"')
      if not os.path.isfile(size):
        messagebox.showerror('File missing', 'Please choose an existing .puz file as the template.')
        return
      size = os.path.abspath(size)
    else:
      size = self._int(self.size_var, 0)
      if size < 2:
        messagebox.showerror('Invalid size', 'Please enter a size of at least 2.')
        return

    # Templates in DEPTH_TEMPLATES take a second argument; 'clone' never does.
    depth = None
    if template != 'clone' and template in DEPTH_TEMPLATES:
      depth = max(1, self._int(self.depth_var, 1))

    self.limit_seconds = max(0, self._int(self.minutes_var, 0)) * 60
    self.target_score = max(0, self._int(self.target_var, 0))
    self.save_settings()

    self.results = []
    self.refresh_tree()
    self.run_info = (template, size, depth)
    self.stop_reason = ''
    self.started_at = time.time()

    self.runner = GeneratorRunner(template, size, self.events, depth)
    try:
      self.runner.start()
    except OSError as error:
      messagebox.showerror('Start failed', str(error))
      self.runner = None
      return

    start_desc = f'{template}, {size}' + (f', depth {depth}' if depth is not None else '')
    self.log_line(f'--- Start: {start_desc} ---')
    self.set_running(True)
    self.status_var.set('Running…')

  def on_stop(self):
    if self.runner and self.runner.running():
      self.stop_reason = 'Stopped manually.'
      self.runner.stop()

  def on_write(self):
    selection = self.tree.selection()
    if not selection:
      messagebox.showinfo('No level selected', 'Please select a level in the list first.')
      return
    if not self.run_info:
      return

    result = self.results[int(selection[0])]
    template, size, depth = self.run_info
    copy = self.copy_var.get()
    game_dir = self.game_dir_var.get().strip()
    if copy and not game_dir:
      messagebox.showerror('Game folder missing', 'Please enter the Tametsi folder or turn off copying.')
      return

    self.save_settings()
    self.write_button.configure(state='disabled')
    self.status_var.set('Creating level…')
    threading.Thread(
      target=self._write_worker,
      args=(template, result['pattern'], size, depth, game_dir if copy else None),
      daemon=True,
    ).start()

  def _write_worker(self, template, pattern, size, depth, game_dir):
    try:
      path = write_puzzle(template, pattern, size, depth)
      dest = copy_to_game(path, game_dir) if game_dir else None
      self.events.put(('written', path, dest))
    except Exception as error:  # noqa: BLE001 - errors should show up in the window
      self.events.put(('error', str(error)))

  def on_close(self):
    if self.runner:
      self.runner.stop()
    self.save_settings()
    self.root.destroy()

  # -- Event loop -------------------------------------------------------------

  def poll(self):
    try:
      while True:
        self.handle(self.events.get_nowait())
    except queue.Empty:
      pass

    running = self.runner is not None and self.runner.running()
    if running:
      elapsed = time.time() - self.started_at
      best = max((r['score'] for r in self.results), default=None)
      best_text = f', best score: {best:g}' if best is not None else ''
      self.status_var.set(f'Running… {int(elapsed // 60):02d}:{int(elapsed % 60):02d}{best_text}')

      if self.limit_seconds and elapsed >= self.limit_seconds and not self.runner.stopped:
        self.stop_reason = 'Time limit reached.'
        self.runner.stop()

    self.root.after(200, self.poll)

  def handle(self, event):
    kind = event[0]

    if kind == 'line':
      self.log_line(event[1])

    elif kind == 'result':
      _, round_num, pattern, score = event

      # Only show levels with a positive score (unsolvable ones are scored -1, trivial ones 0)
      if score <= 0:
        return

      if not any(r['pattern'] == pattern for r in self.results):
        self.results.append(dict(round=round_num, pattern=pattern, score=score))
        self.refresh_tree()
      if self.target_score and score >= self.target_score and self.runner and not self.runner.stopped:
        self.stop_reason = f'Target score {self.target_score} reached.'
        self.runner.stop()

    elif kind == 'done':
      _, code, stopped = event
      self.set_running(False)
      if stopped:
        self.status_var.set(f'{self.stop_reason or "Stopped."} {len(self.results)} levels found.')
      else:
        self.status_var.set(f'Generator finished (code {code}). See the output box for details.')
        if code:
          messagebox.showerror('Generator error', 'The generator exited unexpectedly. See the "Output" box for details.')

    elif kind == 'written':
      _, path, dest = event
      self.write_button.configure(state='normal')
      if dest:
        self.log_line(f'Level copied to: {dest}')
        self.status_var.set('Level created and copied. Restart Tametsi.')
        messagebox.showinfo('Done', f'The level was copied to\n{dest}\n\nRestart Tametsi to see it.')
      else:
        self.log_line(f'Level saved: {path}')
        self.status_var.set('Level created.')
        messagebox.showinfo('Done', f'The level was saved:\n{path}')

    elif kind == 'error':
      self.write_button.configure(state='normal')
      self.status_var.set('Error while creating the level.')
      self.log_line(event[1])
      messagebox.showerror('Error', event[1])


def main():
  if tk is None:
    print('tkinter is not installed. On Windows it is part of the normal Python installation; '
          'on Linux: sudo apt install python3-tk')
    sys.exit(1)

  os.chdir(BASE_DIR)
  root = tk.Tk()
  App(root)
  root.mainloop()


if __name__ == '__main__':
  main()
