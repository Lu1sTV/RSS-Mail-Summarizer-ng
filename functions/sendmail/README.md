# Sendmail Cloud Function

Dieses Projekt ist eine Google Cloud Function, die ungesendete Eintraege aus Firestore laedt, fehlende Zusammenfassungen mit Gemini erzeugt, einen Report erstellt und per Gmail versendet.

## Aufbau und Funktionen

Das Projekt ist modular aufgebaut und umfasst folgende Dateien:

* **Config (`config.py`)**: Quellen-Filter (`SOURCES`), maximale Anzahl Eintraege (`LIMIT`) und optionales Zeitfenster (`TIME_WINDOW_HOURS`).
* **Database (`database.py`)**: Firestore-Anbindung - laedt `mail_sent=False` Eintraege, speichert Summary-Updates und markiert versendete Eintraege.
* **Helpers (`helpers.py`)**: Gmail-Versand, Report-Erzeugung (`markdown_report.md`) und AI-Logik fuer Website-/YouTube-Summaries.
* **Utils (`utils.py`)**: Hilfsfunktionen fuer API-Key-Sanitisierung.
* **SendMailService (`main.py`)**: Orchestriert den Ablauf (laden, filtern, zusammenfassen, Report erzeugen, Mail senden, als gesendet markieren).
* **sendmail_trigger (`main.py`)**: HTTP-Einstiegspunkt - wird von Scheduler oder manuell aufgerufen.

## Systemvoraussetzungen (Requirements)

* Python 3.11
* `requirements.txt`:
  * `firebase-admin==6.6.0`
  * `functions-framework==3.9.2`
  * `google-api-python-client>=2.100.0`
  * `langchain-core==0.3.40`
  * `langchain-google-genai==2.0.9`
  * `google-genai==1.36.0`
  * `google-cloud-secret-manager`
  * `Markdown==3.7`
  * `python-dotenv==1.0.1`

Zusaetzlich werden fuer lokale Tests typischerweise benoetigt:
* `serviceAccountKey.json` (lokale Firestore-Authentifizierung)
* Gmail Token als Umgebungsvariable `CREDENTIALS_TOKEN_JSON` (oder lokal als `credentials/token.json`)
* `GEMINI_API_KEY` (oder `GEMINI_API_KEY_SECRET`)

## Lokales Setup und Testen

1. Erstelle eine virtuelle Umgebung mit Python 3.11 im Root-Verzeichnis und aktiviere sie:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   ```
2. Installiere die Abhaengigkeiten:
   ```bash
   cd functions/sendmail
   pip install -r requirements.txt
   cd ../..
   ```
3. Setze lokale Umgebungsvariablen (z. B. ueber `.env` im Repo-Root):
   ```env
   SENDER_EMAIL=<SENDER_EMAIL>
   RECIPIENT_EMAIL=<RECIPIENT_EMAIL>
   GEMINI_API_KEY=<GEMINI_API_KEY>
   CREDENTIALS_TOKEN_JSON='<GMAIL_TOKEN_JSON>'
   PROJECT_ID=<PROJECT_ID>
   LOG_LEVEL=INFO
   ```
4. Lege optional `serviceAccountKey.json` im Repo-Root ab (falls `RSS_FIREBASE_KEY` nicht als JSON-Env gesetzt ist).
5. Starte den lokalen Server aus dem Repo-Root:
   ```bash
   functions-framework --target=sendmail_trigger --debug
   ```
6. Loese die Funktion in einem zweiten Terminal-Fenster aus:
   ```bash
   curl -X POST http://localhost:8080
   ```

## Deployment in die Google Cloud (GCP)

1. Authentifiziere dich im Terminal:
   ```bash
   gcloud auth login
   ```
2. Verknuepfe das CLI mit deinem Google Cloud Projekt:
   ```bash
   gcloud config set project <PROJECT_ID>
   ```
3. Erstelle benoetigte Secrets im Secret Manager:
   ```bash
   gcloud secrets create gmail-credentials --replication-policy="automatic"
   gcloud secrets create gmail-token --replication-policy="automatic"
   gcloud secrets create gemini-api-key --replication-policy="automatic"
   gcloud secrets create sender-email --replication-policy="automatic"
   gcloud secrets create recipient-email --replication-policy="automatic"
   gcloud secrets create rss-firebase-key --replication-policy="automatic"
   ```
4. Lade lokale Dateien/Werte in die Secrets hoch:
   ```bash
   gcloud secrets versions add gmail-credentials --data-file="keys/gmail_credentials.json"
   gcloud secrets versions add gmail-token --data-file="keys/token.json"
   gcloud secrets versions add gemini-api-key --data-file=- <<< "<GEMINI_API_KEY>"
   gcloud secrets versions add sender-email --data-file=- <<< "<SENDER_EMAIL>"
   gcloud secrets versions add recipient-email --data-file=- <<< "<RECIPIENT_EMAIL>"
   gcloud secrets versions add rss-firebase-key --data-file="keys/serviceAccountKey.json"
   ```
5. Erteile dem Dienstkonto die Secret-Accessor-Berechtigung fuer alle benoetigten Secrets.
6. Fuehre den Deployment-Befehl aus dem Hauptverzeichnis aus:
   ```bash
   gcloud functions deploy sendmail-trigger \
     --gen2 \
     --region=europe-west3 \
     --source=functions/sendmail \
     --entry-point=sendmail_trigger \
     --trigger-http \
     --runtime=python311 \
     --memory=2GiB \
     --timeout=300s \
     --set-secrets=CREDENTIALS_CREDENTIALS_JSON=gmail-credentials:latest,CREDENTIALS_TOKEN_JSON=gmail-token:latest,GEMINI_API_KEY=gemini-api-key:latest,RECIPIENT_EMAIL=recipient-email:latest,RSS_FIREBASE_KEY=rss-firebase-key:latest,SENDER_EMAIL=sender-email:latest \
     --set-env-vars=PROJECT_ID=<PROJECT_ID>,LOG_LEVEL=INFO
   ```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch um 08:00 und 20:00 Uhr deutscher Zeit auszufuehren, wird ein Cloud Scheduler Job eingerichtet.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
   ```bash
   gcloud functions add-invoker-policy-binding sendmail-trigger \
     --region=europe-west3 \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>"
   ```
2. Erstelle den Scheduler-Job:
   ```bash
   gcloud scheduler jobs create http sendmail-scheduler \
     --schedule="0 8,20 * * *" \
     --time-zone="Europe/Berlin" \
     --uri="<CLOUD_FUNCTION_URL>" \
     --http-method=POST \
     --oidc-service-account-email="<SERVICE_ACCOUNT_EMAIL>" \
     --location=europe-west3
   ```

## Hinweis

Fuer das komplette Projekt-Initialsetup (APIs, globale Secrets, Trigger, Scheduler) siehe [InitialSetup.md](../../InitialSetup.md).

