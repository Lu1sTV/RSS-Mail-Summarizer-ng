import re
from collections import defaultdict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os
from langchain_core.rate_limiters import InMemoryRateLimiter
import json
import ast

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.2,
    check_every_n_seconds=0.1,
    max_bucket_size=1,
)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    rate_limiter=rate_limiter
)

def summarise_and_categorize_websites(links_list):
    prompt = build_prompt(links_list, mode="default")
    return process_llm_response(prompt)

def summarise_websites(links_list):
    prompt = build_prompt(links_list, mode="github")
    return process_llm_response(prompt)


def build_prompt(links_list, mode="default"):
    combined_input = "\n\n".join(
        f"Input {i+1} (URL: {url})"
        for i, url in enumerate(links_list)
    )

    if mode == "github":
        prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                You are an assistant that processes multiple GitHub URLs provided by the user.
                For each input, perform the following tasks:

                1. Summarize the content of the Website in about 3 sentences.
                2. Identify specific topics or entities mentioned in the articles. These should be precise and clearly defined, such as names of technologies, events, organizations, or specific concepts discussed in the text.
                3. Estimate the reading time of the article in minutes based on the length and complexity of the content.

                If you are unable to access the contents of the provided website, return "Website content could not be reached!" for that input.

                Format your response as follows:
                Input 1 (URL: <url>):
                Summary: <summary>
                Category: GitHub
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                Input 2 (URL: <url>):
                Summary: <summary>
                Category: GitHub
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                ...

                Ensure that the topics are specific and relevant to the main content of the article. The Category should always be "GitHub".
                """
            ),
            ("human", f"{combined_input}"),
        ]
    ) 
    else:
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
                   - Politics
                   - Business and Finance
                   - Sports
                   - Education and Learning
                   - Health and Wellness
                   - Entertainment and Lifestyle
                   - Travel and Tourism
                   If a website does not fit into one of these categories, return 'Uncategorized'.
                3. Identify specific topics or entities mentioned in the articles. These should be precise and clearly defined, such as names of technologies, events, organizations, or specific concepts discussed in the text.
                4. Estimate the reading time of the article in minutes based on the length and complexity of the content.

                If you are unable to access the contents of the provided website, return "Website content could not be reached!" for that input.

                Format your response as follows:
                Input 1 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                Input 2 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                ...

                Ensure that the topics are specific and relevant to the main content of the article.
                """
            ),
            ("human", f"{combined_input}"),
        
        ]
    ) 
    return prompt
    

def process_llm_response(prompt):
    chain = prompt | llm
    response = chain.invoke({}).content

    # Parse the response and store it in a dictionary
    results = {}
    topic_counts = defaultdict(list)

    for entry in response.split('\n\n'):
        if "Input" in entry:
            url_match = re.search(r"URL: (.+?)\)", entry)
            summary_match = re.search(r"Summary: (.+)", entry)
            category_match = re.search(r"Category: (.+)", entry)
            topics_match = re.search(r"Topics: (.+)", entry)
            reading_time_match = re.search(r"Reading Time: (\d+) minutes", entry)

            if url_match and summary_match and category_match and topics_match:
                url = url_match.group(1)
                summary = summary_match.group(1)
                category = category_match.group(1)
                topics = [topic.strip() for topic in topics_match.group(1).split(',')]
                reading_time = int(reading_time_match.group(1)) if reading_time_match else None

                results[url] = {
                    "summary": summary,
                    "category": category,
                    "topics": topics,
                    "reading_time": reading_time,
                    "subcategory": None
                }

                for topic in topics:
                    topic_counts[topic].append(url)

    for topic, urls in topic_counts.items():
        if len(urls) >= 3:
            for url in urls:
                if results[url]["subcategory"] is None:
                    results[url]["subcategory"] = topic

    return results


#def summarise_and_categorize_websites(links_list):
    combined_input = "\n\n".join(
        f"Input {i+1} (URL: {url})"
        for i, url in enumerate(links_list)
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
                   - Politics
                   - Business and Finance
                   - Sports
                   - Education and Learning
                   - Health and Wellness
                   - Entertainment and Lifestyle
                   - Travel and Tourism
                   If a website does not fit into one of these categories, return 'Uncategorized'.
                3. Identify specific topics or entities mentioned in the articles. These should be precise and clearly defined, such as names of technologies, events, organizations, or specific concepts discussed in the text.
                4. Estimate the reading time of the article in minutes based on the length and complexity of the content.

                If you are unable to access the contents of the provided website, return "Website content could not be reached!" for that input.

                Format your response as follows:
                Input 1 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                Input 2 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                ...

                Ensure that the topics are specific and relevant to the main content of the article.
                """
            ),
            ("human", f"{combined_input}"),
        ]
    )

    chain = prompt | llm
    response = chain.invoke({"input": combined_input}).content

    # Parse the response and store it in a dictionary
    results = {}
    topic_counts = defaultdict(list)

    for entry in response.split('\n\n'):
        if "Input" in entry:
            url_match = re.search(r"URL: (.+?)\)", entry)
            summary_match = re.search(r"Summary: (.+)", entry)
            category_match = re.search(r"Category: (.+)", entry)
            topics_match = re.search(r"Topics: (.+)", entry)
            reading_time_match = re.search(r"Reading Time: (\d+) minutes", entry)

            if url_match and summary_match and category_match and topics_match:
                url = url_match.group(1)
                summary = summary_match.group(1)
                category = category_match.group(1)
                topics = [topic.strip() for topic in topics_match.group(1).split(',')]
                reading_time = int(reading_time_match.group(1)) if reading_time_match else None

                results[url] = {
                    "summary": summary,
                    "category": category,
                    "topics": topics,
                    "reading_time": reading_time,
                    "subcategory": None
                }

                for topic in topics:
                    topic_counts[topic].append(url)

    for topic, urls in topic_counts.items():
        if len(urls) >= 3:
            for url in urls:
                if results[url]["subcategory"] is None:
                    results[url]["subcategory"] = topic

    return results


