"""Kommandozeile: tbd init | sync | apply"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import pipeline
from .config import load_config
from .core.llm import LLMError
from .core.lock import VaultLockedError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tbd", description="TBD-Protokolle in einen Obsidian-Vault überführen.")
    parser.add_argument("-v", "--verbose", action="store_true", help="ausführliche Ausgabe")
    commands = parser.add_subparsers(dest="command", required=True)

    def add_common(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--vault", type=Path, help="Pfad zum Obsidian-Vault")
        cmd.add_argument("--force", action="store_true", help="Sperrdatei ignorieren")

    init = commands.add_parser("init", help="Vault einrichten (Ordner, Übersichten, Konfiguration)")
    init.add_argument("--vault", type=Path, help="Pfad zum Obsidian-Vault")

    sync = commands.add_parser("sync", help="Export importieren, Termine extrahieren und Vault aktualisieren")
    add_common(sync)
    sync.add_argument("--export", type=Path, help="Markdown-Export aus Google Docs")
    sync.add_argument("--initial", action="store_true",
                      help="Erstlauf: unbekannte Personen/Themen direkt als Notizen anlegen")
    sync.add_argument("--refresh", action="store_true", help="Cache ignorieren und alles neu extrahieren")
    sync.add_argument("--restore-deleted", action="store_true", help="gelöschte Terminnotizen wieder anlegen")
    sync.add_argument("--ollama-url", help="Adresse der Ollama-API (Standard: http://localhost:11434)")

    apply = commands.add_parser("apply", help="Nur Prüfbericht umsetzen und Notizen neu schreiben (ohne LLM)")
    add_common(apply)
    apply.add_argument("--restore-deleted", action="store_true", help="gelöschte Terminnotizen wieder anlegen")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    try:
        config = load_config(args.vault, getattr(args, "ollama_url", None))
        if args.command == "init":
            pipeline.init(config)
        elif args.command == "sync":
            if args.export and not args.export.exists():
                raise ValueError(f"Export nicht gefunden: {args.export}")
            pipeline.run(config, pipeline.RunOptions(
                export=args.export, initial=args.initial, refresh=args.refresh,
                restore_deleted=args.restore_deleted, force=args.force))
        elif args.command == "apply":
            pipeline.run(config, pipeline.RunOptions(
                use_llm=False, restore_deleted=args.restore_deleted, force=args.force))
    except (ValueError, LLMError, VaultLockedError) as err:
        logging.error("Fehler: %s", err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
