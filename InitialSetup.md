# Setup Guide: RSS Mail Summarizer

Führe die folgenden Schritte in der Google Cloud Console (Cloud Shell) aus, sofern nicht explizit als lokaler Schritt markiert.

## 1. Umgebungsvariablen setzen (Cloud Shell)

```bash
export PROJECT_ID=$(gcloud config get-value project)
export LOCATION="europe-west3"
export SERVICE_ACCOUNT="rss-mail-summarizer@${PROJECT_ID}.iam.gserviceaccount.com"
```

## 2. APIs aktivieren

```bash
gcloud services enable \
  cloudscheduler.googleapis.com \
  cloudfunctions.googleapis.com \
  logging.googleapis.com \
  firestore.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  texttospeech.googleapis.com \
  artifactregistry.googleapis.com \
  pubsub.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  gmail.googleapis.com \
  iamcredentials.googleapis.com \
  datastore.googleapis.com \
  servicehealth.googleapis.com \
  storage.googleapis.com
```

## 3. Service Account Berechtigung (Compute Engine)

1. IAM → Dienstkonten → `[...]-compute@developer.gserviceaccount.com` kopieren (das ist die COMPUTE_EMAIL).
2. IAM-Policy-Binding ausführen (mit Platzhalter für die kopierte E-Mail):

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:<COMPUTE_EMAIL>" \
  --role="roles/secretmanager.secretAccessor"
```

3. Bei der Abfrage zur Bedingung (Condition) die Option `[2] None` wählen:
`-> 2`

## 4. Storage und Datenbank anlegen

```bash
gcloud storage buckets create "gs://${PROJECT_ID}-podcasts" \
  --location=$LOCATION \
  --uniform-bucket-level-access

gcloud secrets create gcs-bucket-name --replication-policy="automatic"
echo -n "${PROJECT_ID}-podcasts" | gcloud secrets versions add gcs-bucket-name --data-file=-

gcloud firestore databases create \
  --location=$LOCATION \
  --type=firestore-native
```

## 5. Service Account für die Anwendung erstellen und berechtigen

```bash
gcloud iam service-accounts create rss-mail-summarizer \
  --display-name="RSS Mail Summarizer Service Account"

gcloud iam service-accounts keys create keys/serviceAccountKey.json \
  --iam-account="$SERVICE_ACCOUNT"

gcloud secrets create rss-firebase-key --replication-policy="automatic"
gcloud secrets versions add rss-firebase-key --data-file="keys/serviceAccountKey.json"

gcloud secrets add-iam-policy-binding rss-firebase-key \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gcs-bucket-name \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```

## 6. Rollen an den Service Account vergeben

```bash
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/artifactregistry.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/datastore.user"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/cloudfunctions.developer"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/run.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/run.invoker"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/run.developer"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/cloudbuild.builds.builder"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/iam.serviceAccountTokenCreator"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/logging.logWriter"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/storage.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:$SERVICE_ACCOUNT" --role="roles/secretmanager.secretAccessor"
```

## 7. E-Mail Secrets anlegen

```bash
gcloud secrets create sender-email --replication-policy="automatic"
gcloud secrets create recipient-email --replication-policy="automatic"

echo -n "<SENDER_EMAIL>" | gcloud secrets versions add sender-email --data-file=-
echo -n "<RECIPIENT_EMAIL>" | gcloud secrets versions add recipient-email --data-file=-

gcloud secrets add-iam-policy-binding sender-email \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding recipient-email \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```

## 8. Gemini API Key einrichten

1. aistudio.google.com -> Get API key -> Schlüssel erstellen (default gemini project).
2. Key speichern:

```bash
gcloud secrets create gemini-api-key --replication-policy="automatic"
echo -n "<GEMINI_API_KEY>" | gcloud secrets versions add gemini-api-key --data-file=-

gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```

## 9. Gmail OAuth einrichten (Google Cloud Console Web UI)

1. **OAuth-Zustimmungsbildschirm konfigurieren:**
   - Gehe zu APIs & Dienste → OAuth-Zustimmungsbildschirm → Erste Schritte
   - Anwendungsname: `rss-auth`
   - Nutzersupport-E-Mail: E-Mail vom Admin GCloud Account
   - Zielgruppe: Extern
   - Kontaktdaten: E-Mail vom Admin GCloud Account
   - Zustimmung
2. **OAuth Client ID erstellen:**
   - Gehe zu APIs & Dienste → OAuth-Zustimmungsbildschirm → Anmeldedaten erstellen → OAuth-Client-ID
   - Anwendungstyp: Desktopanwendung
   - Name: RSS Mail Summarizer
   - JSON herunterladen und lokal als `keys/gmail_credentials.json` speichern.
   - APIs & Dienste → OAuth-Zustimmungsbildschirm → Zielgruppe → App veröffentlichen → Bestätigen

---

## 10. LOKALES SETUP (GCloud CLI)

**HINWEIS:** Die folgenden Schritte MÜSSEN zwingend lokal auf deinem Rechner über die GCloud CLI ausgeführt werden, da der OAuth Flow einen lokalen Browser benötigt.

### Login und Variablen lokal setzen

```bash
# Login
gcloud auth login

