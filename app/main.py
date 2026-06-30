from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from app.database import get_db
from app.models import Event, Donor, Pledge, Payment, PledgeCategory, PledgeStatus, PledgeType, PaymentMode

from app.routes.reports import router as reports_router
from app.routes.dashboard import router as dashboard_router
from app.routes.users     import router as users_router
from app.routes.events    import router as events_router
from app.routes.donors    import router as donors_router
from app.routes.pledges   import router as pledges_router
from app.routes.payments  import router as payments_router
from app.routes.family    import router as families_router

app = FastAPI(title="Dravya — Jain Temple Management")

templates = Jinja2Templates(directory="templates")


# ── Template filters ──────────────────────────────────────────────────────────

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


def format_date_input(value):
    """YYYY-MM-DD for <input type='date'> value attribute."""
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime("%Y-%m-%d")
    except Exception:
        return ""


templates.env.filters["format_amount"]     = format_amount
templates.env.filters["format_date"]       = format_date
templates.env.filters["format_date_input"] = format_date_input


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_user():
    """Placeholder until auth is wired up."""
    return type("User", (), {"name": "Admin", "role": "admin"})()


def compute_event_status(start, end, now):
    if not start or not end:
        return "upcoming"
    if start.tzinfo is None: start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo   is None: end   = end.replace(tzinfo=timezone.utc)
    if now < start:  return "upcoming"
    if now > end:    return "completed"
    return "active"


# ── Shared dashboard query ────────────────────────────────────────────────────

def get_dashboard_data(db: Session, status_filter: str = None, search: str = None):
    now          = datetime.now(timezone.utc)
    all_events   = db.query(Event).all()
    total_donors = db.query(Donor).count()

    all_events_data = []
    for event in all_events:
        status = compute_event_status(event.start_date, event.end_date, now)

        total_promised = float(db.query(
            func.coalesce(func.sum(Pledge.promised_amount), 0)
        ).filter(
            Pledge.event_id == event.event_id,
            Pledge.pledge_category == PledgeCategory.DONATION
        ).scalar())

        total_received = float(db.query(
            func.coalesce(func.sum(Payment.amount), 0)
        ).join(Pledge, Payment.pledge_id == Pledge.pledge_id)
         .filter(
            Pledge.event_id == event.event_id,
            Pledge.pledge_category == PledgeCategory.DONATION
        ).scalar())

        event_donors = db.query(
            func.count(func.distinct(Pledge.donor_id))
        ).filter(
            Pledge.event_id == event.event_id,
            Pledge.donor_id != None
        ).scalar()

        open_roles = db.query(func.count(Pledge.pledge_id)).filter(
            Pledge.event_id == event.event_id,
            Pledge.pledge_category == PledgeCategory.ROLE,
            Pledge.donor_id == None
        ).scalar()

        all_events_data.append({
            "event_id":       event.event_id,
            "event_name":     event.event_name,
            "category":       event.category,
            "start_date":     event.start_date,
            "end_date":       event.end_date,
            "status":         status,
            "total_promised": total_promised,
            "total_received": total_received,
            "total_donors":   event_donors,
            "open_roles":     open_roles,
        })

    summary = {
        "active_events":  sum(1 for e in all_events_data if e["status"] == "active"),
        "total_received": sum(e["total_received"] for e in all_events_data),
        "total_pending":  sum(e["total_promised"] - e["total_received"] for e in all_events_data),
        "total_donors":   total_donors,
    }

    filtered = all_events_data
    if status_filter:
        filtered = [e for e in filtered if e["status"] == status_filter]
    if search:
        s = search.lower()
        filtered = [
            e for e in filtered
            if s in (e["event_name"] or "").lower()
            or s in (e["category"]   or "").lower()
        ]

    return summary, filtered


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    status: str = None,
    q: str = None,
    db: Session = Depends(get_db)
):
    summary, events = get_dashboard_data(db, status_filter=status, search=q)
    return templates.TemplateResponse(request, "dashboard.html", {
        "current_user":    make_user(),
        "summary":         summary,
        "events":          events,
        "status_filter":   status or "",
        "search_query":    q or "",
        "form_error":      None,
        "success_message": None,
    })


