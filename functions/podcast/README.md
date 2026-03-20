# Podcast Generator

Dieses Projekt ist eine Google Cloud Function, die automatisiert ungelesene Artikel und Posts aus einer Firestore-Datenbank ausliest, daraus mit Gemini ein Podcast-Skript erstellt, dieses per Google Cloud Text-to-Speech (TTS) vertont und die fertige MP3-Datei in einen Google Cloud Storage Bucket hochlädt.

## Module

| Modul | Verantwortlichkeit |
|---|---|
| `config.py` | Zentrale Konfiguration: Quellen, Limit, Zeitfenster, Gemini-Parameter (Temperatur, max. Output-Tokens), TTS-Stimmen + Sample-Rate, Podcast-Ziellaenge (min/max Minuten), Signed-URL-Ablaufdauer. |
| `database.py` | Firestore-Anbindung: laedt unverarbeitete Eintraege, filtert nach `podcast_generated`, markiert verarbeitete Docs per Batch-Update. |
| `GCPAuthService` | Authentifizierung gegenueber GCP-Diensten (TTS, Storage, Gmail, Gemini). Laedt SA-Credentials aus `RSS_FIREBASE_KEY` oder lokal `keys/serviceAccountKey.json`, baut Gmail-Client aus `GMAIL_TOKEN_JSON`. |
| `PodcastAIService` | Web-Scraping via BeautifulSoup, YouTube-Zusammenfassungen via GenAI SDK, Skriptgenerierung mit Gemini 2.5 Flash (JSON-Array, 2 Stimmen). Wortbasierte Laengenvalidierung + Retry + URL-Bereinigung. |
| `AudioService` | TTS-Synthese mit Journey-Stimmen (`de-DE-Journey-D` / `de-DE-Journey-F`), GCS-Upload (MP3), V4-Signed-URL-Generierung. |
| `PodcastMailService` | HTML-E-Mail mit signiertem Download-Link ueber die Gmail-API. |
| `podcast_trigger` | HTTP-Einstiegspunkt: koordiniert die Pipeline, einheitliches JSON-Response-Schema (`status`, `resource`, `details`). |

## Systemvoraussetzungen (Requirements)

* Python 3.11
* `requirements.txt`:
  * `functions-framework==3.9.2`
  * `firebase-admin>=6.0.0`
  * `google-cloud-texttospeech>=2.0.0`
  * `google-cloud-storage>=2.0.0`
  * `google-genai>=0.3.0`
  * `requests>=2.31.0`
  * `beautifulsoup4>=4.12.0`

Zusätzlich wird folgende Authentifizierungsdatei im Ordner `keys/` für lokale Tests benötigt:
* `serviceAccountKey.json` (Firebase/GCP Service Account Key)

## Lokales Setup und Testen

