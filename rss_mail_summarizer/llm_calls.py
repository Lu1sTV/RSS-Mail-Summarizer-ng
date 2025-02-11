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




def summarise_website(html_text):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                You are an  assistant that summarises html websites in about 3 sentences using text the user provides.
                If the user does not provide website text, return only the following sentence:
                
                "No text provided!"
                """
            ),
            ("human", "{input}"),
        ]
    )

    chain = prompt | llm
    response = chain.invoke(
        {
            "input": html_text,
        }
    ).content

    return response


def categorize_website(html_text):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                You are an assistant that categorizes text extracted from HTML websites into one of the following categories:

                - Technology and Gadgets
                - Politics
                - Business and Finance
                - Sports
                - Education and Learning
                - Health and Wellness
                - Entertainment and Lifestyle
                - Travel and Tourism
                
                If a website does not fit into one of these categories, return only a single word: 'Uncategorized'.                
                """,
            ),
            ("human", "{input}"),
        ]
    )

    chain = prompt | llm
    response = chain.invoke(
        {
            "input": html_text,
        }
    ).content

    return response


def get_subcategories(category_summaries):
    """
    This function processes a list of summaries for a single category and identifies subcategories
    within the summaries that share a common theme. Each subcategory must have at least four summaries
    with a similar topic. The function returns a dictionary where each key is a subcategory and each value
    is a list of URLs associated with that subcategory.

    Input:
    - category_summaries (list): A list of dictionaries, each containing:
        - "summary" (str): A string representing the summary of an article.
        - "url" (str): A string representing the URL associated with the summary.

    Example Input:
    [
        {"summary": "AI is improving customer service through chatbots.", "url": "http://example.com/tech1"},
        {"summary": "AI algorithms are optimizing supply chain management.", "url": "http://example.com/tech2"},
        {"summary": "AI in healthcare is revolutionizing diagnostic tools.", "url": "http://example.com/tech3"},
        {"summary": "AI-driven personalized learning is the future of education.", "url": "http://example.com/tech4"}
    ]

    Output:
    - Returns a dictionary where each key is a subcategory name, and each value is a list of URLs associated
      with that subcategory. If no suitable subcategories are identified, the function returns None.

    Example Output:
    {
        "AI Applications": [
            "http://example.com/tech1",
            "http://example.com/tech2",
            "http://example.com/tech3",
            "http://example.com/tech4"
        ]
    }

    The function uses a language model to analyze the summaries and determine appropriate subcategories.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """
                You are an expert in categorizing content. Given a list of summaries, your task is to identify subgroups within the summaries that share a common theme. Each subgroup should have at least four summaries with a similar topic. For each identified subgroup, generate a suitable subcategory that represents the common theme and return all subcategories formatted as a python dictionary with the subcategory as the key and the URLs as the values.

                If there are no subgroups with at least four summaries sharing a common theme, return only a single word: none. Only return subcategories for subgroups that clearly share a similar topic.

                Example 1:
                Summaries:
                - "AI is improving customer service through chatbots."
                - "AI algorithms are optimizing supply chain management."
                - "AI in healthcare is revolutionizing diagnostic tools."
                - "AI-driven personalized learning is the future of education."
                - "The impact of climate change on polar regions is severe."
                - "New fashion trends are focusing on sustainability."

                Subcategories:
                {{"AI Applications": ["url1", "url2", "url3", "url4"]}}

                Example 2:
                Summaries:
                - "The latest smartphone releases have advanced cameras."
                - "Climate change is affecting polar regions significantly."
                - "Sustainable fashion is trending this season."
                - "New advancements in mobile photography are exciting."
                - "Scientists study climate change impacts on ecosystems."
                - "Eco-friendly materials are popular in fashion."

                Subcategories:
                - "none"
                """
            ),
            ("human", "Summaries: {input}"),
        ]
    )

    # Prepare the input for the prompt
    input_summaries = [f"{item['summary']} (URL: {item['url']})" for item in category_summaries]

    chain = prompt | llm
    response = chain.invoke(
        {
            "input": "\n- ".join(input_summaries),  # Format the summaries as a list
        }
    ).content

    # Clean and check the response
    response = response.strip()
    if response.lower() == "none":
        print("No relevant subcategories identified")
        return None
    else:
        try:
            # Attempt to parse the response as a JSON string
            return json.loads(response)
        except json.JSONDecodeError:
            try:
                # Attempt to parse the response as a string representation of a dictionary
                return ast.literal_eval(response)
            except (SyntaxError, ValueError):
                # Handle the case where the response is not a valid dictionary string
                return None






