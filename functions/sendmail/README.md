# Sendmail Cloud Function

Dieser Ordner enthält eine eigenständige Google Cloud Function, die täglich
E-Mails mit einem zusammengefassten Bericht versendet. Sie ist bewusst
**unabhängig** vom restlichen Projekt `rss_mail_summarizer` und benötigt keine
Rückverweise auf andere Verzeichnisse.

## Inhalt

- `main.py` – enthält **alle** benötigten Klassen und Funktionen (LLM‑Zusammenfassung, Mail-Generierung, Firestore-Zugriff etc.) in der Klasse `SendMailService`. Dies ist der einzige Quellcode, der für Deployment nötig ist.
- `database.py` – reines Firestore-/Datenbankmodul (unverändert).
- `cloudbuild.yaml` – Build‑ und Deploy-Skript für diese Funktion.
- `requirements.txt` – benötigte Python-Abhängigkeiten.

*Hinweis:* frühere Dateien (`send_mail.py`, `llm_calls.py`, `llm_youtube_calls.py`, `utils/logger.py`) sind nicht mehr notwendig und können gelöscht; ihre Funktionalität wurde in `main.py` übernommen.

## Deployment

1. Stelle sicher, dass sich die Arbeitsverzeichnisse und die
   Credential-Dateien (`serviceAccountKey.json`, Gmail `credentials.json`,
   `token.json`) im Ordner befinden oder über Umgebungsvariablen/Secrets
   bereitgestellt werden.
2. Konfiguriere die Umgebungsvariablen in der Cloud Function:
   - `PROJECT_ID`, `SENDER_EMAIL`, `RECIPIENT_EMAIL`, `LOG_LEVEL`, etc.
   - Geheimnisse wie `RSS_FIREBASE_KEY`, `GEMINI_API_KEY` sollten über den
     Secret Manager eingebunden werden.
3. Deploy mit `gcloud functions deploy sendmail_trigger --runtime python310 \
   --trigger-http --allow-unauthenticated` (oder gemäß deiner üblichen
   Konfiguration).

Die Funktion `sendmail_trigger` kann vom Scheduler oder einem anderen
Trigger (z. B. Pub/Sub) angesprochen werden, um den Versand auszulösen.