@app.post("/events/create", response_class=HTMLResponse)
async def create_event_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()

    event_name     = form.get("event_name", "").strip()
    category       = form.get("category",   "").strip()
    start_date_str = form.get("start_date", "").strip()
    end_date_str   = form.get("end_date",   "").strip()
    description    = form.get("description","").strip()

    def error(msg):
        summary, events = get_dashboard_data(db)
        return templates.TemplateResponse(request, "dashboard.html", {
            "current_user":    make_user(),
            "summary":         summary,
            "events":          events,
            "status_filter":   "",
            "search_query":    "",
            "form_error":      msg,
            "success_message": None,
        })

    if not event_name or not category or not start_date_str or not end_date_str:
        return error("Event name, category, and dates are required.")

    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date   = datetime.strptime(end_date_str,   "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return error("Invalid date format.")

    if end_date < start_date:
        return error("End date cannot be before start date.")

    new_event = Event(
        event_name  = event_name,
        category    = category,
        start_date  = start_date,
        end_date    = end_date,
        description = description or None,
    )
    db.add(new_event)
    db.flush()

    for i in range(3):
        role_name     = form.get(f"roles[{i}][role_name]",     "").strip()
        target_amount = form.get(f"roles[{i}][target_amount]", "").strip()
        role_desc     = form.get(f"roles[{i}][description]",   "").strip()
        if not role_name:
            continue
        db.add(Pledge(
            event_id        = new_event.event_id,
            donor_id        = None,
            pledge_type     = PledgeType.CASH,
            pledge_category = PledgeCategory.ROLE,
            promised_amount = float(target_amount) if target_amount else None,
            item_name       = role_name,
            description     = role_desc or None,
            status          = PledgeStatus.PENDING,
        ))

    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/events/{event_id}", response_class=HTMLResponse)
def event_detail_page(
    request: Request,
    event_id: int,
    tab: str = "pledges",
    q: str = None,
    status: str = None,
    pledge_type: str = None,
    rq: str = None,
    pq: str = None,
    payment_mode: str = None,
    db: Session = Depends(get_db)
):
    # ── 1. Event ──────────────────────────────────────────────────────────────
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    now          = datetime.now(timezone.utc)
    event_status = compute_event_status(event.start_date, event.end_date, now)

    # ── 2. Financials ─────────────────────────────────────────────────────────
    total_pledged = float(db.query(
        func.coalesce(func.sum(Pledge.promised_amount), 0)
    ).filter(
        Pledge.event_id == event_id,
        Pledge.pledge_category == PledgeCategory.DONATION
    ).scalar())

    total_received = float(db.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).join(Pledge, Payment.pledge_id == Pledge.pledge_id)
     .filter(
        Pledge.event_id == event_id,
        Pledge.pledge_category == PledgeCategory.DONATION
    ).scalar())

    total_donors = db.query(
        func.count(func.distinct(Pledge.donor_id))
    ).filter(
        Pledge.event_id == event_id,
        Pledge.donor_id != None
    ).scalar()

    total_pledges = db.query(func.count(Pledge.pledge_id)).filter(
        Pledge.event_id == event_id,
        Pledge.pledge_category == PledgeCategory.DONATION
    ).scalar()

    anonymous_count = db.query(func.count(Pledge.pledge_id)).join(
        Donor, Pledge.donor_id == Donor.donor_id
    ).filter(
        Pledge.event_id == event_id,
        Donor.is_anonymous == True
    ).scalar()

    # ── 3. Event dict ─────────────────────────────────────────────────────────
    event_data = {
        "event_id":        event.event_id,
        "event_name":      event.event_name,
        "category":        event.category,
        "start_date":      event.start_date,
        "end_date":        event.end_date,
        "description":     event.description,
        "status":          event_status,
        "total_pledged":   total_pledged,
        "total_received":  total_received,
        "total_expenses":  0,
        "total_donors":    total_donors,
        "total_pledges":   total_pledges,
        "anonymous_count": anonymous_count,
    }

    # ── 4. Pledges tab ────────────────────────────────────────────────────────
    pledge_query = db.query(Pledge, Donor).outerjoin(
        Donor, Pledge.donor_id == Donor.donor_id
    ).filter(
        Pledge.event_id == event_id,
        Pledge.pledge_category == PledgeCategory.DONATION
    )

    if q:
        pledge_query = pledge_query.filter(
            func.lower(Donor.first_name + " " + Donor.last_name).contains(q.lower())
        )
    if status:
        status_map = {
            "pending":   PledgeStatus.PENDING,
            "partial":   PledgeStatus.PARTIAL,
            "completed": PledgeStatus.COMPLETED,
        }
        if status in status_map:
            pledge_query = pledge_query.filter(Pledge.status == status_map[status])
    if pledge_type:
        type_map = {
            "cash":    PledgeType.CASH,
            "labh":    PledgeType.LABH,
            "in_kind": PledgeType.IN_KIND,
        }
        if pledge_type in type_map:
            pledge_query = pledge_query.filter(Pledge.pledge_type == type_map[pledge_type])

    pledges = []
    for pledge, donor in pledge_query.all():
        received = float(db.query(
            func.coalesce(func.sum(Payment.amount), 0)
        ).filter(Payment.pledge_id == pledge.pledge_id).scalar())

        if donor:
            donor_name = f"{donor.first_name or ''} {donor.last_name or ''}".strip()
            if donor.is_anonymous:
                donor_name = "Anonymous"
        else:
            donor_name = "—"

        pledges.append({
            "pledge_id":       pledge.pledge_id,
            "donor_name":      donor_name,
            "pledge_type":     pledge.pledge_type.value.lower() if pledge.pledge_type else "—",
            "pledge_category": pledge.pledge_category.value.lower() if pledge.pledge_category else "—",
            "promised_amount": float(pledge.promised_amount or 0),
            "received_amount": received,
            "status":          pledge.status.value.lower() if pledge.status else "pending",
            "description":     pledge.description,
        })

    # ── 5. Roles tab ──────────────────────────────────────────────────────────
    role_query = db.query(Pledge, Donor).outerjoin(
        Donor, Pledge.donor_id == Donor.donor_id
    ).filter(
        Pledge.event_id == event_id,
        Pledge.pledge_category == PledgeCategory.ROLE
    )

    if rq:
        role_query = role_query.filter(
            func.lower(Pledge.item_name).contains(rq.lower()) |
            func.lower(Donor.first_name + " " + Donor.last_name).contains(rq.lower())
        )

    roles = []
    for pledge, donor in role_query.all():
        donor_name = f"{donor.first_name or ''} {donor.last_name or ''}".strip() if donor else "Unassigned"
        roles.append({
            "role_id":       pledge.pledge_id,
            "role_name":     pledge.item_name or "—",
            "donor_name":    donor_name,
            "target_amount": float(pledge.promised_amount or 0),
            "description":   pledge.description,
            "status":        pledge.status.value.lower() if pledge.status else "pending",
        })

    # ── 6. Payments tab ───────────────────────────────────────────────────────
    payment_query = db.query(Payment).join(
        Pledge, Payment.pledge_id == Pledge.pledge_id
    ).filter(Pledge.event_id == event_id)

    if pq:
        payment_query = payment_query.filter(
            func.lower(Payment.donor_name).contains(pq.lower()) |
            func.lower(Payment.receipt_no).contains(pq.lower())
        )
    if payment_mode:
        mode_map = {
            "cash":   PaymentMode.CASH,
            "upi":    PaymentMode.UPI,
            "cheque": PaymentMode.CHEQUE,
            "neft":   PaymentMode.NEFT,
        }
        if payment_mode in mode_map:
            payment_query = payment_query.filter(Payment.payment_mode == mode_map[payment_mode])

    payments = [{
        "receipt_no":       p.receipt_no,
        "donor_name":       p.donor_name or "—",
        "amount":           float(p.amount or 0),
        "payment_mode":     p.payment_mode.value.lower() if p.payment_mode else "—",
        "reference_number": p.payment_ref,
        "payment_date":     p.payment_date,
        "recorded_by":      p.recorded_by,
    } for p in payment_query.order_by(Payment.payment_date.desc()).all()]

    # ── 7. Donors for modal dropdowns ─────────────────────────────────────────
    all_donors = db.query(Donor).order_by(Donor.first_name).all()

    return templates.TemplateResponse(request, "event.html", {
        "request":            request,
        "current_user":       make_user(),
        "event":              event_data,
        "pledges":            pledges,
        "roles":              roles,
        "payments":           payments,
        "donors":             all_donors,
        "active_tab":         tab,
        "q":                  q or "",
        "status":             status or "",
        "pledge_type":        pledge_type or "",
        "rq":                 rq or "",
        "pq":                 pq or "",
        "payment_mode":       payment_mode or "",
        "flash_error":        None,
        "flash_success":      None,
        "pledge_form_error":  None,
        "inkind_form_error":  None,
        "payment_form_error": None,
        "role_form_error":    None,
    })


@app.get("/donors", response_class=HTMLResponse)
def donors_page(request: Request, db: Session = Depends(get_db)):
    donors = db.query(Donor).all()
    return templates.TemplateResponse(request, "donor.html", {
        "current_user": make_user(),
        "donors":       donors,
    })


@app.get("/logout")
def logout():
    return RedirectResponse(url="/login")


# ── API routers ───────────────────────────────────────────────────────────────

app.include_router(dashboard_router)
app.include_router(users_router)
app.include_router(events_router)
app.include_router(donors_router)
app.include_router(pledges_router)
app.include_router(payments_router)
app.include_router(families_router)
app.include_router(reports_router)