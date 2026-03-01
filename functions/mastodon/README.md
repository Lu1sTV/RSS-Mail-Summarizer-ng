# Mastodon Connector – Google Cloud Function

Modularer Microservice zur Synchronisation eines Mastodon-Accounts.  
Ruft neue Beiträge ab, extrahiert enthaltene Links inkl. Metadaten und persistiert sie strukturiert in Firestore zur weiteren Verarbeitung (z. B. KI-Zusammenfassung, RSS-Pipeline).


## Projektstruktur

```text
functions/mastodon/
├── main.py              # HTTP Entry-Point (Cloud Function)
├── mastodon_service.py  # Geschäftslogik (MastodonService)
├── database.py          # Firestore-Zugriffsschicht
├── requirements.txt     # Python-Abhängigkeiten
├── cloudbuild.yaml      # Build- & Deployment-Konfiguration
└── README.md            # Dokumentation
```
## Architektur & Kernfunktionen
Der Service wurde im Rahmen eines Refactorings aus dem ursprünglichen Monolithen extrahiert, um die Unabhängigkeit und Kaltstartzeiten zu optimieren.

### 1. MastodonService (mastodon_service.py)
Abruf: Identifiziert den Account über die Instanz-URL und den Benutzernamen.

Pagination: Speichert und nutzt die last_toot_id, um nur neue Beiträge seit dem letzten Aufruf zu laden.

Metadata Extraction: Extrahiert nicht nur URLs, sondern auch den Text des Toots (toot_text), den Link zum Original-Toot (toot_url) und das Erstellungsdatum (toot_date). Dies liefert wertvollen Kontext für die spätere KI-Zusammenfassung.

### 2. FirestoreRepository (database.py)
Bietet eine saubere Schnittstelle zur Firebase-Datenbank.

Verwaltet zwei Collections:

website: Speichert die extrahierten Links und deren Metadaten.

mastodon_toots: Speichert den Status der zuletzt verarbeiteten ID.

### 3. Entry-Point (main.py)
Verwendet das functions-framework, um die Logik als HTTP-Trigger bereitzustellen.

Nimmt Anfragen entgegen und stößt den Synchronisationsprozess an.

## Setup & Deployment
Lokale Vorbereitung
Installiere die notwendigen Bibliotheken für die Entwicklung:

```bash
pip install -r requirements.txt
```
Deployment zur Google Cloud
Das Deployment wird über Google Cloud Build gesteuert. Stelle sicher, dass du dich im Verzeichnis functions/mastodon/ befindest:

```bash
gcloud builds submit . --config cloudbuild.yaml --substitutions=_PROJECT_ID=[DEINE_PROJECT_ID]
```
## Konfiguration (Secrets & Umgebungsvariablen)
Der Service benötigt Zugriff auf folgende Ressourcen in GCP:

Secrets:

rss-firebase-key: Enthält die Service-Account-Informationen für Firestore.

Umgebungsvariablen:

LOG_LEVEL: Legt die Log-Ausführlichkeit fest (z. B. DEBUG, INFO).