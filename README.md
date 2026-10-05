# TBD-Tool

Überführt die Besprechungsprotokolle des TBD (Google Docs) in einen Obsidian-Vault:
eine Notiz pro Besprechung, pro Termin, pro Person und pro Thema – verknüpft über
Properties, auswertbar mit Dataview, korrigierbar von Hand.

---

## Installation

Voraussetzungen: Python ≥ 3.10, Ollama, in Obsidian das Community-Plugin **Dataview**.

```bash
cd tbd-tool
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # -e: Codeänderungen wirken sofort, ohne Neuinstallation
ollama pull qwen2.5:14b
```

Optional: `~/.config/tbd/config.yaml` für Einstellungen, die nur diesen Rechner betreffen:

```yaml
vault: ~/Obsidian/TBD                 # dann kann --vault weggelassen werden
ollama_url: http://localhost:11434
```

## Benutzung

```bash
tbd init  --vault obsidian/TBD-Data                        # einmalig: Ordner, Übersichten, Konfiguration
tbd sync  --vault obsidian/TBD-Data --export Protokoll.md --initial    # Erstlauf
tbd sync  --vault obsidian/TBD-Data --export Protokoll.md   # jeder weitere Export
tbd apply --vault obsidian/TBD-Data                         # nur Prüfbericht umsetzen (ohne LLM, Sekunden)
```

Den Export bekommst du in Google Docs über **Datei → Herunterladen → Markdown (.md)**.
Dabei muss der Protokoll-Tab geöffnet sein.

| Option | Wirkung |
|---|---|
| `--initial` | Unbekannte Personen und Themen werden direkt als Notizen angelegt statt im Prüfbericht gesammelt. Danach in Obsidian aufräumen (doppelte löschen, Aliase eintragen). |
| `--refresh` | Alle Protokolle neu durchs Modell schicken statt den Cache zu nutzen. |
| `--refresh 2026-09-18 2026-09-25` | Nur diese Protokolle neu auswerten – praktisch zum Ausprobieren eines anderen Modells oder Prompts. |
| `--restore-deleted` | Von Hand gelöschte Terminnotizen wieder anlegen. |
| `--force` | Sperrdatei ignorieren (nach einem Absturz). |
| `--ollama-url` | Andere Ollama-Adresse für diesen Lauf. |
| `-v` | Ausführliche Ausgabe. |

### Typischer Ablauf

1. Export herunterladen, `tbd sync --export …` ausführen.
2. In Obsidian `_System/Prüfbericht.md` öffnen, Haken setzen oder Probleme direkt in den Notizen lösen.
3. `tbd apply` ausführen (oder bis zum nächsten Sync warten).

Der erste Lauf über alle Protokolle dauert je nach Rechner und Modell eine Weile
(grob 10–60 Sekunden pro Protokoll). Danach werden nur neue oder geänderte Protokolle ausgewertet.

### Geschwindigkeit

- Das Modell muss **komplett in den Grafikspeicher** passen. Während eines Laufs `ollama ps`
  ausführen: Steht dort nicht „100% GPU“, ist das Modell zu groß und läuft teilweise auf der
  CPU – dann ein kleineres Modell oder ein kleineres `num_ctx` wählen.
- Bei „Thinking“-Modellen (qwen3, qwen3.5, …) in `.tbd/config.yaml` `think: false` setzen.
- Ollama mit diesen Umgebungsvariablen starten halbiert den Speicher für den Kontext:
  `OLLAMA_FLASH_ATTENTION=1` und `OLLAMA_KV_CACHE_TYPE=q8_0`.
- Die Anweisungen an das Modell (`prompt_system.md`) sind für alle Protokolle gleich.
  Ollama verarbeitet sie dadurch nur einmal pro Lauf und nicht bei jedem Protokoll neu.
  Wechselnde Angaben gehören deshalb immer in `prompt_user.md`.

---

## Der Vault

```
TBD/
├── Protokolle/       2026-10-02.md      eine Notiz pro Besprechung (ist selbst ein Termin)
│   └── Anhänge/      Bilder aus dem Export
├── Termine/          2026-09-25 Vortreffen Ponyfreizeit.md
├── Themen/           Ponyfreizeit.md, Ponyfreizeit - Küche.md
├── Personen/         Bellis.md, Pia.md
├── Übersichten/      Anstehende Termine.md, Deadlines.md, Besprechungen.md
├── _System/          Prüfbericht.md
└── .tbd/             Gedächtnis des Tools (in Obsidian unsichtbar)
    ├── config.yaml   gemeinsame Einstellungen (Modell, Ordnernamen, ignorierte Namen)
    ├── state.json    was das Tool zuletzt geschrieben hat
    ├── ignored.yaml  im Prüfbericht ignorierte Einträge
    └── cache/        Ergebnisse des Modells pro Protokoll
```

