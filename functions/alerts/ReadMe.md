# Gmail Alerts Processor

Dieses Projekt ist eine Google Cloud Function, die automatisiert E-Mails mit Google Alerts über die Gmail-API ausliest, enthaltene Links extrahiert, bereinigt und in einer Google Firestore Datenbank speichert.

## Aufbau und Funktionen

Das Projekt ist modular aufgebaut und umfasst folgende Dateien:

* **Config (`config.py`)**: Alert-Label-Definitionen, URL-Blacklist, Gmail-Scopes, max. Nachrichten pro Abruf (`MAX_RESULTS`) und optionales Max-Alter in Tagen (`MAX_AGE_DAYS`).
* **Database (`database.py`)**: Firestore-Anbindung – speichert extrahierte URLs in der Collection `website` (inkl. `podcast_generated=False`).
* **GmailService (`main.py`)**: Gmail-API-Client – liest Mails per Label, extrahiert HTML-Body, verschiebt verarbeitete Mails. Respektiert `MAX_RESULTS` und `MAX_AGE_DAYS` aus der Config.
* **AlertProcessor (`main.py`)**: Parst HTML mit BeautifulSoup, bereinigt Google-Redirect-URLs, prüft gegen Blacklist und übergibt Links an die Datenbank.
* **alerts_mvp_endpoint (`main.py`)**: HTTP-Einstiegspunkt – koordiniert den gesamten Pipeline-Ablauf.

## Systemvoraussetzungen (Requirements)

* Python 3.11
* `requirements.txt`:
  * `functions-framework==3.5.0`
  * `google-api-python-client>=2.0.0`
  * `google-auth-oauthlib>=1.0.0`
  * `firebase-admin>=6.0.0`
  * `beautifulsoup4>=4.12.0`

Zusätzlich werden folgende Authentifizierungsdateien im Ordner `keys/` benötigt, wenn lokal getestet wird:
* `credentials.json` (OAuth2 Client-ID für Gmail)
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
3. Platziere die `credentials.json` und `serviceAccountKey.json` im Ordner `keys/`.
4. Navigiere in den Ordner `keys/` und generiere das Token:
   ```bash
   cd keys
   python generate_gmail_token.py
   cd ..
   ```
5. Starte den lokalen Server aus dem Hauptverzeichnis:
   ```bash
   functions-framework --target=alerts_mvp_endpoint --debug
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
3. Erstelle die Secrets für die Zugangsdaten im Google Cloud Secret Manager:
   ```bash
   gcloud secrets create gmail-token --replication-policy="automatic"
   gcloud secrets create rss-firebase-key --replication-policy="automatic"
   ```
4. Lade die lokalen Dateien in die erstellten Secrets hoch:
   ```bash
   gcloud secrets versions add gmail-token --data-file="keys/token.json"
   gcloud secrets versions add rss-firebase-key --data-file="keys/serviceAccountKey.json"
   ```
5. Erteile dem Dienstkonto der Cloud Function die Berechtigung, die Secrets auszulesen:
   ```bash
   gcloud secrets add-iam-policy-binding gmail-token \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
     --role="roles/secretmanager.secretAccessor"

   gcloud secrets add-iam-policy-binding rss-firebase-key \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
     --role="roles/secretmanager.secretAccessor"
   ```
6. Führe den Deployment-Befehl aus dem Hauptverzeichnis aus. Die Secrets werden dabei automatisch als Umgebungsvariablen eingebunden:
   ```bash
   gcloud functions deploy alerts-connector \
     --gen2 \
     --region=europe-west3 \
     --source=. \
     --entry-point=alerts_mvp_endpoint \
     --trigger-http \
     --runtime=python311 \
     --memory=512MiB \
     --timeout=60s \
     --set-secrets=GMAIL_TOKEN_JSON=gmail-token:latest,RSS_FIREBASE_KEY=rss-firebase-key:latest
   ```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch um 08:00 und 16:00 Uhr deutscher Zeit auszuführen, wird ein Cloud Scheduler Job eingerichtet.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
   ```bash
   gcloud functions add-invoker-policy-binding alerts-connector \
     --region=europe-west3 \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>"
   ```
2. Erstelle den Scheduler-Job:
   ```bash
   gcloud scheduler jobs create http alerts-scheduler \
     --schedule="0 8,16 * * *" \
     --time-zone="Europe/Berlin" \
     --uri="<CLOUD_FUNCTION_URL>" \
     --http-method=GET \
     --oidc-service-account-email="<SERVICE_ACCOUNT_EMAIL>" \
     --location=europe-west3
   ```

## Hinweis

Fuer das komplette Projekt-Initialsetup (APIs, globale Secrets, Trigger, Scheduler) siehe [InitialSetup.md](../../InitialSetup.md).