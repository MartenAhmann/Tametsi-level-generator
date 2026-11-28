# Level Editor – Anforderungen & Design

Arbeits-Branch: `level_editor`.
Dieses Dokument hält den vereinbarten Umfang, die Design-Entscheidungen und den
Umsetzungsplan fest. Es ist die Referenz für die Implementierung.

---

## 1. Ziel (eine Zeile)

Ein eigenes Editor-Fenster, in dem man per Gitter + Baustein-Palette eine
**Brettform** (Kachel-Geometrie) für Tametsi zusammenklickt. Diese Custom-Form
wird gespeichert und erscheint in einer neuen Picker-Kategorie **"Custom"**. Von
dort wird sie – wie das bestehende `clone`-Template – vom vorhandenen Generator
mit Minen befüllt und bewertet.

## 2. Vom Nutzer bestätigter Umfang (v1)

| Entscheidung | Festlegung |
|---|---|
| Was definiert der Editor? | **Nur die Brettform** (Geometrie). |
| Minen | **Nicht im Editor.** Ausschließlich der Generator setzt Minen. |
| Kachelformen | **Nur Quadrate** in v1. Architektur so bauen, dass weitere Formen (Sechseck, Dreieck, Achteck, Diamant) später leicht ergänzbar sind. |
| Pro Kachel setzbar | Platzieren/Entfernen; **Aufgedeckt (revealed)** als Startfeld markieren. |
| Nicht in v1 | Minen von Hand, Secret (`?`), Farbhinweise, von Hand gezeichnete Spaltenhinweise. |

## 3. Zentrale Design-Entscheidung: Lösbarkeit / Constraints

Eine freie Form braucht **Hinweise**, damit der Generator lösbare Puzzles
erzeugt. Mit nur der Constraint "Gesamtzahl Minen" ist fast jede Zufalls-
belegung unlösbar (Score -1) → im Custom-Bereich käme nie etwas Brauchbares an.

**Lösung (wie `combination_lock`):** Beim Verwenden einer Custom-Form werden die
Constraints **automatisch aus dem Quadratgitter abgeleitet**:
- je **belegter Zeile** (gleiches grid-y) ein Spaltenhinweis über die Kacheln dieser Zeile,
- je **belegter Spalte** (gleiches grid-x) ein Spaltenhinweis über die Kacheln dieser Spalte,
- plus die Gesamt-Constraint über alle Kacheln.

Diese Hinweise werden auch in die fertige `.puz` geschrieben (mit `TEXT_LOCATION`
am Linienende, analog `combination_lock_render`), damit der Spieler sie sieht.
Keine zusätzliche UI nötig – deckt v1 ab und bleibt für spätere Formen gültig.

## 4. Architektur (empfohlen)

Wir reiten auf der bestehenden Template-Registry + `clone`-Pipeline. Kein Eingriff
in Solver/Scorer/Generator-Kern nötig.

**Neues Template `custom` (registriert wie `clone`/`l_shape_grid`):**
- Signatur `custom(compressed, filename)` – identisch zur `clone`-Signatur, damit
  es sich 1:1 in GUI, `writer.py` und `generator.py` einfügt (dort ist für
  `clone` das "size"-Argument bereits der Dateipfad).
- `filename` zeigt auf eine vom Editor gespeicherte **Shape-Datei (JSON)**.
- `make`-Pfad (`compressed is None`): liest JSON → baut `board` (nodes +
  Nachbarn aus Gitter-Adjazenz), `revealed`, abgeleitete `constraints` (siehe §3)
  und einen `sanity_check`. **Wichtig:** `make` **muss** `sanity_check` liefern –
  `generator.py` ruft es auf (`iteration()`), sonst Crash.
- `render`-Pfad (`compressed` gesetzt): belegt die unaufgedeckten Kacheln gemäß
  `compressed`, löst + bewertet (wie `clone`), liefert `nodes/columns/colors/
  title/tile_text/score` für `leveltemplate.xml`.

Logik bleibt damit in `templater.py` (testbar über `tester.py` / `check_template`),
die Editor-UI bleibt dünn (speichert nur das Gitter).

**Alternative (verworfen für v1):** Editor schreibt direkt eine form, hinweise &
revealed enthaltende `.puz` und man nutzt unverändert `clone`. Spart Template-
Code, dupliziert aber Hinweis-/Positions-Logik in der GUI und ist schlechter
testbar. Falls doch gewünscht, ist der Umstieg klein.

### Shape-Datei (JSON) – Entwurf
```json
{
  "version": 1,
  "shape": "square",            // Erweiterungspunkt für spätere Formen
  "tile_size": 10,
  "cells": [                     // nur belegte Zellen
    { "x": 0, "y": 0, "revealed": false },
    { "x": 1, "y": 0, "revealed": true }
  ]
}
```
- Node-IDs: stabil 0..n-1 in fester Reihenfolge (z. B. zeilenweise über belegte Zellen).
- Nachbarn: 8er- oder 4er-Nachbarschaft? → **8er** (wie `combination_lock`, Diagonalen inkl.). TODO bestätigen, falls gewünscht.
- Position/Polygon je Quadrat wie `combination_lock_render` (`points` = Quadrat der Kantenlänge ~`0.96*tile_size`).

