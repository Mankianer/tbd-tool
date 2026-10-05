# Anstehende Termine

```dataview
TABLE WITHOUT ID file.link AS Termin, datum AS Datum, uhrzeit AS Uhrzeit, art AS Art, thema AS Thema, zustaendig AS Zuständig, status AS Status
FROM "{{appointments}}" OR "{{protocols}}"
WHERE datum >= date(today) AND status != "abgesagt" AND status != "vorschlag"
SORT datum ASC
```

## Offene Vorschläge

```dataview
TABLE WITHOUT ID file.link AS Termin, datum AS Datum, thema AS Thema
FROM "{{appointments}}"
WHERE status = "vorschlag" AND datum >= date(today)
SORT datum ASC
```
