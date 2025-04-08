import os
import requests
import json

from typing import Optional, List
from groq import Groq
from constants import (system_prompt_default, fox_exclude_tags, npr_exclude_tags, include_tags, 
                       summarize_article_system_prompt, bias_system_prompt, compare_biases_system_prompt)
from models import NewsExtractSchema

def group_sources(
        serp_returned_articles: dict
) -> dict:
    # Group results by news source
    news_by_source = {}
    for article in serp_returned_articles:
        source = article.get("source")
        if source not in news_by_source:
            news_by_source[source] = []
        news_by_source[source].append(article)

    return news_by_source


def assign_article_bias(
        news_bias_ratings: dict,
        articles: dict
) -> dict:
    for article in articles:
        articles[article['position']-1]["political_bias"] = news_bias_ratings[article['source']]

    return articles

## Groq Function

client = Groq(
    api_key=os.environ['GROQ_API_KEY']
)

def call_groq(
        user_prompt: str, 
        system_prompt: Optional[str]=system_prompt_default, 
        model: Optional[str]="llama-3.1-8b-instant",
        ) -> str:
    
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            },
        ],
        model=model,
    )

    return chat_completion.choices[0].message.content

## Firecrawl & News Related Functions
 
# Extract subject of user's question
def subject_extraction(
        question: str
) -> str:
    subject_extraction_system_prompt = "You will be given a question regarding a subject in the news. Extract the subject from the question."
    subject = call_groq(
        user_prompt=question,
        system_prompt=subject_extraction_system_prompt)
    
    return subject


def scrape_article(url: str, exclude_tags: List, include_tags: List):
    # API endpoint
    api_url = "https://api.firecrawl.dev/v1/scrape"
    
    # Request payload using Firecrawl's automatic content extraction
    payload = {
        "url": url,
        "formats": ['json'],
        "onlyMainContent": True,
        "jsonOptions": {
            "schema": NewsExtractSchema.model_json_schema(),
            "systemPrompt": "Extract out the main title of the article and the main contents of the article. Don't pull any advertisement or extraneous information."
        },
        "excludeTags": exclude_tags,
        "includeTags": include_tags,
        "removeBase64Images": True,
    }
    
    # Headers with your API key
    headers = {
        "Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}",
        "Content-Type": "application/json"
    }
    
    # Make the request
    response = requests.post(api_url, json=payload, headers=headers)
    
    # Parse response
    if response.status_code == 200:
        return response.json()
    else:
        return {"error": response.text}
    

def scrape_article_corpus(
        articles: List[dict]
) -> dict:
        for article in articles:

                if article['source'] == 'Fox News':
                        articles[article['position']-1]['scraped_article'] = scrape_article(
                        article['link'], 
                        exclude_tags=fox_exclude_tags,
                        include_tags=include_tags
                        )
                else:
                        articles[article['position']-1]['scraped_article'] = scrape_article(
                        article['link'],
                        exclude_tags=npr_exclude_tags,
                        include_tags=include_tags
                        )

        return articles


# This one's output isn't being used as part of the bias work. More so useful for presenting main points to the user at the end.
def news_article_summarizer(
        articles: List[dict],
        summarize_article_system_prompt: str = summarize_article_system_prompt
) -> dict:
    for article in articles:

        user_prompt = f"Article: {articles[article['position']-1]['scraped_article']}"
        chat_completion = client.chat.completions.create(
                messages=[
                {
                        "role": "system",
                        "content": summarize_article_system_prompt
                },
                {
                        "role": "user",
                        "content": user_prompt
                },
                ],
                model="llama-3.1-8b-instant",
        )

        articles[article['position']-1]['news_analyst_response'] = chat_completion.choices[0].message.content


# Determine bias of one article
def single_article_bias_analysis(
    user_query_subject: str,
    media_publisher: str,
    media_bias_leaning: str,
    article_title: str,
    article_content: str
    ) -> dict:

    bias_user_prompt = f"""
    USER QUERY SUBJECT: {user_query_subject}
    NEWS PUBLISHER: {media_publisher}
    MEDIA BIAS LEANING: {media_bias_leaning}

    ======

    ARTICLE TITLE: {article_title}
    ARTICLE CONTENT: {article_content}
    """
    tries = 0
    while tries <= 5:
        tries += 1
        groq_bias_analysis = call_groq(
            system_prompt=bias_system_prompt,
            user_prompt=bias_user_prompt
        )

        print(f"groq bias analysis: {groq_bias_analysis}")
        
        try:
            groq_output_dict = json.loads(groq_bias_analysis.replace('\n', ''))
            return groq_output_dict
        except json.JSONDecodeError as e:
            print(f"{json.JSONDecodeError}. Retrying...")


# determine bias of a list of articles
def bias_analysis_all_articles(
        user_query_subject: str,
        articles: List[dict]
) -> dict:
    for article in articles:
        if article['scraped_article'].get('data'):
                article['bias_analysis'] = single_article_bias_analysis(
                user_query_subject=user_query_subject,
                media_publisher=article['source'],
                media_bias_leaning=article['political_bias'],
                article_title=article['scraped_article']['data']['json']['main_article_title'],
                article_content=article['scraped_article']['data']['json']['main_article_content']
                )
        else:
                continue
        

# Compare the bias of different articles grouped by media source
def bias_comparison(
        user_query_subject: str,
        news_by_source: dict
    ) -> str:

    compare_biases_user_prompt = f"""
    USER QUERY SUBJECT: {user_query_subject}

    ======\n
    """
    for agency in news_by_source:
        compare_biases_user_prompt += f"\n# {agency}\n"
        for article in news_by_source[agency]:
            if article.get('bias_analysis') is not None:
                compare_biases_user_prompt += f"{article['bias_analysis']}\n"

    bias_comparison_output = call_groq(
        system_prompt=compare_biases_system_prompt,
        user_prompt=compare_biases_user_prompt
    )

    return bias_comparison_output
