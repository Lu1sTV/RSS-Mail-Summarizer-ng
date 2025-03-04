import os

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore
import numpy as np
from sentence_transformers import SentenceTransformer
import datetime
import json
import google.generativeai as genai  # Zum Ansprechen von gemini-2.0-flash
import re

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- Firebase initialisieren ---
cred = credentials.Certificate("rag-account-service-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- LLM konfigurieren (gemini-2.0-flash) ---
genai.configure(api_key=GEMINI_API_KEY)
llm = genai.GenerativeModel(model_name='gemini-2.0-flash')

# --- Embedding-Modell laden ---
model = SentenceTransformer('all-MiniLM-L6-v2')


# --- Artikel aus der Firestore-Collection "website" laden ---
def load_articles():
    collection_ref = db.collection("website")
    docs = collection_ref.stream()
    articles = []
    for doc in docs:
        data = doc.to_dict()
        # Annahme: Jeder Artikel hat 'summary' und 'timestamp'
        if "summary" in data and "timestamp" in data:
            # Konvertiere den Timestamp, falls er als String vorliegt
            if isinstance(data["timestamp"], str):
                try:
                    data["timestamp"] = datetime.datetime.strptime(data["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    data["timestamp"] = datetime.datetime.fromisoformat(data["timestamp"])
            # Berechne das Embedding, falls noch nicht vorhanden
            if "vector_embedding" not in data:
                data["vector_embedding"] = model.encode(data["summary"]).tolist()
            articles.append(data)
    return articles


# --- Embedding für die Anfrage berechnen ---
def compute_query_embedding(query):
    return model.encode(query)


# --- Kosinus-Ähnlichkeit zwischen zwei Vektoren berechnen ---
def cosine_similarity(vec1, vec2):
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def extract_json_from_text(text):
    """
    Versucht, ein JSON-Objekt aus dem gegebenen Text zu extrahieren.
    """
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if match:
        json_text = match.group(0)
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            print("Fehler beim JSON-Parsen:", json_text)
            return None
    return None


# --- LLM-basierte Extraktion des Zeitfilters aus der Anfrage ---
def extract_time_filter_llm(query, llm):
    """
    Nutzt das LLM, um aus der Anfrage einen Zeitbereich zu extrahieren.
    Das aktuelle Datum wird explizit mitgegeben, damit das LLM relative Zeitangaben korrekt umwandelt.
    """
    today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Aktuelles Datum & Uhrzeit
    prompt = (
        f"Das heutige Datum und die aktuelle Uhrzeit ist {today}.\n"
        "Analysiere die folgende Anfrage und bestimme einen relevanten Zeitbereich, falls vorhanden.\n"
        "Falls die Anfrage einen Zeitbezug enthält, gib nur und ausschließlich das folgende JSON-Format zurück, ohne zusätzliche Wörter:\n"
        '{ "start": "YYYY-MM-DD HH:MM:SS", "end": "YYYY-MM-DD HH:MM:SS" }\n\n'
        "Falls kein Zeitbezug in der Anfrage vorhanden ist, antworte mit null.\n\n"
        "Hier einige Beispiele zur Orientierung:\n"
        'Anfrage: "Welche Artikel wurden gestern über Tesla geschrieben?"\n'
        'Antwort: { "start": "2025-03-02 00:00:00", "end": "2025-03-02 23:59:59" }\n\n'
        'Anfrage: "Welche Artikel gibt es zur Bundestagswahl 2021?"\n'
        'Antwort: { "start": "2021-09-01 00:00:00", "end": "2021-09-30 23:59:59" }\n\n'
        'Anfrage: "Welche Artikel handeln über Künstliche Intelligenz?"\n'
        'Antwort: null\n\n'
        f"Anfrage: \"{query}\""
    )

    response = llm.generate_content(prompt)


    try:
        result = response.text.strip()

        print("Raw LLM Output:", result)  # <-- Debugging-Zeile hinzufügen
        if not result:
            print("Warnung: LLM hat eine leere Antwort zurückgegeben.")
            return None

        time_filter = extract_json_from_text(result)

        if time_filter is None:
            return None

        # Stelle sicher, dass die Zeitangaben gültig sind
        start = datetime.datetime.strptime(time_filter["start"], "%Y-%m-%d %H:%M:%S")
        end = datetime.datetime.strptime(time_filter["end"], "%Y-%m-%d %H:%M:%S")

        # Prüfe, ob der Startzeitpunkt vor dem Endzeitpunkt liegt
        if start > end:
            raise ValueError("Startdatum liegt nach dem Enddatum")

        return start, end

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        print("Fehler beim Parsen der LLM-Antwort:", e)
        return None


# --- Filtert Artikel basierend auf einem Zeitbereich ---
def filter_articles_by_time(articles, time_filter):
    if not time_filter:
        return articles
    start_time, end_time = time_filter
    filtered = []
    for article in articles:
        if "timestamp" in article:
            ts = article["timestamp"]
            if start_time <= ts <= end_time:
                filtered.append(article)
    return filtered


# --- Vektorsuche: Relevante Artikel anhand der Anfrage ermitteln ---
def vector_search(query, articles, top_k=5):
    # Versuche, einen Zeitfilter über das LLM zu extrahieren
    time_filter = extract_time_filter_llm(query, llm)
    if time_filter:
        print(f"Folgender Zeitfilter wurde gefunden: {time_filter}")
        articles = filter_articles_by_time(articles, time_filter)

    # Berechne das Query-Embedding
    query_embedding = compute_query_embedding(query)
    scored_articles = []
    for article in articles:
        article_embedding = article["vector_embedding"]
        score = cosine_similarity(query_embedding, article_embedding)
        scored_articles.append((score, article))
    scored_articles.sort(key=lambda x: x[0], reverse=True)
    return [article for score, article in scored_articles[:top_k]]



########################################################

# Alle Artikel aus der Collection "website" laden
articles = load_articles()

# Beispielhafte Anfrage mit Zeitfilter
query = "Welche Artikel handelten letzte Woche von Skype"
print(query)
relevant_articles = vector_search(query, articles, top_k=3)
print("Gefundene Artikel:")
for article in relevant_articles:
    print(f"- {article.get('url', 'Keine URL vorhanden')}")
