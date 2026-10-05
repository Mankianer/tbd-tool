"""Konfiguration.

Es gibt zwei Konfigurationsdateien:

1. ``<Vault>/.tbd/config.yaml`` – gemeinsame Einstellungen, die mit dem Vault
   mitwandern (Modell, Ordnernamen, ignorierte Namen). Wird von ``tbd init``
   angelegt und ist ausführlich kommentiert.
2. ``~/.config/tbd/config.yaml`` – Einstellungen nur für diesen Rechner
   (Ollama-Adresse, Standard-Vault). Optional.

Kommandozeilen-Optionen haben Vorrang vor beiden Dateien.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

TOOL_DIR_NAME = ".tbd"
VAULT_CONFIG_NAME = "config.yaml"
LOCAL_CONFIG_PATH = Path.home() / ".config" / "tbd" / "config.yaml"

DEFAULT_FOLDERS = {
    "protocols": "Protokolle",
    "appointments": "Termine",
    "topics": "Themen",
    "persons": "Personen",
    "overviews": "Übersichten",
    "system": "_System",
    "attachments": "Anhänge",
}

# Wird bei "tbd init" als .tbd/config.yaml in den Vault geschrieben.
DEFAULT_VAULT_CONFIG = """\
# Gemeinsame Einstellungen für das TBD-Tool.
# Diese Datei liegt im Vault und gilt für alle Rechner, auf denen das Tool läuft.
# Rechnerspezifisches (z.B. die Ollama-Adresse) gehört in ~/.config/tbd/config.yaml.

# Ollama-Modell für die Extraktion. Bewusst hier festgelegt, damit alle Rechner
# dasselbe Modell verwenden. Ein Wechsel wirkt nur auf neue oder geänderte Protokolle;
# bereits ausgewertete neu auswerten: tbd sync --refresh [PROTOKOLL …]
model: qwen2.5:14b

llm:
  temperature: 0
  num_ctx: 8192       # Kontextlänge in Tokens – muss Prompt + längstes Protokoll + Antwort fassen.
                      # Größer = mehr Grafikspeicher. Das Tool warnt, wenn es knapp wird.
  timeout: 600        # Sekunden pro Anfrage
  # think: false      # für "Thinking"-Modelle (qwen3, qwen3.5, …) setzen – spart viel Zeit

# Ordnernamen im Vault
folders:
  protocols: Protokolle
  appointments: Termine
  topics: Themen
  persons: Personen
  overviews: Übersichten
  system: _System
  attachments: Anhänge

# Wörter, die das Modell manchmal als Person liefert, die aber keine sind.
# Groß-/Kleinschreibung egal.
ignore_names:
  - wir
  - uns
  - alle
  - TBD
  - Helferkreis
  - Helfer
  - Helfende
  - Teamer
  - Konfis
  - Katechumenen
  - Katechus
  - Kinder
  - Eltern
  - Gemeinde
  - Presbyterium
"""


@dataclass
class Config:
    vault: Path
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5:14b"
    temperature: float = 0.0
    num_ctx: int = 8192
    timeout: int = 600
    think: bool | None = None
    folders: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FOLDERS))
    ignore_names: list[str] = field(default_factory=list)

    @property
    def tool_dir(self) -> Path:
        return self.vault / TOOL_DIR_NAME


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} muss ein YAML-Objekt (key: value) enthalten.")
    return data


def load_config(vault: Path | None = None, ollama_url: str | None = None) -> Config:
    """Lädt die Konfiguration. Reihenfolge: Kommandozeile > lokal > Vault > Standard."""
    local = _read_yaml(LOCAL_CONFIG_PATH)

    vault = vault or (Path(local["vault"]).expanduser() if local.get("vault") else None)
    if vault is None:
        raise ValueError(
            f"Kein Vault angegeben. Nutze --vault PFAD oder trage 'vault: PFAD' in {LOCAL_CONFIG_PATH} ein.")
    vault = vault.expanduser().resolve()

    shared = _read_yaml(vault / TOOL_DIR_NAME / VAULT_CONFIG_NAME)
    llm = shared.get("llm") or {}

    config = Config(vault=vault)
    config.model = shared.get("model", config.model)
    config.temperature = float(llm.get("temperature", config.temperature))
    config.num_ctx = int(llm.get("num_ctx", config.num_ctx))
    config.timeout = int(llm.get("timeout", config.timeout))
    config.think = llm.get("think", config.think)
    config.folders.update(shared.get("folders") or {})
    config.ignore_names = list(shared.get("ignore_names") or [])
    config.ollama_url = (ollama_url or local.get("ollama_url") or config.ollama_url).rstrip("/")
    return config


def write_default_vault_config(vault: Path) -> bool:
    """Legt .tbd/config.yaml an, falls noch nicht vorhanden. True = neu angelegt."""
    path = vault / TOOL_DIR_NAME / VAULT_CONFIG_NAME
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_VAULT_CONFIG, encoding="utf-8")
    return True
