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
    requests_per_second=0.2,  # Can only make a request once every 10 seconds!!
    check_every_n_seconds=0.1,  # Wake up every 100 ms to check whether allowed to make a request,
    max_bucket_size=1,  # Controls the maximum burst size.
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
    combined_input = "\n\n".join(
        f"Input {i+1} (URL: {url})"
        for i, url in enumerate(links_list)
    )


    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"""
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

                If you are unable to access the contents of the provided website, return "Website content could not be reached!" for that input.

                Format your response as follows:
                Input 1 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...

                Input 2 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...

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

            if url_match and summary_match and category_match and topics_match:
                url = url_match.group(1)
                summary = summary_match.group(1)
                category = category_match.group(1)
                topics = [topic.strip() for topic in topics_match.group(1).split(',')]

                results[url] = {"summary": summary, "category": category, "topics": topics, "subcategory": None}

                # Count occurrences of each topic
                for topic in topics:
                    topic_counts[topic].append(url)

    # Determine subcategories based on topic occurrences
    for topic, urls in topic_counts.items():
        if len(urls) >= 3:
            for url in urls:
                if results[url]["subcategory"] is None:  # Ensure only one subcategory is assigned
                    results[url]["subcategory"] = topic


    return results









