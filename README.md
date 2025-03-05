## Aktueller Stand:
Artikel eines RSS Feeds werden zusammengefasst und (unter)kategorisiert. Die Ergebnisse werden zweimal täglich per Mail versandt und in einer Firestore Datenbank gespeichert.

Außerdem können Fragen wie beispielsweise "Welche Artikel zu Trump wurden letzte Woche veröffentlicht?" durch ein RAG System beantwortet werden, wobei diese Funktionalität noch ausgebaut werden muss.

## Hinweise zum Verwenden:
Um das Programm zu verwenden, müssen folgende Umgebungsvariablen in einer .env file hinterlegt werden:

- **GEMINI_API_KEY**: (kann hier erstellt werden: https://ai.google.dev/gemini-api/docs/api-key?hl=de)

- **SENDER_PASSWORD**: (Hiermit ist das App Passwort für den Gmail Account gemeint)

Außerdem müssen folgende Dateien angelegt werden:

- "rag/rag-account-service.key.json"

- "rss_mail_summarizer/serviceAccountKey.json"

