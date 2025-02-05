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
    model="gemini-1.5-flash",
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
                You are an  assistant that receives text from html websites and categorizes them into one of the following categories:
                - "Technology and Gadgets"
                - "Politics"
                - "Business and Finance"
                - "Sports"
                - "Education and Learning"
                - "Health and Wellness"
                - "Entertainment and Lifestyle"
                - "Travel and Tourism"
                
                If a website does not fit into one of these categories then return only a single word: "Uncategorized"
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





