# Besprechungen

```dataview
TABLE WITHOUT ID file.link AS Besprechung, status AS Status, ort AS Ort, uhrzeit AS Uhrzeit
FROM "{{protocols}}"
WHERE typ = "besprechung"
SORT datum DESC
```
