import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import models
from database import get_db, seed_data
from main import app

# Use a file-based sqlite DB per test session (in-memory doesn't play well
# with multiple connections across TestClient requests + fixtures).
TEST_DATABASE_URL = "sqlite:///./test_safesport.db"


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    seed_data(session)

    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=engine)
        engine.dispose()
        import os
        if os.path.exists("test_safesport.db"):
            os.remove("test_safesport.db")


@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_tag(db_session):
    tag = db_session.query(models.Tag).filter_by(category="country", name="Singapore").first()
    return tag