1. Erstelle eine virtuelle Umgebung mit Python 3.11 im Root-Verzeichnis und aktiviere sie:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   ```
2. Installiere die Abhängigkeiten:
   ```bash
   pip install -r requirements.txt
   ```
3. Platziere die `serviceAccountKey.json` im Ordner `keys/`.
4. Setze die benötigten Umgebungsvariablen für den lokalen Test (ersetze die Platzhalter):
   ```bash
   export GEMINI_API_KEY="dein_gemini_api_key"
   export GCS_BUCKET_NAME="dein-podcast-bucket"
   export SENDER_EMAIL="sender@example.com"
   export RECIPIENT_EMAIL="user@example.com"
   export GMAIL_TOKEN_JSON='{"token":"...","refresh_token":"...","token_uri":"https://oauth2.googleapis.com/token","client_id":"...","client_secret":"...","scopes":["https://www.googleapis.com/auth/gmail.modify"]}'
   ```
5. Starte den lokalen Server aus dem Hauptverzeichnis:
   ```bash
   functions-framework --target=podcast_trigger --debug
   ```
6. Löse die Funktion in einem zweiten Terminal-Fenster aus:
   ```bash
   curl http://localhost:8080
   ```

## Deployment in die Google Cloud (GCP)

1. Authentifiziere dich im Terminal:
   ```bash
   gcloud auth login
   ```
2. Verknüpfe das CLI mit deinem Google Cloud Projekt:
   ```bash
   gcloud config set project <PROJECT_ID>
   ```
3. Erstelle die benötigten Secrets im Google Cloud Secret Manager:
   ```bash
   gcloud secrets create rss-firebase-key --replication-policy="automatic"
   gcloud secrets create gemini-api-key --replication-policy="automatic"
   gcloud secrets create gcs-bucket-name --replication-policy="automatic"
   gcloud secrets create sender-email --replication-policy="automatic"
   gcloud secrets create recipient-email --replication-policy="automatic"
   gcloud secrets create gmail-token --replication-policy="automatic"
   ```
4. Lade die Keys und Werte in die erstellten Secrets hoch:
   ```bash
   gcloud secrets versions add rss-firebase-key --data-file="keys/serviceAccountKey.json"
   echo -n "DEIN_GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
   echo -n "DEIN_PODCAST_BUCKET" | gcloud secrets versions add gcs-bucket-name --data-file=-
   echo -n "sender@example.com" | gcloud secrets versions add sender-email --data-file=-
   echo -n "user@example.com" | gcloud secrets versions add recipient-email --data-file=-
   cat keys/token.json | gcloud secrets versions add gmail-token --data-file=-
   ```
5. Erteile dem Dienstkonto der Cloud Function die Berechtigung, die Secrets auszulesen:
   ```bash
   gcloud secrets add-iam-policy-binding rss-firebase-key \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
     --role="roles/secretmanager.secretAccessor"

   gcloud secrets add-iam-policy-binding gemini-api-key \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
     --role="roles/secretmanager.secretAccessor"

   gcloud secrets add-iam-policy-binding gcs-bucket-name \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
     --role="roles/secretmanager.secretAccessor"
   ```
6. Erteile dem Dienstkonto die Berechtigung, Dateien in den Cloud Storage Bucket zu schreiben:
   ```bash
   gcloud storage buckets add-iam-policy-binding gs://<DEIN_PODCAST_BUCKET> \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
     --role="roles/storage.objectUser"
   ```
7. Führe den Deployment-Befehl aus dem Hauptverzeichnis aus:
   ```bash
   gcloud functions deploy podcast-trigger \
     --gen2 \
     --region=europe-west3 \
     --source=. \
     --entry-point=podcast_trigger \
     --trigger-http \
     --runtime=python311 \
     --memory=4GiB \
     --timeout=600s \
       --set-secrets=GCS_BUCKET_NAME=gcs-bucket-name:latest,RSS_FIREBASE_KEY=rss-firebase-key:latest,GEMINI_API_KEY=gemini-api-key:latest,SENDER_EMAIL=sender-email:latest,RECIPIENT_EMAIL=recipient-email:latest,GMAIL_TOKEN_JSON=gmail-token:latest
   ```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch einmal täglich (z. B. um 06:00 Uhr deutscher Zeit) auszuführen, wird ein Cloud Scheduler Job eingerichtet.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
   ```bash
   gcloud functions add-invoker-policy-binding podcast-trigger \
     --region=europe-west3 \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>"
   ```
2. Erstelle den Scheduler-Job:
   ```bash
   gcloud scheduler jobs create http podcast-scheduler \
     --schedule="0 6 * * *" \
     --time-zone="Europe/Berlin" \
     --uri="<CLOUD_FUNCTION_URL>" \
     --http-method=GET \
     --oidc-service-account-email="<SERVICE_ACCOUNT_EMAIL>" \
     --location=europe-west3
   ```

## Architektur

```
Cloud Scheduler (cron)
        |
        v
podcast_trigger (HTTP Entry Point)
        |
        v
FirestoreDatabase.fetch_entries()
        |   Firestore Collection "website"
        |   filtert: podcast_generated == False
        v
PodcastAIService.fetch_raw_content(urls)
        |   Web-URLs  --> BeautifulSoup (requests + HTML-Parser)
        |   YouTube   --> Gemini GenAI SDK (video/* summarization)
        v
PodcastAIService.generate_script(content)
        |   Gemini 2.5 Flash (JSON-Array, 2 Stimmen)
        |   Laengenvalidierung (Wortanzahl / WPM)
        |   Retry bei zu kurzem Skript
        |   URL-Bereinigung (_strip_urls)
        v
AudioService.generate_and_upload(script)
        |   Google Cloud TTS (Journey-Stimmen)
        |   Upload --> GCS Bucket (MP3)
        v
AudioService.generate_signed_url(filename)
        |   V4 Signed URL (konfigurierbare Ablaufdauer)
        v
PodcastMailService.send_podcast_mail()
        |   Gmail API --> HTML-Mail mit Download-Link
        v
FirestoreDatabase.mark_as_podcast_generated()
        |   Batch-Update: podcast_generated = True
        v
    JSON Response {status, resource, details}
```

## Hinweis

Fuer das komplette Projekt-Initialsetup (APIs, globale Secrets, Trigger, Scheduler) siehe [InitialSetup.md](../../InitialSetup.md).