---
typ: thema
aliases: []
oberthema:
---
## Beschreibung

_Worum geht es? Wer ist hauptverantwortlich? Links zu Dokumenten …_

## Anstehende Termine

```dataview
TABLE WITHOUT ID file.link AS Termin, datum AS Datum, uhrzeit AS Uhrzeit, art AS Art, status AS Status, zustaendig AS Zuständig
FROM "{{appointments}}"
WHERE (thema = this.file.link OR thema.oberthema = this.file.link) AND datum >= date(today)
SORT datum ASC
```

## Termine ohne Datum

```dataview
TABLE WITHOUT ID file.link AS Termin, art AS Art, status AS Status, zustaendig AS Zuständig
FROM "{{appointments}}"
WHERE (thema = this.file.link OR thema.oberthema = this.file.link) AND !datum
```

## Vergangene Termine

```dataview
TABLE WITHOUT ID file.link AS Termin, datum AS Datum, art AS Art, status AS Status, zustaendig AS Zuständig
FROM "{{appointments}}"
WHERE (thema = this.file.link OR thema.oberthema = this.file.link) AND datum < date(today)
SORT datum DESC
```

## Unterthemen

```dataview
LIST FROM "{{topics}}" WHERE oberthema = this.file.link
```
