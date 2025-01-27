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

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are an  assistant that summarises html websites using text the user provides.",
        ),
        ("human", "{input}"),
    ]
)


def summarise_website(html_text):
    chain = prompt | llm
    response = chain.invoke(
        {
            "input": html_text,
        }
    ).content

    print(response)
    print("---------------------------------------")





