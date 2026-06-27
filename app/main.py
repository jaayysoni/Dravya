from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from app.database import get_db
from app.models import Event, Donor, Pledge, Payment

from app.routes.users import router as users_router
from app.routes.events import router as events_router
from app.routes.donors import router as donors_router
from app.routes.pledges import router as pledges_router
from app.routes.payments import router as payments_router
from app.routes.family import router as families_router
from app.routes.dashboard import router as dashboard_router

app = FastAPI()

templates = Jinja2Templates(directory="templates")


def format_amount(value):
    try:
        value = float(value)
        if value >= 10_000_000:
            return f"₹{value/10_000_000:.1f}Cr"
        elif value >= 100_000:
            return f"₹{value/100_000:.1f}L"
        elif value >= 1000:
            return f"₹{value/1000:.1f}K"
        else:
            return f"₹{value:,.0f}"
    except Exception:
        return "₹0"


def format_date(value):
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime("%d %b %Y")
    except Exception:
        return "—"


templates.env.filters["format_amount"] = format_amount
templates.env.filters["format_date"] = format_date


def get_dashboard_data(db: Session, status_filter: str = None, search: str = None):
    now = datetime.now(timezone.utc)
    all_events = db.query(Event).all()
    total_donors = db.query(Donor).count()

    all_events_data = []
    for event in all_events:
        start = event.start_date
        end = event.end_date
        if start and end:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            if now < start:
                status = "upcoming"
            elif now > end:
                status = "completed"
            else:
                status = "active"
        else:
            status = "upcoming"

        total_promised = float(db.query(
            func.coalesce(func.sum(Pledge.promised_amount), 0)
        ).filter(Pledge.event_id == event.event_id).scalar())

        total_received = float(db.query(
            func.coalesce(func.sum(Payment.amount), 0)
        ).join(Pledge, Payment.pledge_id == Pledge.pledge_id)
         .filter(Pledge.event_id == event.event_id).scalar())

        event_donors = db.query(
            func.count(func.distinct(Pledge.donor_id))
        ).filter(Pledge.event_id == event.event_id).scalar()

        all_events_data.append({
            "event_id": event.event_id,
            "event_name": event.event_name,
            "category": event.category,
            "start_date": event.start_date,
            "end_date": event.end_date,
            "status": status,
            "total_promised": total_promised,
            "total_received": total_received,
            "total_donors": event_donors,
        })

    summary = {
        "active_events": sum(1 for e in all_events_data if e["status"] == "active"),
        "total_received": sum(e["total_received"] for e in all_events_data),
        "total_pending": sum(e["total_promised"] - e["total_received"] for e in all_events_data),
        "total_donors": total_donors,
    }

    filtered = all_events_data
    if status_filter:
        filtered = [e for e in filtered if e["status"] == status_filter]
    if search:
        s = search.lower()
        filtered = [
            e for e in filtered
            if s in (e["event_name"] or "").lower()
            or s in (e["category"] or "").lower()
        ]

    return summary, filtered


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    status: str = None,
    q: str = None,
    db: Session = Depends(get_db)
):
    current_user = type("User", (), {"name": "Admin", "role": "admin"})()
    summary, events = get_dashboard_data(db, status_filter=status, search=q)
    return templates.TemplateResponse(request, "dashboard.html", {
        "current_user": current_user,
        "summary": summary,
        "events": events,
        "status_filter": status or "",
        "search_query": q or "",
        "form_error": None,
        "success_message": None,
    })


@app.post("/events/create", response_class=HTMLResponse)
async def create_event_post(
    request: Request,
    db: Session = Depends(get_db)
):
    form = await request.form()
    event_name = form.get("event_name", "").strip()
    category = form.get("category", "").strip()
    start_date_str = form.get("start_date", "").strip()
    end_date_str = form.get("end_date", "").strip()
    description = form.get("description", "").strip()

    current_user = type("User", (), {"name": "Admin", "role": "admin"})()

    def error(msg):
        summary, events = get_dashboard_data(db)
        return templates.TemplateResponse(request, "dashboard.html", {
            "current_user": current_user,
            "summary": summary,
            "events": events,
            "status_filter": "",
            "search_query": "",
            "form_error": msg,
            "success_message": None,
        })

    if not event_name or not category or not start_date_str or not end_date_str:
        return error("Event name, category, and dates are required.")

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return error("Invalid date format.")

    if end_date < start_date:
        return error("End date cannot be before start date.")

    new_event = Event(
        event_name=event_name,
        category=category,
        start_date=start_date,
        end_date=end_date,
        description=description or None,
    )
    db.add(new_event)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_detail_page(request: Request, event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.event_id == event_id).first()
    return templates.TemplateResponse(request, "event.html", {
        "event": event,
        "event_id": event_id,
    })


@app.get("/donors", response_class=HTMLResponse)
def donors_page(request: Request, db: Session = Depends(get_db)):
    donors = db.query(Donor).all()
    return templates.TemplateResponse(request, "donor.html", {
        "donors": donors,
    })


@app.get("/logout")
def logout():
    return RedirectResponse(url="/login")


app.include_router(users_router)
app.include_router(events_router)
app.include_router(donors_router)
app.include_router(pledges_router)
app.include_router(payments_router)
app.include_router(families_router)
app.include_router(dashboard_router)