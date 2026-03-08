## RSS Mail Summarizer

Automatisierte Pipeline, die Inhalte aus RSS-Feeds, Mastodon und Alerts einsammelt, aufbereitet und als kompakten Mail-Report versendet. Das Projekt ist auf Google Cloud Functions ausgelegt und nutzt Cloud Build + Cloud Scheduler fuer Deployment und Ausfuehrung.

## Quick Start

Das komplette Initial-Setup (GCP, Secrets, OAuth, Trigger, Scheduler) ist hier dokumentiert:

- [Initial Setup Guide](./InitialSetup.md)

## Projektstruktur

```text
RSS-Mail-Summarizer-ng/
|- functions/
|  |- alerts/
|  |  |- .gcloudignore
|  |  |- cloudbuild.yaml
|  |  |- config.py
|  |  |- database.py
|  |  |- main.py
|  |  |- ReadMe.md
|  |  `- requirements.txt
|  |- mastodon/
|  |  |- cloudbuild.yaml
|  |  |- config.py
|  |  |- database.py
|  |  |- main.py
|  |  |- mastodon_service.py
|  |  |- README.md
|  |  `- requirements.txt
|  |- podcast/
|  |  |- .gcloudignore
|  |  |- cloudbuild.yaml
|  |  |- config.py
|  |  |- database.py
|  |  |- main.py
|  |  |- README.md
|  |  `- requirements.txt
|  |- rss/
|  |  |- cloudbuild.yaml
|  |  |- config.py
|  |  |- database.py
|  |  |- main.py
|  |  |- README.md
|  |  |- requirements.txt
|  |  `- rss_service.py
|  |- sendmail/
|  |  |- cloudbuild.yaml
|  |  |- config.py
|  |  |- database.py
|  |  |- helpers.py
|  |  |- main.py
|  |  |- markdown_report.md
|  |  |- README.md
|  |  |- requirements.txt
|  |  `- utils.py
|  `- cloudbuild.yaml
|- keys/
|  `- generate_gmail_token.py
|- .gitignore
|- InitialSetup.md
`- README.md
```

## Komponenten im Ueberblick

- `functions/rss`: Holt und verarbeitet RSS-Inhalte.
- `functions/mastodon`: Holt und verarbeitet Mastodon-Inhalte.
- `functions/alerts`: Verarbeitet Alert-Daten als zusaetzliche Quelle.
- `functions/podcast`: Erzeugt/verwaltet Podcast-bezogene Inhalte.
- `functions/sendmail`: Baut den finalen Report und versendet die E-Mail.

## Deployment-Hinweis

Jede Function hat eine eigene `cloudbuild.yaml` und kann ueber dedizierte Cloud-Build-Trigger deployt werden. Details inkl. Scheduler-Jobs stehen im [Initial Setup Guide](./InitialSetup.md).
