from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os
from langchain_core.rate_limiters import InMemoryRateLimiter

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
                
                Additionally, for categorized content, provide a subcategory from the following predefined subcategories:
                
                - Technology and Gadgets → (Artificial Intelligence, Smartphones & Wearables, Software & Apps)
                - Politics → (Domestic Policy, International Relations, Elections & Government)
                - Business and Finance → (Stock Market & Investments, Startups & Entrepreneurship, Corporate News)
                - Sports → (Football, Individual Sports, Extreme & Outdoor Sports)
                - Education and Learning → (Online Learning & EdTech, Academic Research, Career & Skill Development)
                - Health and Wellness → (Nutrition & Diet, Mental Health, Fitness & Exercise)
                - Entertainment and Lifestyle → (Movies & TV Shows, Fashion & Beauty, Music & Performing Arts)
                - Travel and Tourism → (Destinations & Attractions, Travel Tips & Hacks, Hotels & Accommodation)
                
                
                Output Format:
                If categorized, return the category and an appropriate subcategory as follows: 'Category: [Main Category], Subcategory: [Subcategory]'
                If the content is unclear or does not fit, return only: 'Uncategorized'
                Ensure that subcategories are chosen based on relevance to the content. If none of the predefined subcategories fit precisely, choose the closest match.
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

    # Parsing the response
    if response == "Uncategorized":
        return "Uncategorized", None  # Category is 'Uncategorized', no subcategory

    # Split the response into category and subcategory
    try:
        category_part, subcategory_part = response.split(", ")
        category = category_part.split(": ")[1]
        subcategory = subcategory_part.split(": ")[1]
    except (IndexError, ValueError):
        # In case of unexpected response format
        return "Error", "Invalid response format provided by llm"

    return category, subcategory





