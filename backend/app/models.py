from database import Base
from sqlalchemy import Column, Integer, String, TIMESTAMP, text, JSON
from pydantic import BaseModel, Field

class UserQueryAndResponse(Base):
    __tablename__ = "user_query_and_response"

    id = Column(Integer, primary_key=True, nullable=False)
    user_query = Column(String, nullable=False)
    query_subject = Column(String, nullable=False)
    serp_params = Column(JSON, nullable=False)


class NewsExtractSchema(BaseModel):
    main_article_title: str = Field(description="The main title of the article.")
    main_article_content: str = Field(description="The main content of the article. Do not include any information from other attachments.")
