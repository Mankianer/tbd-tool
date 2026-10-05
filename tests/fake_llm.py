"""Ein simuliertes Sprachmodell für Tests – ohne Ollama.

Jede Zeile mit einem Datum wird zu einem Termin. Thema und Personen werden
über einfache Schlüsselwörter erkannt. Das ist natürlich viel dümmer als ein
echtes Modell, reicht aber, um die Pipeline vollständig durchzutesten.
"""

import re

TOPICS = {"pony": "Ponyfreizeit", "pferd": "Pferdefreizeit", "konfi": "Konfiarbeit",
          "weihnacht": "Weihnachtsfeier", "martin": "Martinsumzug"}
NAMES = ["Pia", "Michelle", "Mitch", "Philipp", "Marvin", "Bellis", "Kira", "Malte"]
DATE_RE = re.compile(r"(\d{1,2}\.\d{1,2}\.(?:\d{4})?)")


class FakeLLM:
    model = "fake"
    num_ctx = 8192

    def __init__(self):
        self.calls = 0
        self.system_prompts: list[str] = []

    def check(self):
        pass

    def chat_json(self, system, user, schema):
        self.calls += 1
        self.system_prompts.append(system)
        # Nur den Protokolltext auswerten (steht nach der Überschrift "# Besprechung vom …")
        protocol_text = user.split("# Besprechung vom", 1)[-1].split("\n", 1)[-1]
        appointments = []
        for line in protocol_text.splitlines():
            match = DATE_RE.search(line)
            if not match:
                continue
            text = line.strip(" *-")
            topic = next((t for k, t in TOPICS.items() if k in text.lower()), "Sonstiges")
            names = [n for n in NAMES if re.search(rf"\b{n}\b", text)]
            kind = "deadline" if "bis" in text.lower() else "besprechung" if "TBD" in text else "veranstaltung"
            appointments.append({
                "title": DATE_RE.sub("", text).strip(" :-")[:40] or "Termin",
                "kind": kind, "date_text": match.group(1), "topic": topic,
                "responsible": names, "quote": text,
                "status": "abgesagt" if "kein" in text.lower() else "geplant",
            })
        return {"appointments": appointments}
