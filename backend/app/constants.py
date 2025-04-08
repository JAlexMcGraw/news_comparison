system_prompt_default = """You are a helpful news analyst."""

fox_exclude_tags = ["video", "div.sidebar", "div.contain", "comment", "related", "recommendation",
            "advertisement", "social", "share", "newsletter", "subscription",
            "author-bio", "read-more", "popular", "trending", "strong", "div.pdf-container", "div.sidebar", "div.contain",
            "div.article-meta", "footer", "div.image-ct", "div.ad-container"]

npr_exclude_tags = ["div.tags", "div.callout-end-of-story-piano-wrap", "aside", "footer", "div.bucketblock",
            "picture", "div.primaryaudio", "div.credit-caption"]

include_tags = ["h1", "p"]

summarize_article_system_prompt = """You are a news analyst. Your job is to analyze an article and summarize what what the article is about, and respond in a JSON format.
The JSON schema should include the following

{
    "summary": "str",
    "main_points": "List[str]"
}
"""

bias_system_prompt = """You are a bias identifier for news articles. You will be given the subject of the user query, the news publisher, 
pre-determined media bias leaning, article title, and article content.
Your job is to determine the sentiment across all the articles describe the bias shown.
Return ONLY the JSON schema, which should include the following

{
    "sentiment_analysis": Field("float", description="Bias range between -1 and 1, where -1 is very negative, 0 is unbiased/neutral, and 1 is very positive"),
    "bias_shown": Field("str", description="Description of the bias shown in the article"),
}
"""

compare_biases_system_prompt = """Your job is to compare the biases from different media outlets, based off the subject of a topic searched for by a user.
You will be given the subject the user searched for. 
You will be given bias analyses for 1 or more articles for 2 or more media outlets.
You will be given the sentiment analysis, which is a float between -1 and 1, where -1 is full negative bias and 1 and full positive bias.
You will also be given a write up on the bias shown in each article. 
Compare the biases between these two media outlets, and draw conclusions between the biases of each of the outlets.
"""

news_rating_bias = {
    "NPR": "Center Left",
    "Fox News": "Right",
}