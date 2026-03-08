# Podcast Generator

Dieses Projekt ist eine Google Cloud Function, die automatisiert ungelesene Artikel und Posts aus einer Firestore-Datenbank ausliest, daraus mit Gemini ein Podcast-Skript erstellt, dieses per Google Cloud Text-to-Speech (TTS) vertont und die fertige MP3-Datei in einen Google Cloud Storage Bucket hochlädt.

## Aufbau und Funktionen

Das Skript ist modular aufgebaut und umfasst folgende Kernkomponenten:

* **Config (`config.py`)**: Quellen (Mastodon, Alerts, RSS), Limit und optionales Zeitfenster.
* **Database (`database.py`)**: Firestore-Anbindung – lädt unverarbeitete Einträge anhand der Config, filtert clientseitig nach `podcast_generated` (fehlendes Feld = `False`) und markiert verarbeitete Docs.
* **PodcastAIService (`main.py`)**: Lädt Rohtexte von Web-URLs, erstellt YouTube-Zusammenfassungen über das Google GenAI SDK und generiert mit Gemini 2.5 Flash ein zweistimmiges Podcast-Skript als JSON-Array.
* **AudioService (`main.py`)**: Wandelt das Skript abwechselnd mit zwei TTS-Stimmen (`de-DE-Journey-D` / `de-DE-Journey-F`) in Audio um und lädt die MP3 in den konfigurierten GCS Bucket hoch.
* **podcast_trigger (`main.py`)**: HTTP-Einstiegspunkt – koordiniert den gesamten Pipeline-Ablauf.

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
   export CREDENTIALS_TOKEN_JSON='{"token":"...","refresh_token":"...","token_uri":"https://oauth2.googleapis.com/token","client_id":"...","client_secret":"...","scopes":["https://www.googleapis.com/auth/gmail.modify"]}'
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
   gcloud secrets create credentials-token-json --replication-policy="automatic"
   ```
4. Lade die Keys und Werte in die erstellten Secrets hoch:
   ```bash
   gcloud secrets versions add rss-firebase-key --data-file="keys/serviceAccountKey.json"
   echo -n "DEIN_GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key --data-file=-
   echo -n "DEIN_PODCAST_BUCKET" | gcloud secrets versions add gcs-bucket-name --data-file=-
   echo -n "sender@example.com" | gcloud secrets versions add sender-email --data-file=-
   echo -n "user@example.com" | gcloud secrets versions add recipient-email --data-file=-
   cat keys/token.json | gcloud secrets versions add credentials-token-json --data-file=-
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
       --set-secrets=GCS_BUCKET_NAME=gcs-bucket-name:latest,RSS_FIREBASE_KEY=rss-firebase-key:latest,GEMINI_API_KEY=gemini-api-key:latest,SENDER_EMAIL=sender-email:latest,RECIPIENT_EMAIL=recipient-email:latest,CREDENTIALS_TOKEN_JSON=credentials-token-json:latest
   ```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch einmal täglich (z. B. um 06:00 Uhr deutscher Zeit) auszuführen, wird ein Cloud Scheduler Job eingerichtet.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
   ```bash
   gcloud functions add-invoker-policy-binding podcast-generator \
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

## Hinweis

Fuer das komplette Projekt-Initialsetup (APIs, globale Secrets, Trigger, Scheduler) siehe [InitialSetup.md](../../InitialSetup.md).