# Projekt setzen
gcloud config set project <PROJECT_ID>

# Variablen setzen (Linux / Mac)
export PROJECT_ID=$(gcloud config get-value project)
export LOCATION="europe-west3"
export SERVICE_ACCOUNT="rss-mail-summarizer@${PROJECT_ID}.iam.gserviceaccount.com"
```

*Windows Command Prompt verwendet anderen Syntax und wird daher separat behandelt:*
```cmd
gcloud config set project <PROJECT_ID>

set PROJECT_ID=DEINE_PROJECT_ID
set LOCATION=europe-west3
set SERVICE_ACCOUNT=rss-mail-summarizer@%PROJECT_ID%.iam.gserviceaccount.com
```

### Credentials als Secret speichern

```bash
# Linux / Mac
gcloud secrets create gmail-credentials --replication-policy="automatic"
gcloud secrets versions add gmail-credentials --data-file="keys/gmail_credentials.json"

gcloud secrets add-iam-policy-binding gmail-credentials \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```

```cmd
# Windows
gcloud secrets create gmail-credentials --replication-policy="automatic"
gcloud secrets versions add gmail-credentials --data-file="keys/gmail_credentials.json"

gcloud secrets add-iam-policy-binding gmail-credentials \
  --member="serviceAccount:%SERVICE_ACCOUNT%" \
  --role="roles/secretmanager.secretAccessor"
```

### Token generieren

```bash
pip install google-auth-oauthlib
cd keys && python generate_gmail_token.py && cd ..
```

### Token als Secret speichern

```bash
# Linux / Mac
gcloud secrets create gmail-token --replication-policy="automatic"
gcloud secrets versions add gmail-token --data-file="keys/token.json"

gcloud secrets add-iam-policy-binding gmail-token \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"
```
```cmd
# Windows
gcloud secrets create gmail-token --replication-policy="automatic"
gcloud secrets versions add gmail-token --data-file="keys/token.json"

gcloud secrets add-iam-policy-binding gmail-token \
  --member="serviceAccount:%SERVICE_ACCOUNT%" \
  --role="roles/secretmanager.secretAccessor"
```

---

## 10.1 Lokale Secrets aus Secret Manager in `.env` synchronisieren

`keys/token.json` und `keys/gmail_credentials.json` sind lokal bereits vorhanden.
Für lokale Tests fehlen danach typischerweise noch die Runtime-Secrets aus Google Secret Manager.

### Secret -> `.env` Mapping

| Secret Manager Name | `.env` Key |
|---|---|
| `rss-firebase-key` | `RSS_FIREBASE_KEY` |
| `gmail-token` | `GMAIL_TOKEN_JSON` |
| `gemini-api-key` | `GEMINI_API_KEY` |
| `gcs-bucket-name` | `GCS_BUCKET_NAME` |
| `sender-email` | `SENDER_EMAIL` |
| `recipient-email` | `RECIPIENT_EMAIL` |

Zusätzlich lokal setzen:
- `PROJECT_ID`
- `LOG_LEVEL`

### `.env` automatisch erzeugen

Im Repo-Root ausführen:

```bash
# Linux / Mac
gcloud auth login
gcloud config set project <PROJECT_ID>

PROJECT_ID=$(gcloud config get-value project)

RSS_FIREBASE_KEY=$(gcloud secrets versions access latest --secret=rss-firebase-key | jq -c .)
GMAIL_TOKEN_JSON=$(gcloud secrets versions access latest --secret=gmail-token | jq -c .)
GEMINI_API_KEY=$(gcloud secrets versions access latest --secret=gemini-api-key | tr -d '\r\n')
GCS_BUCKET_NAME=$(gcloud secrets versions access latest --secret=gcs-bucket-name | tr -d '\r\n')
SENDER_EMAIL=$(gcloud secrets versions access latest --secret=sender-email | tr -d '\r\n')
RECIPIENT_EMAIL=$(gcloud secrets versions access latest --secret=recipient-email | tr -d '\r\n')

cat > .env <<EOF
PROJECT_ID=$PROJECT_ID
LOG_LEVEL=INFO
RSS_FIREBASE_KEY='$RSS_FIREBASE_KEY'
GMAIL_TOKEN_JSON='$GMAIL_TOKEN_JSON'
GEMINI_API_KEY=$GEMINI_API_KEY
GCS_BUCKET_NAME=$GCS_BUCKET_NAME
SENDER_EMAIL=$SENDER_EMAIL
RECIPIENT_EMAIL=$RECIPIENT_EMAIL
EOF

