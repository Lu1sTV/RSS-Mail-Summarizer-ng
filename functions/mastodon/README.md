# Mastodon Connector

Dieses Projekt ist eine Google Cloud Function, die automatisiert Mastodon-Toots eines konfigurierten Accounts ausliest, enthaltene Links extrahiert und in einer Google Firestore Datenbank speichert.

## Aufbau und Funktionen

Das Projekt ist modular aufgebaut und umfasst folgende Dateien:

* **Config (`config.py`)**: Feed-Definitionen (`MASTODON_FEEDS`), Abruf-Limit (`ENTRY_LIMIT`) und Sync-Modus (`FETCH_ALL_SINCE_LAST`).
* **Database (`database.py`)**: Firestore-Anbindung - speichert extrahierte URLs in der Collection `website` und verwaltet den Cursor (`toot_id`) in `mastodon_toots`.
* **MastodonService (`mastodon_service.py`)**: Ruft Toots ueber die Mastodon API ab, nutzt Cursor-basiertes Nachladen und extrahiert externe Links aus dem HTML-Inhalt.
* **mastodon_connector_activate (`main.py`)**: HTTP-Einstiegspunkt - koordiniert den gesamten Pipeline-Ablauf.

## Systemvoraussetzungen (Requirements)

* Python 3.11
* `requirements.txt`:
  * `beautifulsoup4==4.12.3`
  * `firebase-admin==6.6.0`
  * `functions-framework==3.9.2`
  * `Mastodon.py==2.0.1`
  * `python-dotenv==1.0.1`

Zusaetzlich wird fuer lokale Tests benoetigt:
* `serviceAccountKey.json` (Firebase/GCP Service Account Key)

## Lokales Setup und Testen

1. Erstelle eine virtuelle Umgebung mit Python 3.11 im Root-Verzeichnis und aktiviere sie:
	```bash
	python3.11 -m venv venv
	source venv/bin/activate
	```
2. Installiere die Abhaengigkeiten:
	```bash
	cd functions/mastodon
	pip install -r requirements.txt
	cd ../..
	```
3. Platziere die `serviceAccountKey.json` im Ordner `functions/mastodon/`.
4. Starte den lokalen Server aus `functions/mastodon/`:
	```bash
	cd functions/mastodon
	functions-framework --target=mastodon_connector_activate --debug
	```
5. Loese die Funktion in einem zweiten Terminal-Fenster aus:
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
3. Erstelle das Secret fuer die Firestore-Credentials:
	```bash
	gcloud secrets create rss-firebase-key --replication-policy="automatic"
	```
4. Lade die lokale Datei in das Secret hoch:
	```bash
	gcloud secrets versions add rss-firebase-key --data-file="functions/mastodon/serviceAccountKey.json"
	```
5. Erteile dem Dienstkonto der Cloud Function die Berechtigung, das Secret auszulesen:
	```bash
	gcloud secrets add-iam-policy-binding rss-firebase-key \
	  --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>" \
	  --role="roles/secretmanager.secretAccessor"
	```
6. Fuehre den Deployment-Befehl aus dem Hauptverzeichnis aus:
	```bash
	gcloud functions deploy mastodon-connector \
	  --gen2 \
	  --region=europe-west3 \
	  --source=functions/mastodon \
	  --entry-point=mastodon_connector_activate \
	  --trigger-http \
	  --runtime=python311 \
	  --memory=2GiB \
	  --timeout=120s \
	  --set-secrets=RSS_FIREBASE_KEY=rss-firebase-key:latest \
	  --set-env-vars=PROJECT_ID=<PROJECT_ID>,LOG_LEVEL=DEBUG
	```

## Automatisierung mit Cloud Scheduler

Um die Cloud Function automatisch alle 2 Stunden auszufuehren, wird ein Cloud Scheduler Job eingerichtet.

1. Erteile dem Dienstkonto die Berechtigung, die Cloud Function (Gen 2) aufzurufen:
	```bash
	gcloud functions add-invoker-policy-binding mastodon-connector \
	  --region=europe-west3 \
	  --member="serviceAccount:<SERVICE_ACCOUNT_EMAIL>"
	```
2. Erstelle den Scheduler-Job:
	```bash
	gcloud scheduler jobs create http mastodon-scheduler \
	  --schedule="0 */2 * * *" \
	  --time-zone="Europe/Berlin" \
	  --uri="<CLOUD_FUNCTION_URL>" \
	  --http-method=POST \
	  --oidc-service-account-email="<SERVICE_ACCOUNT_EMAIL>" \
	  --location=europe-west3
	```

## Hinweis

Fuer das komplette Projekt-Initialsetup (APIs, globale Secrets, Trigger, Scheduler) siehe [InitialSetup.md](../../InitialSetup.md).
