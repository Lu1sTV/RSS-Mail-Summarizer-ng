"""
Dieses Modul steuert die Interaktion mit Gemini.
Es enthält Funktionen, um Webseiten anhand ihrer URLs zusammenzufassen, zu kategorisieren
und relevante Themen sowie Lesezeit zu bestimmen.
Für Google Alerts werden gesonderte Prompts verwendet, die kurze Zusammenfassungen liefern.
"""

#package imports
import re
from collections import defaultdict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os
from langchain_core.rate_limiters import InMemoryRateLimiter
from google.cloud import secretmanager

# Umgebungsvariablen laden
load_dotenv()

LOCAL_GEMINI_KEY_ENV = "GEMINI_API_KEY"

# Google Secret einholen wenn in Google ausgeführt
def access_secret(secret_id: str, project_id: str):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Gemini API Key abrufen (entweder aus Secret Manager oder lokale .env)
def get_gemini_api_key():
    project_id = os.environ["PROJECT_ID"]
    secret_id = "gemini-api-key"

    try:
        # Wenn in Google:
        api_key = access_secret(secret_id, project_id)
        print("Using Gemini API key from Secret Manager")
        return api_key
    except Exception as e:
        # Wenn lokale Ausführung:
        api_key = os.getenv(LOCAL_GEMINI_KEY_ENV)
        if not api_key:
            raise RuntimeError(
                f"Gemini API key not found in Secret Manager or local env. Reason: {e}"
            )
        print("Using Gemini API key from local .env")
        return api_key

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.2,
    check_every_n_seconds=0.1,
    max_bucket_size=1,
)

# Holt GEMINI_API_KEY entweder aus Secret Manager oder .env
GEMINI_API_KEY = get_gemini_api_key()

# Gemini initialisieren
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    rate_limiter=rate_limiter,
)


# Führt den Workflow zur Summary und Kategorisierung einer Liste von URLs aus
def summarise_and_categorize_websites(links_list):
    prompt = build_prompt(links_list)
    return process_llm_response(prompt)