`.tbd/` muss mit dem Vault mitwandern, wenn das Tool auf mehreren Rechnern laufen soll.

### Properties

**Termin** (`Termine/…`): `id`, `typ: termin`, `art` (veranstaltung · treffen · deadline),
`titel`, `datum`, `datum_bis`, `uhrzeit`, `uhrzeit_bis`, `ort`,
`status` (vorschlag · geplant · bestätigt · verschoben · abgesagt),
`thema` (Link), `zustaendig` (Links), `beteiligt` (Links), `quellen` (Links auf Protokolle).

**Besprechung** (`Protokolle/…`): `id`, `typ: besprechung`, `titel`, `datum`,
`status` (stattgefunden · angekündigt · abgesagt · ausgefallen), `uhrzeit`, `ort`,
`hinweise` (Zitate aus früheren Protokollen), `quellen`.

**Person**: `aliases`, `vollname`, `rufname`, `rolle`, `gruppe`, `aktiv` – plus freier Text.

**Thema**: `aliases`, `oberthema` (Link, bei Unterthemen).

### Stammdaten = Personen- und Themen-Notizen

Es gibt keine separate Liste. Wer „Mitch“ ist, steht in `Personen/Michelle.md`:

```yaml
aliases: [Mitch]
```

Obsidian löst `[[Mitch]]` damit selbst auf, und das Tool verlinkt beim nächsten Lauf alle
Erwähnungen von „Mitch“ auf `[[Michelle]]`.

### Was gehört wem?

| Bereich | Wer schreibt |
|---|---|
| Properties von Terminen und Besprechungen | Tool – **aber** von Hand geänderte Werte werden nie überschrieben |
| Text zwischen `<!-- tbd:auto:start -->` und `<!-- tbd:auto:end -->` | nur das Tool (Protokolltext, Zitate) |
| Alles andere (Abschnitt „Notizen“, Personen- und Themenbeschreibungen) | nur Menschen |
| Personen- und Themen-Notizen | Menschen; das Tool legt sie nur an und trägt Aliase ein |

Wie Handeingaben erkannt werden: Das Tool merkt sich in `.tbd/state.json`, welchen Wert es
zuletzt geschrieben hat. Steht in der Notiz etwas anderes, war es ein Mensch. Liefert ein neues
Protokoll dann einen *anderen* Wert, entsteht ein Konflikt im Prüfbericht.

Weitere Regeln:
- Eine gelöschte Terminnotiz wird nicht wieder angelegt (außer mit `--restore-deleted`).
- Würde das Tool einen Termin nicht mehr erzeugen (z.B. weil ein Thema per Alias
  zusammengelegt wurde), wird die Notiz gelöscht – sofern niemand sie bearbeitet hat.
  Sonst fragt der Prüfbericht.
- Fehlen die Auto-Marker in einer Notiz, wird ihr Text nicht mehr angefasst.

### Cache

Die Ergebnisse des Modells liegen pro Protokoll in `.tbd/cache/`. Ein Eintrag wird nur
ungültig, wenn sich **der Protokolltext** oder **der Aufbau des Ergebnisses** (Schema,
Extraktor-Version) ändert.

Ein anderes **Modell** oder ein geänderter **Prompt** machen den Cache bewusst nicht ungültig:
Jeder Eintrag vermerkt, womit er erzeugt wurde, und `tbd sync` meldet, wie viele Ergebnisse
von einem anderen Modell oder älteren Prompt stammen (`-v` zeigt welche). Neu ausgewertet
wird nur auf Wunsch mit `--refresh` – für alle oder einzelne Protokolle.

### Der Prüfbericht

Wird bei jedem Lauf neu erzeugt. Abschnitte: neue Personen, neue Themen, Konflikte,
verwaiste Termine, Hinweise (z.B. unplausibles Jahr, Zitat nicht im Protokoll gefunden).
Pro Eintrag **eine** Option anhaken. Bei „Alias von [[…]]“ darf der Name im Link vorher
geändert werden. Ignorierte Einträge stehen in `.tbd/ignored.yaml`; eine Zeile dort
löschen holt den Eintrag zurück.

---

## Aufbau des Codes

