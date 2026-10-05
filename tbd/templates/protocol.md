<!-- tbd:auto:start -->
<!-- tbd:auto:end -->

---

## Termine aus dieser Besprechung

```dataview
TABLE WITHOUT ID file.link AS Termin, datum AS Datum, thema AS Thema, zustaendig AS Zuständig
FROM "{{appointments}}"
WHERE contains(quellen, this.file.link)
SORT datum ASC
```

## Notizen

