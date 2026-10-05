# Deadlines

## Anstehend

```dataview
TABLE WITHOUT ID file.link AS Deadline, datum AS Datum, thema AS Thema, zustaendig AS Zuständig
FROM "{{appointments}}"
WHERE art = "deadline" AND datum >= date(today)
SORT datum ASC
```

## Vergangen

```dataview
TABLE WITHOUT ID file.link AS Deadline, datum AS Datum, thema AS Thema, zustaendig AS Zuständig
FROM "{{appointments}}"
WHERE art = "deadline" AND datum < date(today)
SORT datum DESC
```
