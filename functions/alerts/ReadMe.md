# Gmail Alerts Processor

Dieses Projekt ist eine Google Cloud Function, die automatisiert E-Mails mit Google Alerts über die Gmail-API ausliest, enthaltene Links extrahiert, bereinigt und in einer Google Firestore Datenbank speichert.

## Aufbau und Funktionen

Das Skript (`main.py`) ist objektorientiert aufgebaut und umfasst folgende Kernkomponenten:

* **Config**: Enthält statische Konfigurationsdaten wie Label-Namen, Blacklists für URLs und API-Scopes.
* **FirestoreDatabase**: Initialisiert die Verbindung zu Firebase/Firestore und speichert die validierten URLs in der Collection `website`.
* **GmailService**: Verwaltet die Authentifizierung mit der Gmail-API, ruft E-Mails ab, extrahiert den HTML-Body und verschiebt verarbeitete E-Mails in ein neues Label.
* **AlertProcessor**: Koordiniert den Ablauf. Parst das HTML mit BeautifulSoup, bereinigt Google-Weiterleitungs-URLs, prüft gegen die Blacklist und übergibt gültige Links an die Datenbank.
* **alerts_mvp_endpoint**: Der HTTP-Einstiegspunkt für das Functions Framework, der bei Aufruf der Cloud Function ausgeführt wird.

## Systemvoraussetzungen (Requirements)

* Python 3.11
* `requirements.txt`:
  * `functions-framework==3.5.0`
  * `google-api-python-client>=2.0.0`
  * `google-auth-oauthlib>=1.0.0`
  * `firebase-admin>=6.0.0`
  * `beautifulsoup4>=4.12.0`

Zusätzlich werden folgende Authentifizierungsdateien im Ordner `keys/` benötigt:
* `credentials.json` (OAuth2 Client-ID für Gmail)
* `serviceAccountKey.json` (Firebase/GCP Service Account Key)

## Lokales Setup und Testen

1. Erstelle eine virtuelle Umgebung mit Python 3.11 und aktiviere sie.
2. Installiere die Abhängigkeiten:
   ```bash
   pip install -r requirements.txt
   ```
3. Platziere die `credentials.json` und `serviceAccountKey.json` im Ordner `keys/`.
4. Navigiere in den Ordner `keys/` und generiere das Token (öffnet den Browser für den Google-Login):
   ```bash
   cd keys
   python generate_token.py
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

1. Lade das Google Cloud CLI herunter und installiere es (https://cloud.google.com/sdk/docs/install).
2. Authentifiziere dich im Terminal:
   ```bash
   gcloud auth login
   ```
3. Verknüpfe das CLI mit deinem Google Cloud Projekt:
   ```bash
   gcloud config set project <PROJECT_ID>
   ```
4. Führe den Deployment-Befehl aus dem Hauptverzeichnis aus:
   ```bash
   gcloud functions deploy alerts-handler \
     --gen2 \
     --region=europe-west3 \
     --source=. \
     --entry-point=alerts_mvp_endpoint \
     --trigger-http \
     --runtime=python311 \
     --memory=512MiB \
     --timeout=60s
   ```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch um 08:00 und 16:00 Uhr deutscher Zeit auszuführen, wird ein Cloud Scheduler Job eingerichtet. Dieser benötigt zwingend eine OIDC-Authentifizierung.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
   ```bash
   gcloud functions add-invoker-policy-binding alerts-handler \
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