```
tbd/
├── cli.py                 Kommandozeile
├── config.py              Konfiguration laden, Standardwerte
├── pipeline.py            ★ Ablauf eines Laufs – hier anfangen zu lesen
├── core/                  allgemeine Bausteine, wissen nichts von "Terminen"
│   ├── notes.py           Notiz lesen/schreiben (Frontmatter, Auto-Block)
│   ├── vault.py           Ordner, Notizen finden, aus Vorlagen anlegen, Aliase
│   ├── names.py           Namen normalisieren, Alias-Index
│   ├── managed.py         ★ Properties schreiben ohne Handeingaben zu überschreiben
│   ├── review.py          Prüfbericht erzeugen und auslesen
│   ├── state.py           state.json und ignored.yaml
│   ├── extraction.py      Rahmen für LLM-Extraktoren inkl. Cache
│   ├── llm.py             Ollama-Client
│   ├── dates.py           Datum/Uhrzeit aus Text
│   └── lock.py            Sperrdatei
├── features/              fachliche Module
│   ├── master_data.py     Personen & Themen: auflösen, Prüfbericht-Entscheidungen
│   ├── protocols/         Export importieren, Besprechungsnotizen
│   └── appointments/      Termine
│       ├── models.py      Datenmodelle (+ Zuordnung englisch → deutsche Property)
│       ├── prompt_system.md ★ Anweisungen ans Modell – anpassen ohne Code
│       ├── prompt_user.md   Nachricht pro Protokoll (Datum, bekannte Themen, Text)
│       ├── extractor.py   verbindet Prompt und Modell
│       ├── builder.py     Rohdaten → zusammengeführte Termine
│       └── writer.py      Terminnotizen schreiben
└── templates/             Vorlagen für neue Notizen (inkl. Dataview-Abfragen)
```

Im Code sind alle Namen englisch, die Properties im Vault deutsch. Die Zuordnung steht
an genau einer Stelle: in den `models.py` (`Field(alias="datum")`).

### Häufige Anpassungen

| Was | Wo |
|---|---|
| Was als Termin zählt, Tonfall, Beispiele | `features/appointments/prompt_system.md` (danach `--refresh`, siehe „Cache“) |
| Was pro Protokoll mitgeschickt wird | `features/appointments/prompt_user.md` + `prompt_values()` in `extractor.py` |
| Modell, Ordnernamen, ignorierte Namen | `<Vault>/.tbd/config.yaml` |
| Dataview-Abfragen neuer Notizen | `templates/*.md` (bestehende Notizen bleiben unverändert) |
| Neue Property für Termine | `features/appointments/models.py` (+ ggf. Feld im Prompt und in `builder.py`) |
| Wann zwei Erwähnungen derselbe Termin sind | `Appointment.key` in `builder.py` |
| Jahr bei Daten ohne Jahreszahl | `LOOKBACK` in `core/dates.py` |

### Neuer Extraktor (z.B. Aufgaben)

1. `features/tasks/` anlegen nach dem Vorbild von `features/appointments/`:
   `models.py`, `prompt_system.md`, `prompt_user.md`, `extractor.py`, `builder.py`, `writer.py`.
2. In `pipeline.py` einen weiteren Block „extrahieren → bauen → schreiben“ ergänzen.
3. Für Personen und Themen den vorhandenen `Resolver` aus `master_data.py` nutzen –
   Aliase, Prüfbericht und Initial-Modus funktionieren dann automatisch.
4. In `templates/person.md` und `templates/topic.md` eine Dataview-Abfrage ergänzen.

### Tests

```bash
pytest
```

Die Tests brauchen kein Ollama: `tests/fake_llm.py` simuliert das Modell.
`tests/test_pipeline.py` spielt einen kompletten Ablauf durch (Erstlauf, Handeingabe,
Prüfbericht, gelöschte Notiz).

---

## Updates einspielen

Das Projekt ist ein Git-Repository. Änderungen kommen als Patch-Datei:

```bash
git apply --check aenderung.patch   # prüfen
git apply aenderung.patch
git commit -am "Beschreibung"
```

Eigene Anpassungen am besten ebenfalls committen – dann sieht man mit `git diff`
jederzeit, was sich geändert hat, und kann Patches sauber zusammenführen.

---

## Bekannte Grenzen

- **Thema oder Datum ändern sich** (z.B. Termin verschoben): Es entsteht ein neuer Termin.
  Der alte bleibt stehen, weil ihn das ältere Protokoll weiterhin erwähnt – am besten von Hand
  auf `status: verschoben` setzen oder löschen.
- **Kleine Modelle** übersehen Termine oder ordnen Themen uneinheitlich zu. Der Prüfbericht
  fängt erfundene Termine ab (Zitat-Prüfung), übersehene nicht. 14B-Modelle oder größer
  sind empfehlenswert.
- **Emojis** aus Google Docs kommen im Export mit; im PDF-Weg gingen sie verloren.
