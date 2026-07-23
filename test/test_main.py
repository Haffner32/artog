from unittest.mock import patch
import models


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Logged Articles" in response.text


def test_home_page_shows_no_articles_message_when_empty(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "No articles logged yet" in response.text


def test_home_page_lists_created_article(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/story-1",
        "title": "Test Story",
        "added_by": "Alice",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.get("/")
    assert response.status_code == 200
    assert "Test Story" in response.text


# ---------------------------------------------------------------------------
# New article form (GET)
# ---------------------------------------------------------------------------

def test_new_article_form_loads(client):
    response = client.get("/articles/new")
    assert response.status_code == 200
    assert "Add New Article" in response.text


# ---------------------------------------------------------------------------
# Create article (POST /articles/new)
# ---------------------------------------------------------------------------

def test_create_article_with_existing_tag_succeeds(client, sample_tag):
    response = client.post("/articles/new", data={
        "url": "https://example.com/article-a",
        "title": "Article A",
        "added_by": "Bob",
        "tags_ids": [str(sample_tag.id)],
    }, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_create_article_with_new_custom_tag_succeeds(client):
    response = client.post("/articles/new", data={
        "url": "https://example.com/article-b",
        "title": "Article B",
        "added_by": "Carol",
        "new_tags": "sport:Curling, country:Norway",
    }, follow_redirects=False)

    assert response.status_code == 303


def test_create_article_persists_new_custom_tags(client, db_session):
    client.post("/articles/new", data={
        "url": "https://example.com/article-c",
        "added_by": "Dave",
        "new_tags": "sport:Curling",
    })
    tag = db_session.query(models.Tag).filter_by(name="Curling", category="sport").first()
    assert tag is not None


def test_create_article_without_any_tag_fails_validation(client):
    response = client.post("/articles/new", data={
        "url": "https://example.com/article-d",
        "added_by": "Eve",
    })
    assert response.status_code == 400
    assert "At least one tag is required" in response.text
    # Regression check: the tag picker must still render on validation failure
    assert "tag-checkboxes" in response.text or "Country" in response.text


def test_create_article_duplicate_url_fails(client, sample_tag):
    payload = {
        "url": "https://example.com/dup-story",
        "title": "First Save",
        "added_by": "Frank",
        "tags_ids": [str(sample_tag.id)],
    }
    client.post("/articles/new", data=payload)

    response = client.post("/articles/new", data=payload)
    assert response.status_code == 400
    assert "already been logged" in response.text


def test_create_article_without_title_saves_as_untitled(client, sample_tag):
    # Auto-fill is now a separate client-side action (the "Auto-fill from URL"
    # button calling /articles/fetch-metadata), so saving with a blank title
    # should no longer trigger a server-side scrape.
    with patch("main.fetch_article_metadata") as mock_fetch:
        client.post("/articles/new", data={
            "url": "https://example.com/no-title",
            "added_by": "Grace",
            "tags_ids": [str(sample_tag.id)],
        })
        mock_fetch.assert_not_called()
    response = client.get("/")
    assert "Untitled Article" in response.text


def test_create_article_keeps_explicit_title(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/explicit-title",
        "title": "My Explicit Title",
        "added_by": "Heidi",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.get("/")
    assert "My Explicit Title" in response.text


# ---------------------------------------------------------------------------
# Auto-fill metadata endpoint (GET /articles/fetch-metadata)
# ---------------------------------------------------------------------------

def test_fetch_metadata_success_returns_all_fields(client):
    with patch("main.fetch_article_metadata", return_value={
        "title": "Scraped Title",
        "summary": "Scraped summary text.",
        "publish_date": "2026-01-15",
    }):
        response = client.get("/articles/fetch-metadata", params={"url": "https://example.com/article"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["title"] == "Scraped Title"
    assert data["summary"] == "Scraped summary text."
    assert data["publish_date"] == "2026-01-15"


def test_fetch_metadata_partial_fields_returns_nulls_for_missing(client):
    with patch("main.fetch_article_metadata", return_value={
        "title": "Scraped Title",
        "summary": None,
        "publish_date": None,
    }):
        response = client.get("/articles/fetch-metadata", params={"url": "https://example.com/article"})
    data = response.json()
    assert data["success"] is True
    assert data["title"] == "Scraped Title"
    assert data["summary"] is None
    assert data["publish_date"] is None


def test_fetch_metadata_request_failure_returns_error(client):
    import requests
    with patch("main.fetch_article_metadata", side_effect=requests.exceptions.RequestException("blocked")):
        response = client.get("/articles/fetch-metadata", params={"url": "https://example.com/blocked"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["title"] is None
    assert "error" in data


# ---------------------------------------------------------------------------
# Article detail (GET /articles/{id})
# ---------------------------------------------------------------------------

def test_article_detail_loads_for_existing_article(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/detail-story",
        "title": "Detail Story",
        "added_by": "Ivan",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.get("/articles/1")
    assert response.status_code == 200
    assert "Detail Story" in response.text


def test_article_detail_404_for_missing_article(client):
    response = client.get("/articles/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Edit article form (GET /articles/{id}/edit)
# ---------------------------------------------------------------------------

def test_edit_article_form_loads_with_existing_values(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/edit-story",
        "title": "Editable Story",
        "added_by": "Judy",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.get("/articles/1/edit")
    assert response.status_code == 200
    assert "Editable Story" in response.text
    assert "Edit Article" in response.text


# ---------------------------------------------------------------------------
# Update article (POST /articles/{id}/edit)
# ---------------------------------------------------------------------------

def test_update_article_changes_fields(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/update-story",
        "title": "Original Title",
        "added_by": "Karl",
        "tags_ids": [str(sample_tag.id)],
    })

    response = client.post("/articles/1/edit", data={
        "url": "https://example.com/update-story",
        "title": "Updated Title",
        "added_by": "Karl",
        "status": "reviewed",
        "tags_ids": [str(sample_tag.id)],
    }, follow_redirects=False)

    assert response.status_code == 303
    detail = client.get("/articles/1")
    assert "Updated Title" in detail.text
    assert "REVIEWED" in detail.text


def test_update_article_rejects_when_no_tags_submitted(client, sample_tag, db_session):
    client.post("/articles/new", data={
        "url": "https://example.com/clear-tags",
        "added_by": "Leo",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.post("/articles/1/edit", data={
        "url": "https://example.com/clear-tags",
        "added_by": "Leo",
    })
    assert response.status_code == 400
    assert "At least one tag is required" in response.text

    # Original tag should still be intact since the update was rejected
    article = db_session.query(models.Article).get(1)
    assert article.tags == [sample_tag]


# ---------------------------------------------------------------------------
# Delete article (POST /articles/{id}/delete)
# ---------------------------------------------------------------------------

def test_delete_article_removes_it(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/delete-story",
        "added_by": "Mallory",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.post("/articles/1/delete", follow_redirects=False)
    assert response.status_code == 303

    detail = client.get("/articles/1")
    assert detail.status_code == 404


# ---------------------------------------------------------------------------
# Search (GET /search)
# ---------------------------------------------------------------------------

def test_search_page_loads(client):
    response = client.get("/search")
    assert response.status_code == 200
    assert "Search & Filter" in response.text


def test_search_by_keyword_matches_title(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/keyword-story",
        "title": "Unique Keyword Headline",
        "added_by": "Nina",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.get("/search", params={"q": "Keyword Headline"})
    assert response.status_code == 200
    assert "Unique Keyword Headline" in response.text


def test_search_by_keyword_excludes_non_matching(client, sample_tag):
    client.post("/articles/new", data={
        "url": "https://example.com/other-story",
        "title": "Completely Different",
        "added_by": "Oscar",
        "tags_ids": [str(sample_tag.id)],
    })
    response = client.get("/search", params={"q": "NoMatchHere"})
    assert response.status_code == 200
    assert "No articles match your search criteria" in response.text


def test_search_by_country_tag_filters_results(client, db_session):
    sg_tag = db_session.query(models.Tag).filter_by(name="Singapore", category="country").first()
    us_tag = db_session.query(models.Tag).filter_by(name="USA", category="country").first()

    client.post("/articles/new", data={
        "url": "https://example.com/sg-story",
        "title": "SG Story",
        "added_by": "Peggy",
        "tags_ids": [str(sg_tag.id)],
    })
    client.post("/articles/new", data={
        "url": "https://example.com/us-story",
        "title": "US Story",
        "added_by": "Peggy",
        "tags_ids": [str(us_tag.id)],
    })

    response = client.get("/search", params={"country": "Singapore"})
    assert "SG Story" in response.text
    assert "US Story" not in response.text