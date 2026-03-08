# RSS Connector

Dieses Projekt ist eine Google Cloud Function, die automatisiert RSS/Atom Feeds abruft, neue Artikel filtert, Metadaten extrahiert und die Links in einer Google Firestore Datenbank speichert.

## Aufbau und Funktionen

Das Projekt ist modular aufgebaut und umfasst folgende Dateien:

* **Config (`config.py`)**: Zentrale Feed-Konfiguration. Jeder Feed definiert Name, URL, Crawl-Modus (`since_last_crawl` oder `time_window`), optionales Zeitfenster in Stunden und ETag-Support.
* **Database (`database.py`)**: Firestore-Anbindung - speichert extrahierte URLs in der Collection `website` (inkl. RSS-Metadaten) und verwaltet den Crawl-Status pro Feed in der Collection `rss_feeds_state`.
* **RSSService (`rss_service.py`)**: Geschaeftslogik - holt Feeds mit `feedparser`, unterstuetzt Conditional GET (ETag/Last-Modified), filtert Eintraege nach Modus und uebergibt Links an die Datenbank.
* **rss_connector (`main.py`)**: HTTP-Einstiegspunkt - koordiniert den gesamten Pipeline-Ablauf fuer alle konfigurierten Feeds.

### Crawl-Modi

* **`since_last_crawl`**: Speichert das Datum des neuesten Artikels. Beim naechsten Lauf werden nur neuere Artikel geladen.
* **`time_window`**: Laedt alle Artikel innerhalb der letzten N Stunden, unabhaengig vom letzten Crawl.

## Systemvoraussetzungen (Requirements)

* Python 3.11
* `requirements.txt`:
  * `firebase-admin==7.2.0`
  * `functions-framework==3.10.1`
  * `feedparser==6.0.12`
  * `python-dotenv==1.2.2`

Zusaetzlich wird folgende Authentifizierungsdatei fuer lokale Tests benoetigt:
* `keys/serviceAccountKey.json` (Firebase/GCP Service Account Key)

## Lokales Setup und Testen

1. Erstelle eine virtuelle Umgebung mit Python 3.11 im Root-Verzeichnis und aktiviere sie:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   ```
2. Installiere die Abhaengigkeiten:
   ```bash
   cd functions/rss
   pip install -r requirements.txt
   cd ../..
   ```
3. Platziere die `serviceAccountKey.json` im Ordner `keys/`.
4. Passe bei Bedarf die Feed-Konfiguration in `config.py` an.
5. Starte den lokalen Server aus dem Hauptverzeichnis:
   ```bash
   functions-framework --target=rss_connector --debug
   ```
6. Loese die Funktion in einem zweiten Terminal-Fenster aus:
   ```bash
   curl http://localhost:8080
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
3. Erstelle das Secret fuer die Zugangsdaten im Google Cloud Secret Manager:
   ```bash
   gcloud secrets create rss-firebase-key --replication-policy="automatic"
   ```
4. Lade die lokale Datei in das erstellte Secret hoch:
   ```bash
   gcloud secrets versions add rss-firebase-key --data-file="keys/serviceAccountKey.json"
   ```
5. Erteile dem Dienstkonto der Cloud Function die Berechtigung, das Secret auszulesen:
   ```bash
   gcloud secrets add-iam-policy-binding rss-firebase-key \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
     --role="roles/secretmanager.secretAccessor"
   ```
6. Fuehre den Deployment-Befehl aus dem Hauptverzeichnis aus:
   ```bash
   gcloud functions deploy rss-connector \
     --gen2 \
     --region=europe-west3 \
     --source=functions/rss \
     --entry-point=rss_connector \
     --trigger-http \
     --runtime=python311 \
     --memory=1GiB \
     --timeout=540s \
     --set-secrets=RSS_FIREBASE_KEY=rss-firebase-key:latest \
     --set-env-vars=PROJECT_ID=<PROJECT_ID>,LOG_LEVEL=INFO
   ```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch alle 2 Stunden auszufuehren, wird ein Cloud Scheduler Job eingerichtet.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
   ```bash
   gcloud functions add-invoker-policy-binding rss-connector \
     --region=europe-west3 \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>"
   ```
2. Erstelle den Scheduler-Job:
   ```bash
   gcloud scheduler jobs create http rss-scheduler \
     --schedule="0 */2 * * *" \
     --time-zone="Europe/Berlin" \
     --uri="<CLOUD_FUNCTION_URL>" \
     --http-method=POST \
     --oidc-service-account-email="<SERVICE_ACCOUNT_EMAIL>" \
     --location=europe-west3
   ```

## Hinweis

Fuer das komplette Projekt-Initialsetup (APIs, globale Secrets, Trigger, Scheduler) siehe [InitialSetup.md](../../InitialSetup.md).

