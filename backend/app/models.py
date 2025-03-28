from database import Base
from sqlalchemy import Column, Integer, String, TIMESTAMP, text, JSON

class UserQueryAndResponse(Base):
    __tablename__ = "user_query_and_response"

    id = Column(Integer, primary_key=True, nullable=False)
    user_query = Column(String, nullable=False)
    query_subject = Column(String, nullable=False)
    serp_params = Column(JSON, nullable=False)
    
