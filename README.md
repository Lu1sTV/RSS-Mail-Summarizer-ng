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

## Veränderungen im Code:
Bei der rss-mail-summarizer/cloudbuild.yaml müssen die PROJECT_ID Werte ersetzt werden. 
(Für eine lokale Ausführung in .env PROJECT_ID=IHRE_PROJECT_ID hinterlegen)

### APIs Aktivieren:
Für die weitere Bearbeitung müssen einige der APIs aktiviert werden. Am einfachsten geht das mit der Google Console (in der Webanwendung oder durch herunterladen einer entsprechenden Software in der eigenen Konsole):

```bash
gcloud services enable cloudbuild.googleapis.com \
                       cloudfunctions.googleapis.com \
                       cloudresourcemanager.googleapis.com \
                       cloudscheduler.googleapis.com \
                       artifactregistry.googleapis.com \
                       secretmanager.googleapis.com \
                       logging.googleapis.com \
                       firestore.googleapis.com \
                       run.googleapis.com
```
Alternativ können diese auch in der Web Benutzeroberfläche freigeschaltet werden.

Ein weiterer Hinweis: sie müssen für einige der Dienste ein Rechnungskonto bei dem Projekt hinterlegt haben.

### Dienstkonto:
Da Google es nicht mag, wenn das Admin-Service-Account verwendet wird, sollte an dieser stellte (unter IAM & Verwaltung --> Dienstkonten) ein Dienstkonto mit einer gut zu merkenden Emailadresse und erstmal ohne weitere Berechtigungen erstellt werden.

### Firestore: 
Zunächst im Google Firestore eine Sammlung/Collection mit dem Namen "website" anlegen. Der Name der Datenbank kann dabei als Default belassen werden. Zum vollständigen Erstellen der Collection dann noch einen Dummy Eintrag einfügen, die Werte und Bezeichnungen sind dabei egal, notwendige "Spalten" werden dann automatisch vom Code angelegt. 

Für den Firestore wird nun ein privater JSON Schlüssel benötigt.

Um aus der lokalen Umgebung oder über gcloud Daten in die Firebase einspeichern zu können braucht es einen privaten Schlüssel (JSON) dafür:
- Unter IAM & Verwaltung --> Dienstkonten zu dem im letzten Abschnitt erstellten Dienstkonto gehen und drauf clicken.
- Beim Reiter "Schlüssel" auf "Schlüssel hinzufügen" clicken und neuen generieren als JavaScript Object Notation
- die JSON unter serviceAccountKey.json im Ordner rss_mail_summarizer speichern (für lokae Ausführung)
- Für das Deployment in der Google Cloud Weboberfläche nun zu Sicherheit --> Secret Manager navigieren und dort:
    - "secret erstellen"
    - name als "rss-firebase-key" vergeben
    - Inhalt der JSON einfügen
    - Erstellen
    - Zugriff gewähren an das Dienskonto (erst generell zum Secret Manager und dann das spezifische Secret):

```bash
 gcloud projects add-iam-policy-binding IHRE_PROJECT_ID \
  --member="serviceAccount:IHRE_DIENSTKONTO_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
```

```bash
gcloud secrets add-iam-policy-binding rss-firebase-key \
  --member="serviceAccount:IHRE_DIENSTKONTO_EMAIL" \
  --role="roles/secretmanager.secretAccessor"
```

Außerdem nutzt die Funktion im Container dann folgendes Service Account, welches auch Zugriff braucht auf das Secret/ die Secrets:

