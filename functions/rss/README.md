# RSS Connector

Dieses Projekt ist eine Google Cloud Function, die automatisiert RSS/Atom Feeds abruft, neue Artikel filtert, Metadaten extrahiert und die Links in einer Google Firestore Datenbank speichert.

## Aufbau und Funktionen

Das Projekt ist modular aufgebaut und umfasst folgende Dateien:

* **Config** (`config.py`): Zentrale Feed-Konfiguration. Jeder Feed definiert Name, URL, Crawl-Modus (`since_last_crawl` oder `time_window`), optionales Zeitfenster in Stunden und ETag-Support.
* **Database** (`database.py`): Firestore-Anbindung – speichert extrahierte URLs in der Collection `website` (inkl. RSS-Metadaten) und verwaltet den Crawl-Status pro Feed in der Collection `rss_feeds_state`.
* **RSSService** (`rss_service.py`): Geschäftslogik – holt Feeds mit `feedparser`, unterstützt Conditional GET (ETag/Last-Modified), filtert Einträge nach Modus, extrahiert Titel, Zusammenfassung und Veröffentlichungsdatum und übergibt Links an die Datenbank.
* **rss_connector** (`main.py`): HTTP-Einstiegspunkt – koordiniert den gesamten Pipeline-Ablauf für alle konfigurierten Feeds.

### Crawl-Modi

* **`since_last_crawl`**: Speichert das Datum des neuesten Artikels. Beim nächsten Lauf werden nur neuere Artikel geladen. Ideal für Feeds mit unregelmäßigen Updates (z. B. HackerNews).
* **`time_window`**: Lädt alle Artikel innerhalb der letzten N Stunden, unabhängig vom letzten Crawl. Ideal für hochfrequente Feeds (z. B. TechCrunch).

## Systemvoraussetzungen (Requirements)

* Python 3.11
* `requirements.txt`:
  * `firebase-admin==6.6.0`
  * `functions-framework==3.9.2`
  * `feedparser==6.0.11`
  * `python-dotenv==1.0.1`

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
4. Passe bei Bedarf die Feed-Konfiguration in `config.py` an:
   ```python
   RSS_FEEDS = [
       {
           "name": "my_feed",
           "url": "https://example.com/feed.xml",
           "mode": "since_last_crawl",
           "time_window_hours": None,
           "use_etag": True
       }
   ]
   ```
5. Starte den lokalen Server aus dem Hauptverzeichnis:
   ```bash
   functions-framework --target=rss_connector --debug
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
3. Erstelle das Secret für die Zugangsdaten im Google Cloud Secret Manager:
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
6. Führe den Deployment-Befehl aus dem Hauptverzeichnis aus. Das Secret wird dabei automatisch als Umgebungsvariable eingebunden:
   ```bash
   gcloud functions deploy rss_connector \
     --gen2 \
     --region=europe-west3 \
     --source=. \
     --entry-point=rss_connector \
     --trigger-http \
     --runtime=python311 \
     --memory=1GiB \
     --timeout=540s \
     --set-secrets=RSS_FIREBASE_KEY=rss-firebase-key:latest \
     --set-env-vars=LOG_LEVEL=INFO
   ```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch um 07:00 und 15:00 Uhr deutscher Zeit auszuführen, wird ein Cloud Scheduler Job eingerichtet.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
   ```bash
   gcloud functions add-invoker-policy-binding rss_connector \
     --region=europe-west3 \
     --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>"
   ```
2. Erstelle den Scheduler-Job:
   ```bash
   gcloud scheduler jobs create http rss-scheduler \
     --schedule="0 7,15 * * *" \
     --time-zone="Europe/Berlin" \
     --uri="<CLOUD_FUNCTION_URL>" \
     --http-method=GET \
     --oidc-service-account-email="<SERVICE_ACCOUNT_EMAIL>" \
     --location=europe-west3
   ```
