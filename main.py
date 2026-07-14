import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from datetime import date

import models
from database import engine, get_db, seed_data

# Initialize DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def on_startup():
    # Seed the initial tags when the app starts
    db = next(get_db())
    seed_data(db)

# --- Helper Functions ---

def fetch_title_from_url(url: str):
    """Attempts to scrape the <title> tag from a URL."""
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        if soup.title and soup.title.string:
            return soup.title.string.strip()
    except Exception as e:
        print(f"Scraping failed for {url}: {e}")
    return None

# --- Routes ---

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    articles = db.query(models.Article).order_by(models.Article.added_at.desc()).all()
    return templates.TemplateResponse(
        name="index.html", 
        context={"request": request, "articles": articles}
    )



@app.get("/articles/new", response_class=HTMLResponse)
def new_article_form(request: Request, db: Session = Depends(get_db)):
    tags = db.query(models.Tag).all()
    # Group tags by category for the UI
    categories = ['country', 'sport', 'abuse_type', 'organisation']
    grouped_tags = {cat: [t for t in tags if t.category == cat] for cat in categories}
    return templates.TemplateResponse("article_form.html", {"request": request, "tags": grouped_tags, "article": None})

@app.post("/articles/new")
def create_article(
    url: str = Form(...), 
    title: str = Form(None), 
    publish_date: str = Form(None), 
    added_by: str = Form(None), 
    summary: str = Form(None), 
    status: str = Form("new"),
    tags_ids: list = Form(None), # IDs of existing tags selected
    new_tags: str = Form(None),  # Comma separated new tags in format "cat:val,cat:val"
    db: Session = Depends(get_db)
):
    # 1. Check for duplicate URL
    existing = db.query(models.Article).filter(models.Article.url == url).first()
    if existing:
        return templates.TemplateResponse("article_form.html", {
            "request": Request(), 
            "error": f"This URL has already been logged: {existing.title} ({existing.added_at})",
            "tags": {} # Simplified for error state
        }, status_code=400)

    # 2. Auto-fill title if not provided
    if not title:
        title = fetch_title_from_url(url)

    # 3. Validation: At least one tag required
    if not tags_ids and not new_tags:
        return templates.TemplateResponse("article_form.html", {"request": Request(), "error": "At least one tag is required."}, status_code=400)

    # Create Article object
    pub_date = date.fromisoformat(publish_date) if publish_date else None
    new_art = models.Article(url=url, title=title, publish_date=pub_date, added_by=added_by, summary=summary, status=status)
    db.add(new_art)
    db.flush() # Get the new_art.id

    # Handle existing tags
    if tags_ids:
        for tid in tags_ids:
            tag = db.query(models.Tag).get(int(tid))
            if tag: new_art.tags.append(tag)

    # Handle brand-new tags (passed as "category:value")
    if new_tags:
        for entry in new_tags.split(','):
            if ':' in entry:
                cat, val = entry.split(':', 1)
                cat, val = cat.strip(), val.strip()
                tag = db.query(models.Tag).filter_by(name=val, category=cat).first()
                if not tag:
                    tag = models.Tag(name=val, category=cat)
                    db.add(tag)
                new_art.tags.append(tag)

    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/articles/{id}", response_class=HTMLResponse)
def article_detail(request: Request, id: int, db: Session = Depends(get_db)):
    article = db.query(models.Article).get(id)
    if not article: raise HTTPException(status_code=404)
    return templates.TemplateResponse("article_detail.html", {"request": request, "article": article})

@app.get("/articles/{id}/edit", response_class=HTMLResponse)
def edit_article_form(request: Request, id: int, db: Session = Depends(get_db)):
    article = db.query(models.Article).get(id)
    tags = db.query(models.Tag).all()
    categories = ['country', 'sport', 'abuse_type', 'organisation']
    grouped_tags = {cat: [t for t in tags if t.category == cat] for cat in categories}
    return templates.TemplateResponse("article_form.html", {"request": request, "tags": grouped_tags, "article": article})

@app.post("/articles/{id}/edit")
def update_article(
    id: int, url: str = Form(...), title: str = Form(None), 
    publish_date: str = Form(None), added_by: str = Form(None), 
    summary: str = Form(None), status: str = Form("new"),
    tags_ids: list = Form(None), db: Session = Depends(get_db)
):
    article = db.query(models.Article).get(id)
    article.url = url
    article.title = title
    article.publish_date = date.fromisoformat(publish_date) if publish_date else None
    article.added_by = added_by
    article.summary = summary
    article.status = status
    
    # Update tags (clear and replace)
    article.tags = []
    if tags_ids:
        for tid in tags_ids:
            tag = db.query(models.Tag).get(int(tid))
            if tag: article.tags.append(tag)
            
    db.commit()
    return RedirectResponse(url=f"/articles/{id}", status_code=303)

@app.post("/articles/{id}/delete")
def delete_article(id: int, db: Session = Depends(get_db)):
    article = db.query(models.Article).get(id)
    db.delete(article)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = None, country: str = None, sport: str = None, abuse_type: str = None, org: str = None, db: Session = Depends(get_db)):
    query = db.query(models.Article)
    
    # Keyword search (title or summary)
    if q:
        query = query.filter(or_(models.Article.title.contains(q), models.Article.summary.contains(q)))

    # Tag filtering logic
    filters = []
    if country: filters.append(models.Article.tags.any(models.Tag.category == 'country', models.Tag.name == country))
    if sport: filters.append(models.Article.tags.any(models.Tag.category == 'sport', models.Tag.name == sport))
    if abuse_type: filters.append(models.Article.tags.any(models.Tag.category == 'abuse_type', models.Tag.name == abuse_type))
    if org: filters.append(models.Article.tags.any(models.Tag.category == 'organisation', models.Tag.name == org))

    if filters:
        query = query.filter(and_(*filters))

    results = query.order_by(models.Article.added_at.desc()).all()
    tags = db.query(models.Tag).all()
    categories = ['country', 'sport', 'abuse_type', 'organisation']
    grouped_tags = {cat: [t for t in tags if t.category == cat] for cat in categories}
    
    return templates.TemplateResponse("search.html", {"request": request, "articles": results, "tags": grouped_tags})
