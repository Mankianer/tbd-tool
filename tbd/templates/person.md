---
typ: person
aliases: []
vollname:
rufname:
rolle:
gruppe:
aktiv: true
---
## Wer ist das?

_Hier allgemeine Infos eintragen: richtiger Name, Rufname, Aufgaben im TBD, wie man die Person erreicht …_

## Anstehende Termine (zuständig)

```dataview
TABLE WITHOUT ID file.link AS Termin, datum AS Datum, thema AS Thema, status AS Status
FROM "{{appointments}}"
WHERE contains(zustaendig, this.file.link) AND datum >= date(today)
SORT datum ASC
```

## Themen

```dataview
TABLE WITHOUT ID key AS Thema, length(rows) AS Termine
FROM "{{appointments}}"
WHERE contains(zustaendig, this.file.link) OR contains(beteiligt, this.file.link)
GROUP BY thema
SORT key ASC
```

## Alle Termine

```dataview
TABLE WITHOUT ID file.link AS Termin, datum AS Datum, thema AS Thema, choice(contains(zustaendig, this.file.link), "zuständig", "beteiligt") AS Rolle
FROM "{{appointments}}"
WHERE contains(zustaendig, this.file.link) OR contains(beteiligt, this.file.link)
SORT datum DESC
```
