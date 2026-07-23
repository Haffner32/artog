import requests
from bs4 import BeautifulSoup
from htmldate import find_date
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, extract
from types import SimpleNamespace
from datetime import date

import models
from database import engine, get_db, seed_data

models.Base.metadata.create_all(bind=engine)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            request,
            "404.html", 
            {"request": request, "detail": exc.detail},
            status_code=404
        )
    return HTMLResponse(content=str(exc.detail), status_code=exc.status_code)

@app.on_event("startup")
def on_startup():
    db = next(get_db())
    seed_data(db)

def fetch_article_metadata(url: str):
    """Attempts to scrape title, summary, and publish date from a URL.
    Returns a dict with each field set to a string or None if not found.
    Raises requests.exceptions.RequestException if the request itself fails
    (network error, timeout, non-2xx status, bot-block, etc.)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }

    response = requests.get(url, headers=headers, timeout=8)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    # --- Title ---
    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.title and soup.title.string and soup.title.string.strip():
        title = soup.title.string.strip()

    # --- Summary ---
    summary = None
    og_desc = soup.find("meta", property="og:description")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if og_desc and og_desc.get("content"):
        summary = og_desc["content"].strip()
    elif meta_desc and meta_desc.get("content"):
        summary = meta_desc["content"].strip()

    # --- Publish date ---
    publish_date = find_date(response.text, url=url, original_date=True)
    

    return {"title": title, "summary": summary, "publish_date": publish_date}

def _rebuild_form_state(url, title, publish_date, added_by, summary, status, article_id=None):
    """Returns a fake 'article' from submitted form data so the form re-renders with the user's input intact after validation error."""
    try:
        pub_date = date.fromisoformat(publish_date) if publish_date else None
    except ValueError:
        pub_date = None
    return SimpleNamespace(
        id=article_id,
        url=url,
        title=title,
        publish_date=pub_date,
        added_by=added_by,
        summary=summary,
        status=status,
        tags=[]
    )

def _grouped_tags(db):
    tags = db.query(models.Tag).all()
    categories = ['country', 'sport', 'abuse_type', 'organisation']
    return {cat: [t for t in tags if t.category == cat] for cat in categories}

def _available_years(db):
    dates = db.query(models.Article.publish_date).filter(models.Article.publish_date != None).all()
    years = sorted({d[0].year for d in dates if d[0] is not None}, reverse=True)
    return years

@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    articles = db.query(models.Article).order_by(models.Article.added_at.desc()).all()
    return templates.TemplateResponse(request, "index.html", {"articles": articles})

@app.get("/articles/new", response_class=HTMLResponse)
def new_article_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "article_form.html", {"tags": _grouped_tags(db), "article": None})

@app.get("/articles/fetch-metadata")
def fetch_metadata(url: str):
    """Called by the 'Auto-fill from URL' button via fetch(). Returns whichever
    fields could be scraped; fields that couldn't be found are null so the
    frontend can show a per-field 'couldn't auto-detect' message."""
    try:
        metadata = fetch_article_metadata(url)
        return {"success": True, **metadata}
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": "Couldn't reach that URL to auto-fill details. Please enter them manually.",
            "title": None, "summary": None, "publish_date": None
        }

@app.post("/articles/new")
def create_article(
    request: Request,
    url: str = Form(...),
    title: str = Form(None),
    publish_date: str = Form(None),
    added_by: str = Form(None),
    summary: str = Form(None),
    status: str = Form("new"),
    tags_ids: list = Form(None),
    new_tags: str = Form(None),
    db: Session = Depends(get_db)
):
    existing = db.query(models.Article).filter(models.Article.url == url).first()
    if existing:
        return templates.TemplateResponse(
            request, "article_form.html",
            {"error": f"This URL has already been logged: {existing.title} ({existing.added_at})",
             "tags": _grouped_tags(db), "article": None},
            status_code=400
        )

    if not tags_ids and not new_tags:
        return templates.TemplateResponse(
            request, "article_form.html",
            {"error": "At least one tag is required.",
             "tags": _grouped_tags(db),
             "article": _rebuild_form_state(url, title, publish_date, added_by, summary, status)},
            status_code=400
        )

    pub_date = date.fromisoformat(publish_date) if publish_date else None
    new_art = models.Article(url=url, title=title, publish_date=pub_date, added_by=added_by, summary=summary, status=status)
    db.add(new_art)
    db.flush()

    if tags_ids:
        for tid in tags_ids:
            tag = db.get(models.Tag, int(tid))
            if tag: new_art.tags.append(tag)

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
    article = db.get(models.Article, id)
    if not article: raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "article_detail.html", {"article": article})

