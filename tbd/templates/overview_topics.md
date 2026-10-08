---
aktuell_zeitraum: 14 days
---
# Themen

Ein Thema ist **aktuell**, wenn sein letzter Termin höchstens `= this.aktuell_zeitraum` zurückliegt
(oder noch bevorsteht). Den Zeitraum oben in den Properties anpassen, z.B. `21 days` oder `1 month`.
Unterthemen werden ihrem Hauptthema zugerechnet.

## Aktuelle Themen

```dataview
TABLE WITHOUT ID
  key AS Thema,
  minby(filter(rows, (r) => r.datum >= date(today)), (r) => r.datum).file.link AS "Nächster Termin",
  min(filter(rows.datum, (d) => d >= date(today))) AS "am",
  max(filter(rows.datum, (d) => d < date(today))) AS "Zuletzt",
  length(rows) AS Termine,
  unique(nonnull(flat(rows.zustaendig))) AS Zuständig
FROM "{{appointments}}"
WHERE thema AND datum
GROUP BY choice(thema.oberthema, thema.oberthema, thema)
WHERE max(rows.datum) >= date(today) - dur(this.aktuell_zeitraum)
SORT min(filter(rows.datum, (d) => d >= date(today))) ASC
```

## Vergangene Themen

```dataview
TABLE WITHOUT ID
  key AS Thema,
  max(rows.datum) AS "Letzter Termin",
  maxby(rows, (r) => r.datum).file.link AS "Was",
  length(rows) AS Termine
FROM "{{appointments}}"
WHERE thema AND datum
GROUP BY choice(thema.oberthema, thema.oberthema, thema)
WHERE max(rows.datum) < date(today) - dur(this.aktuell_zeitraum)
SORT max(rows.datum) DESC
```
