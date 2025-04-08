import os
import requests

from burr.core import action, State, ApplicationBuilder
from burr.tracking import LocalTrackingClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from serpapi.google_search import GoogleSearch
from typing import Optional, List

from constants import (news_rating_bias, fox_exclude_tags, npr_exclude_tags, include_tags, summarize_article_system_prompt)
from utils import assign_article_bias, group_sources, call_groq, client
from models import NewsExtractSchema

@action(reads=[], writes=['original_user_input'])
def user_entry_point(
        state: State,
        query: str
) -> State:
    return state.update(original_user_input=query)

#####################
## Serp Functions ##
#####################

@action(reads=["original_user_input"], writes=['serp_params'])
def set_serp_params(
        state: State,
        # time_range: Optional[str],
        country: Optional[str] = "us",
        site_list: Optional[List[str]] = ["foxnews.com", "npr.org"]
) -> State:
    # Set up your search parameters
    params = {
        "api_key": os.environ['SERP_API_KEY'],
        "engine": "google",
        "q": state['original_user_input'],  # Main query terms
        "tbm": "nws",              # This specifies a news search
        "num": 10,                 # Number of results (up to 100)
        "gl": country,                # Country (us, uk, ca, etc.)
        "hl": "en"                 # Language
    }
    # if time_range:
    #     params['tbs'] = time_range # Time range (d=day, w=week, m=month, y=year)
    
    sites_query = " OR ".join([f"site:{site}" for site in site_list])
    params["q"] = f"{params['q']} ({sites_query})"

    return state.update(serp_params=params)

@action(reads=["serp_params"], writes=["news_results"])
def serp_google_search(
        state: State
) -> State:

    # Execute the search
    search = GoogleSearch(state["serp_params"])
    results = search.get_dict()

    # Process the results
    news_results = results.get("news_results", [])
    news_results = assign_article_bias(
         news_bias_ratings=news_rating_bias,
         articles=news_results
    )
    
    return state.update(news_results=news_results)

@action(reads=["news_results"], writes=["media_grouped_news_results"])
def group_serp_results_by_source(
        state: State,
) -> State:
    # Group results by news source
    news_by_source = {}
    for article in state["news_results"]:
        source = article.get("source")
        if source not in news_by_source:
            news_by_source[source] = []
        news_by_source[source].append(article)

    return state.update(media_grouped_news_results=news_by_source)

################################
## Firecrawl & News Functions ##
################################

@action(reads=["original_user_input"], writes=["query_subject"])
# Extract subject of user's question
def subject_extraction(
        state: State
) -> State:
    subject_extraction_system_prompt = "You will be given a question regarding a subject in the news. Extract the subject from the question."
    subject = call_groq(
        user_prompt=state['original_user_input'],
        system_prompt=subject_extraction_system_prompt)
    
    return state.update(query_subject=subject)

# Helper function for scraping all articles
def scrape_article(
        url: str, 
        exclude_tags: List, 
        include_tags: List
     ) -> dict:
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
    
@action(reads=["news_results"], writes=["news_results"])
def scrape_article_corpus(
        state: State
) -> State:
        articles = state["news_results"]

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

        return state.update(news_results=articles)


# This one's output isn't being used as part of the bias work. More so useful for presenting main points to the user at the end.
@action(reads=["news_results"], writes=["news_results"])
def news_articles_summarizer(
        state: State,
        summarize_article_system_prompt: str = summarize_article_system_prompt
) -> State:
    articles = state["news_results"]

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

    return state.update(news_results=articles)


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
@action(reads=['news_results', 'query_subject'], writes=['news_results'])
def bias_analysis_all_articles(
        state: State
) -> State:
    articles = state['news_results']

    for article in articles:
        if article['scraped_article'].get('data'):

            articles[article['position']-1]['bias_analysis'] = single_article_bias_analysis(
            user_query_subject=state['query_subject'],
            media_publisher=article['source'],
            media_bias_leaning=article['political_bias'],
            article_title=article['scraped_article']['data']['json']['main_article_title'],
            article_content=article['scraped_article']['data']['json']['main_article_content']
            )
        else:
            continue
        
    return state.update(news_results=articles)


# Compare the bias of different articles grouped by media source
@action(reads=['query_subject', 'media_grouped_news_results'], writes=["bias_comparison_output"])
def bias_comparison(
        state: State
    ) -> str:

    compare_biases_user_prompt = f"""
    USER QUERY SUBJECT: {state['query_subject']}

    ======\n
    """
    for agency in state['media_grouped_news_results']:
        compare_biases_user_prompt += f"\n# {agency}\n"
        for article in state['media_grouped_news_results'][agency]:
            if article.get('bias_analysis') is not None:
                compare_biases_user_prompt += f"{article['bias_analysis']}\n"

    bias_comparison_output = call_groq(
        system_prompt=compare_biases_system_prompt,
        user_prompt=compare_biases_user_prompt
    )

    return state.update(bias_comparison_output=bias_comparison_output)