# Erstellt den Prompt für Gemini, inkl. Anweisungen zu Zusammenfassung, Kategorie, Themen, Lesezeit
def build_prompt(links_list):
    combined_input = "\n\n".join(
        f"Input {i+1} (URL: {url})" for i, url in enumerate(links_list)
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                You are an assistant that processes multiple URLs provided by the user.
                For each input, perform the following tasks:

                1. Summarize the content of the Website in about 3 sentences.
                2. Categorize it into one of the following categories:
                   - Technology and Gadgets
                   -Artificial Intelligence
                   -Programming and Development
                   - Politics
                   - Business and Finance
                   - Sports
                   - Education and Learning
                   - Health and Wellness
                   - Entertainment and Lifestyle
                   - Travel and Tourism
                   If a website does not fit into one of these categories, return 'Uncategorized'.
                3. Identify specific topics or entities mentioned in the articles. These should be precise and clearly defined, such as names of technologies, events, organizations, or specific concepts discussed in the text.
                4. Estimate the reading time of the article in minutes based on the length and complexity of the content. Make sure you assess each article individually!
                
                SPECIAL RULE FOR GITHUB URLs:
                - If the URL is a GitHub **repository** page, set Category **exactly** to "GitHub" (override the list above).
                - If content is a **GitHub Blog** Post, treat it like any other website, do not categorize it as "GitHub". Check the content of the page to determine if it is a blog post.
                DO NOT use the "GitHub" category; choose from the normal list above if the post is a blog post. Only repositories should be categorized as "GitHub".
                

                If you are unable to access the contents of the provided website, return "Website content could not be reached!" for that input.

                Format your response as follows:
                Input 1 (URL: <url>):
                Summary: <summary>
                Category: <category> # "GitHub" only for repository URLs as defined above
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                Input 2 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                ...

                Ensure that the topics are specific and relevant to the main content of the article.
                """,
            ),
            ("human", f"{combined_input}"),
        ]
    )

    return prompt


# Verarbeitet die LLM-Ausgabe und extrahiert strukturierte Daten (Summary, Kategorie, Topics, Reading Time)
def process_llm_response(prompt):
    chain = prompt | llm
    response = chain.invoke({}).content

    # Parsed die Antwort und extrahiert die Informationen in ein Dictionary
    results = {}
    topic_counts = defaultdict(list)

    # LLM-Antwort nach Abschnitten splitten und auslesen
    for entry in response.split("\n\n"):
        if "Input" in entry:
            url_match = re.search(r"URL:\s*(https?://[^\s)]+)", entry, re.IGNORECASE)
            summary_match = re.search(r"Summary:\s*(.+)", entry, re.IGNORECASE)
            category_match = re.search(r"Category:\s*(.+)", entry, re.IGNORECASE)
            topics_match = re.search(r"Topics:\s*(.+)", entry, re.IGNORECASE)
            reading_time_match = re.search(
                r"Reading\s*Time:\s*(\d+)\s*minute[s]?", entry, re.IGNORECASE
            )
            # Felder extrahieren
            url = url_match.group(1)
            summary = summary_match.group(1).strip() if summary_match else None
            category = category_match.group(1).strip() if category_match else None
            topics = (
                [topic.strip() for topic in topics_match.group(1).split(",")]
                if topics_match
                else []
            )
            reading_time = (
                int(reading_time_match.group(1)) if reading_time_match else None
            )

            results[url] = {
                "summary": summary,
                "category": category,
                "topics": topics,
                "reading_time": reading_time,
                "subcategory": None,
            }

            # Sammelt Themen für spätere Subkategorisierung
            for topic in topics:
                topic_counts[topic].append(url)

    for topic, urls in topic_counts.items():
        # Wenn ein Thema in mindestens 3 Artikeln vorkommt, wird es als Subcategory verwendet
        if len(urls) >= 3:
            for url in urls:
                if results[url]["subcategory"] is None:
                    results[url]["subcategory"] = topic

    return results



# Erstellt Zusammenfassungen für Google Alerts (kürzerer Prompt, nur Summary + Reading Time)
def summarise_alerts(alerts_dict):
    all_results = {}

    for label, urls in alerts_dict.items():
        combined_input = "\n".join(f"{url}" for url in urls)
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    f"""
            You are an assistant that summarizes multiple URLs for the alert '{label}'.
            For each URL, provide:
            1. Summary (2-3 sentences)
            2. Estimated reading time in minutes

            If you cannot access the website, return:
            "Website content could not be reached!"

            Format your response as follows:
            <URL>:
            Summary: <summary>
            Reading Time: <X> minutes
            """,
                ),
                ("human", combined_input),
            ]
        )
        # Ergebnisse abrufen und mit Sammelergebnis zusammenführen
        result = process_alert_response(prompt, urls)
        all_results.update(result)

    return all_results


# Erstellt den Prompt für die Google Alerts
def build_alert_prompt(alerts_dict):
    """
    alerts_dict: Dictionary {label+url: url} für den Prompt
    """
    combined_input = "\n\n".join(
        f"{label} (URL: {url})" for label, url in alerts_dict.items()
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
        You are an assistant that processes multiple URLs provided by the user.
        For each input, perform the following tasks:

        1. Summarize the content of the website in 2-3 sentences.
        2. Estimate the reading time of the article in minutes based on length and complexity.

        If you are unable to access the website, return "Website content could not be reached!".

        Format your response as follows:
        Alert1 (URL: <url>):
        Summary: <summary>
        Reading Time: <X> minutes

        Alert2 (URL: <url>):
        Summary: <summary>
        Reading Time: <X> minutes

        ...
        """,
            ),
            ("human", combined_input),
        ]
    )
    return prompt

# Verarbeitet die Gemini Antwort für Google Alerts und extrahiert Summary + Reading Time
def process_alert_response(prompt, urls):
    chain = prompt | llm
    response = chain.invoke({}).content

    results = {}
    for entry in response.split("\n\n"):
        # URL aus dem Entry extrahieren
        url_match = re.search(r"(https?://\S+)", entry)
        summary_match = re.search(r"Summary:\s*(.+)", entry, re.IGNORECASE)
        reading_time_match = re.search(
            r"Reading\s*Time:\s*(\d+)\s*minute[s]?", entry, re.IGNORECASE
        )

        if url_match:
            url = url_match.group(1)
            results[url] = {
                "summary": summary_match.group(1).strip() if summary_match else None,
                "reading_time": (
                    int(reading_time_match.group(1)) if reading_time_match else None
                ),
            }

    return results