## 5. Editor-Fenster (UI-Spezifikation)

Technik: `tk.Toplevel` mit `tk.Canvas` (konsistent mit dem bestehenden Picker in
`gui.py`). Keine neue Abhängigkeit.

Aufbau:
- **Gitter-Canvas** (Hauptfläche): quadratisches Raster, scroll-/scrollbar-fähig.
  Rasterlinien sichtbar. Platzierte Kacheln gefüllt, aufgedeckte visuell
  abgesetzt (z. B. dunkler, wie `REVEALED_TILE` in `render.py`).
- **Palette** (Seitenleiste): v1 enthält die auswählbaren "Bausteine":
  1. Quadrat-Kachel (platzieren)
  2. Werkzeug "Aufgedeckt umschalten"
  3. Werkzeug "Entfernen" (oder Rechtsklick entfernt)
  Ausgewählter Baustein ist hervorgehoben. Spätere Formen kommen hier als
  weitere Einträge dazu.
- **Interaktion:** Baustein in Palette anklicken → auswählen. Dann auf das Gitter
  klicken → gewählten Baustein setzen (bzw. Zustand umschalten). Klicken+Ziehen
  zum Mehrfachsetzen ist nett-to-have, nicht v1-Pflicht.
- **Aktionen (Buttons):** Neu/Leeren, Speichern (→ JSON in `custom/`), evtl.
  Namensfeld, Schließen. Beim Speichern Thumbnail-Cache ggf. invalidieren.
- **Validierung beim Speichern:** mind. 1 Kachel; zusammenhängend? (nice-to-have);
  Name eindeutig.

## 6. Picker-Änderungen (`gui.py`, `open_picker`)

- Neue Sektion **"Custom"** ganz **oben**, über "Templates (size adjustable)".
- **Per Default leer** (keine Puzzles).
- **Erster Eintrag ist immer ein Button**, der den Level-Editor öffnet
  (eigenes Fenster). Kein Puzzle-Thumbnail an erster Stelle.
- Danach: Thumbnails der gespeicherten Custom-Formen (gerendert aus der JSON via
  `render.py`). Klick auf eine Form wählt sie aus: `template_var='custom'`,
  `file_var=<json-pfad>` (analog `select_bonus`, das `clone` setzt).
- Reihenfolge der Sektionen danach unverändert: Templates → Tametsi bonus levels.

Betroffene Stellen in `gui.py`, die aktuell hart auf `template == 'clone'`
prüfen, müssen `custom` gleich behandeln (dateibasiert statt größenbasiert):
`update_hint`, `update_preview`, `set_running`, `on_start` (Pfad statt Size),
`save_settings`/`load_config` (Custom-Auswahl merken).

## 7. Rendering / Vorschau (`render.py`)

- Thumbnails der Custom-Formen: kleine Funktion, die aus der JSON-Shape ein
  `render_data`-taugliches dict (nodes mit `position`/`points`) baut – oder die
  `custom`-make/render-Funktion aus `templater.py` mit leerer Belegung nutzt
  (wie `_template_datas()` es für Templates tut).
- Caching analog `ensure_render` (PNG neu rendern, wenn JSON neuer ist).

## 8. Speicherort

- Neuer Ordner `custom/` im Repo-Root für die JSON-Shape-Dateien.
- `.gitignore` prüfen: Custom-Shapes des Nutzers vermutlich **nicht** committen
  (lokale Kreationen). Entscheidung beim Umsetzen festhalten.

## 9. Erweiterbarkeit (spätere Formen)

Der Erweiterungspunkt ist das Feld `shape` in der JSON plus ein Geometrie-Builder
pro Form im `custom`-Template:
- `square` (v1): Gitter-Adjazenz + quadratische Polygone.
- später `hexagon`/`triangle`/`octagon`/`diamond`: eigene Koordinaten→Pixel-
  Abbildung, Polygon-Punkte und Nachbarschaftsregel. `combination_lock`,
  `hexagon`, `octagons`, `diamond` in `templater.py` liefern Vorlagen.
Editor-Palette bekommt je Form einen weiteren Baustein; Rest der Pipeline bleibt.

## 10. Risiken / zu verifizieren

1. **`clone` + Generator – GEKLÄRT:** Der echte Pfad ist `gradient_ascent`
   (nicht das tote `iteration`), dort ist `sanity_check` **optional**
   (`if sanity_check and ...`). Entscheidend: Kandidaten-Strings decken **nur die
   unaufgedeckten Zellen in ID-Reihenfolge** ab (`num_unrevealed`), und genau so
   expandiert `_simple_render` beim Rendern → konsistent. `custom`-`make` liefert
   dennoch einen (trivialen) `sanity_check`.
2. **Hinweis-Positionen (`TEXT_LOCATION`)** für auto-generierte Zeilen/Spalten so
   setzen, dass Tametsi die Zahlen sinnvoll am Linienende zeichnet.
3. **Lösbarkeit/Score:** mit nur Zeilen-/Spaltenhinweisen ähnlich gut wie
   `combination_lock`? Früh mit `tester.py` / `check_template` gegenprüfen.