@app.get("/articles/{id}/edit", response_class=HTMLResponse)
def edit_article_form(request: Request, id: int, db: Session = Depends(get_db)):
    article = db.get(models.Article, id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with id {id} not found")
    return templates.TemplateResponse(request, "article_form.html", {"tags": _grouped_tags(db), "article": article})

@app.post("/articles/{id}/edit")
def update_article(
    request: Request,
    id: int, url: str = Form(...), title: str = Form(None),
    publish_date: str = Form(None), added_by: str = Form(None),
    summary: str = Form(None), status: str = Form("new"),
    tags_ids: list = Form(None), new_tags: str = Form(None),
    db: Session = Depends(get_db)
):
    article = db.get(models.Article, id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with id {id} not found")

    if not tags_ids and not new_tags:
        return templates.TemplateResponse(
            request, "article_form.html",
            {"error": "At least one tag is required.",
             "tags": _grouped_tags(db),
             "article": _rebuild_form_state(url, title, publish_date, added_by, summary, status, article_id=id)},
            status_code=400
        )

    article.url = url
    article.title = title
    article.publish_date = date.fromisoformat(publish_date) if publish_date else None
    article.added_by = added_by
    article.summary = summary
    article.status = status

    article.tags = []
    if tags_ids:
        for tid in tags_ids:
            tag = db.get(models.Tag, int(tid))
            if tag: article.tags.append(tag)

    if new_tags:
        for entry in new_tags.split(','):
            if ':' in entry:
                cat, val = entry.split(':', 1)
                cat, val = cat.strip(), val.strip()
                tag = db.query(models.Tag).filter_by(name=val, category=cat).first()
                if not tag:
                    tag = models.Tag(name=val, category=cat)
                    db.add(tag)
                article.tags.append(tag)

    db.commit()
    return RedirectResponse(url=f"/articles/{id}", status_code=303)

@app.post("/articles/{id}/delete")
def delete_article(id: int, db: Session = Depends(get_db)):
    article = db.get(models.Article, id)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with id {id} not found")
    db.delete(article)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/search", response_class=HTMLResponse)
def search(
    request: Request, q: str = None, country: str = None, sport: str = None,
    abuse_type: str = None, org: str = None,
    year: str = None, month: str = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Article)

    if q:
        query = query.filter(or_(models.Article.title.contains(q), models.Article.summary.contains(q)))

    filters = []
    if country: filters.append(models.Article.tags.any(and_(models.Tag.category == 'country', models.Tag.name == country)))
    if sport: filters.append(models.Article.tags.any(and_(models.Tag.category == 'sport', models.Tag.name == sport)))
    if abuse_type: filters.append(models.Article.tags.any(and_(models.Tag.category == 'abuse_type', models.Tag.name == abuse_type)))
    if org: filters.append(models.Article.tags.any(and_(models.Tag.category == 'organisation', models.Tag.name == org)))

    if filters:
        query = query.filter(and_(*filters))

    year_int = int(year) if year else None
    month_int = int(month) if month else None

    if year_int:
        query = query.filter(extract('year', models.Article.publish_date) == year_int)
    if month_int:
        query = query.filter(extract('month', models.Article.publish_date) == month_int)

    results = query.order_by(models.Article.added_at.desc()).all()
    active_filter_count = sum(1 for v in [q, country, sport, abuse_type, org, year, month] if v)

    return templates.TemplateResponse(request, "search.html", {
        "articles": results,
        "tags": _grouped_tags(db),
        "available_years": _available_years(db),
        "active_filter_count": active_filter_count
    })