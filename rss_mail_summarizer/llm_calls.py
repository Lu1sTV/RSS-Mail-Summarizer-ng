from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import os

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
)




def summarise_website(html_text):
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an  assistant that summarises html websites in about 3 sentences using text the user provides.",
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

    print(response)
    print("---------------------------------------")


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
                
                If a website does not fit into one of these categories then categorize it as "Uncategorized"
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

    print("Category: " + response)