4. **Node-ID-/Reihenfolge-Stabilität** zwischen Editor-Speicherung, Rendering und
   `compressed`-Zuordnung (revealed-Zellen vs. unrevealed, siehe `replace_cells`).

## 11. Dateien, die angefasst werden

- `templater.py` – neues `custom`-Template (make+render) + Registrierung.
- `gui.py` – Picker-Sektion "Custom" + Editor-Fenster (neues `tk.Toplevel`),
  `clone`→`custom` gleichbehandeln.
- `render.py` – Thumbnail/Preview für Custom-Shapes.
- `custom/` – neuer Ordner für gespeicherte Shapes.
- Tests: ein Custom-Beispiel in `test/` + `tester.py`-Lauf zur Validierung.
- ggf. `README.md` – kurzer Hinweis auf den Editor.

## 12. Out of scope (v1)

Von Hand gesetzte Minen, Secret-Kacheln, Farbgruppen, manuelle Spaltenhinweise,
Nicht-Quadrat-Formen, Undo/Redo, Mehrfach-Auswahl per Rahmen. Alles bewusst
späteren Versionen vorbehalten; Architektur hält die Tür dafür offen.

## 13. Status: v1 umgesetzt

Umgesetzt und end-to-end getestet (Branch `level_editor`):
- `custom_levels.py` – Shape-Speicher (JSON in `custom/`, `.gitignore`-geschützt).
- `templater.py` – `custom`-Template (make/render) über `_masked_square_grid`
  (8er-Nachbarschaft + auto Zeilen-/Spaltenhinweise) + `_simple_render`
  (jetzt mit `revealed`-Markierung); registriert wie `clone`. Titel ohne `:`
  (sonst ungültiger Windows-Dateiname in `writer.py`).
- `render.py` – `custom_shape_data` / `render_custom` / `ensure_custom_render`
  für Vorschau + Thumbnails (nur Geometrie, kein Solver).
- `editor.py` – `LevelEditor` (tk.Toplevel): Gitter-Canvas + Palette (Square
  tile / Revealed start / Erase), Klick+Ziehen, Speichern mit Name/Validierung.
- `gui.py` – Picker-Sektion „Custom" ganz oben (Editor-Knopf als erster Eintrag,
  per Default leer), `custom` wird wie `clone` dateibasiert behandelt; Picker
  degradiert ohne Pillow, sodass der Editor-Knopf erreichbar bleibt.

**Verifiziert:** Shape → `make`/`render` → Generator (positive Scores, keine
Fehler) → `writer.py` (gültige `.puz`) → `loader` (Round-Trip, Nachlösen ergibt
denselben Score). Minen landen nie auf aufgedeckten Feldern. `tester.py` nicht
nutzbar (kein `.puz` in `test/` in diesem Worktree); validiert per eigenem Skript.

**Umgebungs-Hinweis (kein Bug von uns):** `writer.py` schreibt nach `puzzles/`
und legt den Ordner nicht an; in einem frischen Checkout muss `puzzles/`
existieren (gilt für alle Templates).

**Noch offen / sinnvolle Follow-ups:** manuelles Durchklicken des Editor-Fensters
(GUI-Smoke-Test), optional 4er- statt 8er-Nachbarschaft als Editor-Option,
README-Notiz zum Editor.

## 14. Status: Sechseck-Kacheln ergänzt

Der Editor kann jetzt auch **hexagonale** Level bauen (neben Quadraten):
- **`custom_levels.py`** – `save_shape(..., shape=...)` speichert `shape`
  (`'square'` / `'hexagon'`). Hex-Zellen liegen als axiale `(q, r)` in den
  `x`/`y`-Feldern; das JSON-Schema bleibt unverändert (abwärtskompatibel, alte
  Dateien sind weiter `'square'`).
- **`templater.py`** – `custom()` verzweigt auf das `shape`-Feld. Neuer Helfer
  `_masked_hex_grid` (6er-Nachbarschaft, Pointy-Top-Hex-Polygone, Linienhinweise
  entlang der drei Hex-Achsen) – analog zum vorhandenen `hexagon`-Template, nur
  über die handgezeichnete Zellmenge.
- **`render.py`** – `custom_shape_data` zeichnet für `'hexagon'` echte Hex-Kacheln
  (Vorschau/Thumbnails).
- **`editor.py`** – Tile-Shape-Picker (zwei anklickbare Thumbnails Quadrat/Sechseck)
  unten in der Palette, über dem Namensfeld. Hex-Gitter wird gezeichnet und per
  Pixel→Hex-Rundung angeklickt; „Square tile" wird im Hex-Modus zu „Hexagon tile".
  Formwechsel leert die aktuelle Zeichnung (andere Koordinatensysteme).

**Verifiziert:** Hex-Shape → `make`/`render` (löst + bewertet, 6er-Nachbarschaft,
12-Punkt-Hex-Polygone) → Vorschau-PNG korrekt; Editor-Smoke-Test (Bauen, Wechseln,
Platzieren, Speichern, Wieder-Laden, Zurückwechseln).
