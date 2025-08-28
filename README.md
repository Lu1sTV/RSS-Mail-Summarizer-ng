## Aktueller Stand:
Artikel eines RSS Feeds werden zusammengefasst und (unter)kategorisiert. Die Ergebnisse werden zweimal täglich per Mail versandt und in einer Firestore Datenbank gespeichert.

Außerdem können Fragen wie beispielsweise "Welche Artikel zu Trump wurden letzte Woche veröffentlicht?" durch ein RAG System beantwortet werden, wobei diese Funktionalität noch ausgebaut werden muss.

## Hinweise zum Verwenden:
Um das Programm zu verwenden, müssen folgende Umgebungsvariablen in einer .env file hinterlegt werden:

- **GEMINI_API_KEY**: (kann hier erstellt werden: https://ai.google.dev/gemini-api/docs/api-key?hl=de)

- **SENDER_PASSWORD**: (Hiermit ist das App Passwort für den Gmail Account gemeint)

Außerdem müssen folgende Dateien angelegt werden:

- "rag/rag-account-service.key.json"

- "rss_mail_summarizer/serviceAccountKey.json"

## Deployen:
Zum eigenen deployen müssen die folgenden Schritte unternommen werden.
### Firestore: 
Zur Speicherung der Daten wird eine Firestore Sammlung/Collection mit dem Namen "website" benötigt in die ein "dummy" Eintrag eingefügt werden kann und nach dem Hinzufügen richtiger Datensätze entfernt werden kann.
Um aus der lokalen Umgebung oder über gcloud Daten in die Firebase einspeichern zu können braucht es einen privaten Schlüssel (JSON) dafür:
- Unter IAM & Verwaltung --> Dienstkonten in der cloud Console ein Dienstkonto erstellen.
- Neuen Privaten Schlüssel generieren
- die JSON unter serviceAccountKey.json im Ordner rss_mail_summarizer speichern (für lokal)
- (In der Cloud deployed) In gcloud console zu Security --> Secret Manager navigieren:
    - "secret erstellen"
    - name vergeben
    - Inhalt der JSON einfügen
    - Erstellen
    - Zugriff gewähren unter "Berechtigungen" an: service-PROJEKTNUMMER@gcf-admin-robot.iam.gserviceaccount.com mit der Rolle: Secret Manager Secret Accessor
### APIs Aktivieren:
Für die weitere Bearbeitung müssen einige der APIs aktiviert werden. Am einfachsten geht das mit gcloud SDK (sonst in der Webanwendung google cloud console):
```bash
gcloud services enable cloudbuild.googleapis.com \
                       cloudfunctions.googleapis.com \
                       cloudresourcemanager.googleapis.com \
                       cloudscheduler.googleapis.com \
                       artifactregistry.googleapis.com 
```

### Cloud Build Rechte:
```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_ID@cloudbuild.gserviceaccount.com" \
    --role="roles/cloudfunctions.developer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_ID@cloudbuild.gserviceaccount.com" \
    --role="roles/iam.serviceAccountUser"
```

### Umgang mit Secrets
Für jedes der Google Secrets (momentan 3: rss-firestore-key, credentials-token-json, credentials-credentials-json) müssen die folgenden Berechtigungen vergeben werden, wobei PROJECT_ID und NR sowie der SECRET_NAME entsprechend eingefügt werden müssen: 

```bash
gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:PROJECT_NO-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:cloud-build@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```
(das zweite Service Account is das welches im Build Trigger für den Build festgelegt wurde, weshalb es auch eine gänzlich andere Email sein kann)

Außerdem müssen für lokale Ausführungen in einer .env und für den Build Trigger in der cloudbuild.yaml PROJECT_ID hinterlegt werden bzw. bei der cloudbuild.yaml mit der eigenen PROJECT_ID ersetzt werden.

### GitHub-Repository mit Cloud Build verbinden
Hierdurch wird der Code automatisch in der google Cloud Funktion aktualisiert, wenn die Main des GitHub Repos gepushed wird (Nur Repo Owner können die folgenden Schritte ausführen)

1. In der Cloud Build Umgebung auf Trigger gehen
2. Klicke auf „Trigger erstellen“
3. Wähle:
    - Quelle: GitHub (verknüpfen, falls noch nicht geschehen)
    - Repository: `RSS-Mail-Summarizer`
    - Ereignis: Push to branch (z. B. `main`)
    - Verzeichnis: `rss_mail_summarizer/`
    - Build Config File: `cloudbuild.yaml`
4. „Erstellen“

### Scheduler:
Mit einem Scheduler wird die Cloud Funktion zu bestimmten Zeiten ausgeführt je nach eingestelltem Cron-Timejob

Zuerst wird die URL der Cloud Funktion benötigt:
```bash
gcloud functions describe rss_mail_summarizer_main --region=europe-west3 \
    --format="value(serviceConfig.uri)"
```
Dann beim Cloud Scheduler in der Webanwendung auf "Job Erstellen"
Felder folgenderweise befüllen:
    - **Name**: SELBST-WÄHLEN
    - **Frequenz**: z. B. `0 * * * *` (stündlich)
    - **Zieltyp**: `HTTP`
    - **URL**: Die aus dem vorherigen Befehl kopierte URL
    - **HTTP-Methode**: `GET`