```bash
gcloud secrets add-iam-policy-binding rss-firebase-key \
  --member="serviceAccount:PROEJECT_NO-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Alerts Connector

### Alerts Connector

Der Alerts Connector ermöglicht es, automatisch Links aus Google Alerts E-Mails auszulesen, weiterzuverarbeiten und als erledigt zu markieren.  

Folgende Schritte sind dazu notwendig:

1. **Google Alerts einrichten**  
   - Besuchen: [https://www.google.com/alerts](https://www.google.com/alerts)  
   - Alert zu einem beliebigen Thema erstellen (z. B. *Carlo Masala*).  

2. **Labels und Filter in Gmail anlegen**  
   - Label erstellen:  
     - `alerts-carlo-masala`  
     - `alerts-carlo-masala-processed`  
   - Filter erstellen:  
     - Absender: `googlealerts-noreply@google.com`  
     - Aktion: *Inbox überspringen*  
     - Aktion: *Label anwenden* → `alerts-carlo-masala`  

3. **Ordner `credentials` anlegen**  
   - Auf oberster Ebene neben der `main.py`.  
   - Der Ordner wird genutzt, um Zugangsdaten und Token zu speichern.  

4. **`credentials.json` erstellen**  
   - [Google Cloud Console](https://console.cloud.google.com/) öffnen.  
   - **Gmail API aktivieren**:  
     - Menü → APIs & Dienste → Bibliothek → "Gmail API" suchen → *Aktivieren*.  
   - **OAuth-Zustimmungsbildschirm konfigurieren**:  
     - Menü → APIs & Dienste → OAuth-Zustimmungsbildschirm → *Get Started*  
     - Schritt 1: beliebige Werte eintragen  
     - Schritt 2: *Extern* auswählen  
     - Schritt 3: beliebige E-Mail-Adresse eintragen  
   - **OAuth-Client anlegen**:  
     - Menü → APIs & Dienste → Anmeldedaten → *Anmeldedaten erstellen* → OAuth-Client-ID  
     - Anwendungstyp: *Desktop-App*  
     - Name: `gmail-alerts-client`  
   - JSON herunterladen  
   - Datei im Ordner `credentials` speichern und in **`credentials.json`** umbenennen  

5. **Token generieren**  
   - Einmalig lokal ausführen:  
     ```bash
     python utils/create_gmail_token_locally.py
     ```  
   - Dadurch wird eine **`credentials/token.json`** erstellt.  
   - Diese Datei enthält den Refresh-Token und wird für den automatisierten Zugriff benötigt.  



**Hinweis:**  
Wenn weitere Alerts erstellt werden, muss die **`alert_map`** in der Datei `alerts_connector.py` entsprechend erweitert werden.  
Zusätzlich müssen die passenden Gmail-Labels (`alerts-<NAME>` und `alerts-<NAME>-processed`) angelegt werden.  


---

<!-- ```bash
gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:PROJECT_NO-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:cloud-build@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding SECRET_NAME \
  --member="serviceAccount:PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

  (das zweite Service Account is das welches im Build Trigger für den Build festgelegt wurde, weshalb es auch eine gänzlich andere Email sein kann)
``` -->

### Cloudbuild Trigger:
Mit einem Cloudbuildtrigger kann erreicht werden, dass die Google Funktionen des rss-mail-summarizer in Google automatisch aktualisiert werden, wenn in Github auf dem Main-Branch ein Commit geschieht (Nur Repo Owner können die folgenden Schritte ausführen).

1. In der Cloud Build Umgebung auf Trigger gehen
2. Klicke auf „Trigger erstellen“
3. Wähle:
    - Name: Frei wählbar
    - Region: global
    - Ereignis: Push to branch (z. B. `main`)
    - Repository: Neues Repository verbinden --> GitHub --> Fortfahren --> dann entsprechendes Repository (hier: `RSS-Mail-Summarizer`) auswählen und erlauben.
    - Konfiguration Typ: Cloud Build-Konfigurationsdatei (YAML oder JSON)
    - Standort: Repository (Wert: rss_mail_summarizer/cloudbuild.yaml)
    - Dienstkonto: das neu kreierte wählen
4. „Erstellen“

Nun müssen noch weitere Rechte an das Dienstkonto für den Cloudbuild prozess vergeben werden:

```bash
PROJECT_ID=$(gcloud config get-value project)

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:IHRE_DIENSTKONTO_EMAIL" \
    --role="roles/cloudfunctions.developer"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:IHRE_DIENSTKONTO_EMAIL" \
    --role="roles/iam.serviceAccountUser"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:IHRE_DIENSTKONTO_EMAIL" \
    --role="roles/logging.logWriter"  

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:IHRE_DIENSTKONTO_EMAIL" \
    --role="roles/run.admin"  

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:PROJECT_NO-compute@developer.gserviceaccount.com" \
    --role="roles/cloudbuild.builds.builder"      
```

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


