from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Table, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

# Junction Table for Many-to-Many relationship between Articles and Tags
article_tags = Table(
    'article_tags',
    Base.metadata,
    Column('article_id', Integer, ForeignKey('articles.id', ondelete="CASCADE"), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id', ondelete="CASCADE"), primary_key=True)
)

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, nullable=False) 
    title = Column(String)
    publish_date = Column(Date)
    added_by = Column(String)
    added_at = Column(DateTime(timezone=False), server_default=func.now())
    summary = Column(Text)
    status = Column(String, default="new") 

    tags = relationship("Tag", secondary=article_tags, back_populates="articles")

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False) 

    # CORRECTED: Use UniqueConstraint object instead of a dictionary
    __table_args__ = (
        UniqueConstraint('name', 'category', name='_name_category_uc'),
    )

    articles = relationship("Article", secondary=article_tags, back_populates="tags")