echo "Created .env"
```

```cmd
# Windows (GCloud Cli)
gcloud auth login
```

```cmd
gcloud config set project <PROJECT_ID>
```

```cmd
powershell -NoProfile -Command "$p=(gcloud config get-value project).Trim();$rf=(gcloud secrets versions access latest --secret=rss-firebase-key | ConvertFrom-Json | ConvertTo-Json -Compress);$gt=(gcloud secrets versions access latest --secret=gmail-token | ConvertFrom-Json | ConvertTo-Json -Compress);$gk=(gcloud secrets versions access latest --secret=gemini-api-key).Trim();$bn=(gcloud secrets versions access latest --secret=gcs-bucket-name).Trim();$se=(gcloud secrets versions access latest --secret=sender-email).Trim();$re=(gcloud secrets versions access latest --secret=recipient-email).Trim();Set-Content -Encoding utf8 .env ('PROJECT_ID=' + $p);Add-Content .env 'LOG_LEVEL=INFO';Add-Content .env ('RSS_FIREBASE_KEY=''' + $rf + '''');Add-Content .env ('GMAIL_TOKEN_JSON=''' + $gt + '''');Add-Content .env ('GEMINI_API_KEY=' + $gk);Add-Content .env ('GCS_BUCKET_NAME=' + $bn);Add-Content .env ('SENDER_EMAIL=' + $se);Add-Content .env ('RECIPIENT_EMAIL=' + $re)"
```

## 11. GitHub Repository und Cloud Build verbinden (Google Cloud Console Web UI)

*(Muss durch den Owner des Repositories durchgeführt werden)*

1. Cloud Build → Trigger → **Repository verbinden**.
2. Anbieter für Quellcodeverwaltung auswählen → **global (Global)** lassen.
3. **GitHub (Cloud Build-GitHub-Anwendung)** auswählen → Fortfahren.
4. Authentifizieren → GitHub-Konto auswählen und Repository auswählen.
   - Falls das Repo nicht sichtbar ist: über *Repositories auf GitHub bearbeiten* freischalten.
5. Haken bei *Mir ist bewusst…* setzen → **Verbinden**.
6. **Trigger erstellen** klicken.

## 12. Cloud Build Trigger einrichten (Google Cloud Console Web UI)

Für jede Function wird ein eigener Trigger angelegt. Im Folgenden wird der erste Trigger (alerts) Schritt für Schritt beschrieben – die übrigen werden analog erstellt.

### Ersten Trigger anlegen (alerts)

1. Cloud Build → Trigger → **Trigger erstellen**.
2. Einstellungen:
   - **Name:** `deploy-alerts`
   - **Ereignis:** Push zu Zweig
   - **Quelle:** Cloud Build Repository
   - **Zweig:** `^main$`
3. *Filter für enthaltene und ignorierte Dateien anzeigen* ausklappen:
   - **Filter für enthaltene Dateien (glob):** `functions/alerts/**`
4. **Cloud Build-Konfigurationsdatei (YAML oder JSON)** anhaken:
   - **Standort:** Repository
   - **Speicherort der Cloud Build-Konfigurationsdatei:** `/functions/alerts/cloudbuild.yaml`
5. **Dienstkonto:** Das in Schritt 5 angelegte Dienstkonto (`rss-mail-summarizer@...`) auswählen.
6. **Erstellen** klicken.

### Weitere Trigger anlegen

Den alerts-Trigger duplizieren und für jede weitere Function anpassen:

| Name | Filter für enthaltene Dateien (glob) | Speicherort Cloud Build-Konfigurationsdatei |
|---|---|---|
| `deploy-mastodon` | `functions/mastodon/**` | `/functions/mastodon/cloudbuild.yaml` |
| `deploy-podcast` | `functions/podcast/**` | `/functions/podcast/cloudbuild.yaml` |
| `deploy-rss` | `functions/rss/**` | `/functions/rss/cloudbuild.yaml` |
| `deploy-sendmail` | `functions/sendmail/**` | `/functions/sendmail/cloudbuild.yaml` |

Alle anderen Einstellungen (Ereignis, Zweig, Dienstkonto) bleiben identisch.


## 13. Scheduling einrichten (Cloud Shell)

```bash
for f in rss-connector mastodon-connector alerts-connector; do
  gcloud scheduler jobs create http "job-$f" \
    --project=$PROJECT_ID \
    --location=$LOCATION \
    --schedule="0 */2 * * *" \
    --uri="https://$LOCATION-$PROJECT_ID.cloudfunctions.net/$f" \
    --http-method=POST \
    --oidc-service-account-email="$SERVICE_ACCOUNT" \
    --time-zone="Europe/Berlin" \
    --quiet
done

for f in sendmail-trigger podcast-trigger; do
  gcloud scheduler jobs create http "job-$f" \
    --project=$PROJECT_ID \
    --location=$LOCATION \
    --schedule="0 8,20 * * *" \
    --uri="https://$LOCATION-$PROJECT_ID.cloudfunctions.net/$f" \
    --http-method=POST \
    --oidc-service-account-email="$SERVICE_ACCOUNT" \
    --time-zone="Europe/Berlin" \
    --quiet
done
```

Kontrolle der Jobs:

```bash
gcloud scheduler jobs list --location=$LOCATION
```

Alle erstellten Cloud Build Trigger und Scheduler Jobs einmal manuell auslösen.