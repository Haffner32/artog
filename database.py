import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://adenchan@localhost:5432/safesport"
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def seed_data(db):
    """Populates the tags table with initial controlled vocabulary if empty."""
    # IMPORT INSIDE FUNCTION to prevent Circular Import error
    from models import Tag 

    if db.query(Tag).first():
        return

    starter_tags = [
        {"name": "Physical Abuse", "category": "abuse_type"},
        {"name": "Emotional/Psychological Abuse", "category": "abuse_type"},
        {"name": "Sexual Abuse", "category": "abuse_type"},
        {"name": "Neglect", "category": "abuse_type"},
        {"name": "Bullying/Harassment", "category": "abuse_type"},
        {"name": "Financial Misconduct", "category": "abuse_type"},
        {"name": "Other", "category": "abuse_type"},
        {"name": "Athletics", "category": "sport"},
        {"name": "Swimming", "category": "sport"},
        {"name": "Gymnastics", "category": "sport"},
        {"name": "Football", "category": "sport"},
        {"name": "Basketball", "category": "sport"},
        {"name": "Badminton", "category": "sport"},
        {"name": "Other", "category": "sport"},
        {"name": "Singapore", "category": "country"},
        {"name": "USA", "category": "country"},
        {"name": "UK", "category": "country"},
        {"name": "Australia", "category": "country"},
        {"name": "Japan", "category": "country"},
        {"name": "Other", "category": "country"},
    ]

    for tag_data in starter_tags:
        tag = Tag(name=tag_data["name"], category=tag_data["category"])
        db.add(tag)
    
    db.commit()
