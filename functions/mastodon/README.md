# Mastodon Connector Function

Refaktorierte Cloud Function für das Abrufen von Mastodon-Links.

## Struktur

```
functions/mastodon/
├── main.py                      # Cloud Function Entry-Point
├── mastodon_service.py          # Business Logic (MastodonService Klasse)
├── test_mastodon_service.py     # Unit Tests mit Mocks
├── requirements.txt             # Dependencies
├── cloudbuild.yaml              # Deployment Config
└── README.md
```

## Setup

### Lokal mit Mock-Tests

```bash
# Dependencies installieren
pip install -r requirements.txt

# Tests ausführen
pytest test_mastodon_service.py -v

# Speziellen Test ausführen
pytest test_mastodon_service.py::TestMastodonService::test_fetch_and_store_links_success_with_new_toots -v
```

### Lokal mit echtem Firebase (später)

```bash
# .env Datei mit RSS_FIREBASE_KEY erstellen
echo "RSS_FIREBASE_KEY=<your-firebase-key>" > .env

# Cloud Function lokal emulieren
functions-framework --target=mastodon_connector_activate --debug --port=8080

# In anderem Terminal testen
curl http://localhost:8080/
```

### Deploy zu Google Cloud

```bash
# Vom root des Projekts
cd functions/mastodon
gcloud builds submit . --config cloudbuild.yaml --substitutions=_PROJECT_ID=<your-project-id>
```

## Tests

### Mock-Tests (aktuell)

Die `test_mastodon_service.py` testet die komplette Business Logic mit Mock-Objekten:

- ✅ Erfolgreiches Abrufen neuer Toots
- ✅ Pagination (mehrere Seiten)
- ✅ Filterung von Hashtags/Mentions
- ✅ Link-Extraktion und DB-Speicherung
- ✅ Error Handling

**Keine echten API-Aufrufe oder Firebase-Zugriffe** – schnell & zuverlässig.

```bash
pytest test_mastodon_service.py -v
```

### Integration Tests (TODO)

Nach lokal Setup mit echtem Firebase:
```bash
set RSS_FIREBASE_KEY=<your-firebase-key>
pytest test_mastodon_service.py -v --integration
```

## Architecture

### MastodonService Klasse

```python
class MastodonService:
    def fetch_and_store_links(self):
        """Holt Toots und speichert Links in DB"""
    
    def _extract_and_store_links(self, toots):
        """Extrahiert Links aus Toots"""
```

### main.py Entry-Point

```python
@functions_framework.http
def mastodon_connector_activate(request):
    service = MastodonService()
    service.fetch_and_store_links()
    return "OK", 200
```

## Workflow für Kollegen

Diese Function ist ein Template für:
- `functions/alerts/` (Google Alerts)
- `functions/mail/` (Mail Service)

Gleiche Struktur anwenden:
1. Entry-Point Funktion in `main.py`
2. Service-Klasse in `{service}_service.py`
3. Mock-Tests in `test_{service}_service.py`
4. Individuelles `cloudbuild.yaml`

