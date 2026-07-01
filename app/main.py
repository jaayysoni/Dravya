from urllib.parse import quote

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

# Fixes: jinja2.exceptions.UndefinedError: 'get_flashed_messages' is undefined
# (leftover Flask-ism in login.html — this no-ops it instead of erroring)
templates.env.globals["get_flashed_messages"] = lambda *a, **k: []


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


def _err_redirect(event_id: int, tab: str, hash_id: str, param: str, msg: str):
    """Redirect back to the event page with the offending modal reopened (via #hash)
    and an error message passed as a query param."""
    return RedirectResponse(
        url=f"/events/{event_id}?tab={tab}&{param}={quote(msg)}#{hash_id}",
        status_code=303,
    )


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


# ── Shared event-detail context builder ───────────────────────────────────────

def build_event_context(db: Session, event_id: int, tab: str, q=None, status=None,
                         pledge_type=None, rq=None, pq=None, payment_mode=None):
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    now          = datetime.now(timezone.utc)
    event_status = compute_event_status(event.start_date, event.end_date, now)

    # ── Financials ──────────────────────────────────────────────────────────
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

    # ── Pledges tab ─────────────────────────────────────────────────────────
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
            "donor_id":        pledge.donor_id,
            "donor_name":      donor_name,
            "pledge_type":     pledge.pledge_type.value.lower() if pledge.pledge_type else "—",
            "pledge_category": pledge.pledge_category.value.lower() if pledge.pledge_category else "—",
            "promised_amount": float(pledge.promised_amount or 0),
            "received_amount": received,
            "status":          pledge.status.value.lower() if pledge.status else "pending",
            "description":     pledge.description,
            "item_name":       pledge.item_name,
            "item_category":   pledge.item_category,
            "quantity":        float(pledge.quantity or 0),
            "unit":            pledge.unit,
            "market_value":    float(pledge.market_value or 0),
        })

    # ── Roles tab ───────────────────────────────────────────────────────────
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
            "donor_id":      pledge.donor_id,
            "donor_name":    donor_name,
            "target_amount": float(pledge.promised_amount or 0),
            "description":   pledge.description,
            "status":        pledge.status.value.lower() if pledge.status else "pending",
        })

    # ── Payments tab ────────────────────────────────────────────────────────
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

    # ── Donors for modal dropdowns ──────────────────────────────────────────
    all_donors = db.query(Donor).order_by(Donor.first_name).all()

    return {
        "current_user": make_user(),
        "event":        event_data,
        "pledges":      pledges,
        "roles":        roles,
        "payments":     payments,
        "donors":       all_donors,
        "active_tab":   tab,
        "q":            q or "",
        "status":       status or "",
        "pledge_type":  pledge_type or "",
        "rq":           rq or "",
        "pq":           pq or "",
        "payment_mode": payment_mode or "",
    }


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
    flash_success: str = None,
    flash_error: str = None,
    pledge_error: str = None,
    inkind_error: str = None,
    payment_error: str = None,
    role_error: str = None,
    db: Session = Depends(get_db),
):
    ctx = build_event_context(db, event_id, tab, q, status, pledge_type, rq, pq, payment_mode)
    ctx.update({
        "flash_success":      flash_success,
        "flash_error":        flash_error,
        "pledge_form_error":  pledge_error,
        "inkind_form_error":  inkind_error,
        "payment_form_error": payment_error,
        "role_form_error":    role_error,
    })
    return templates.TemplateResponse(request, "event.html", ctx)


# ── EDIT EVENT ─────────────────────────────────────────────────────────────
@app.post("/events/{event_id}/edit")
async def edit_event_post(request: Request, event_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event_name     = form.get("event_name", "").strip()
    category       = form.get("category", "").strip()
    start_date_str = form.get("start_date", "").strip()
    end_date_str   = form.get("end_date", "").strip()
    description    = form.get("description", "").strip()

    if not event_name or not category or not start_date_str or not end_date_str:
        return _err_redirect(event_id, "pledges", "editEventModal", "flash_error",
                              "Event name, category, and dates are required.")
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_date   = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return _err_redirect(event_id, "pledges", "editEventModal", "flash_error", "Invalid date format.")
    if end_date < start_date:
        return _err_redirect(event_id, "pledges", "editEventModal", "flash_error",
                              "End date cannot be before start date.")

    event.event_name  = event_name
    event.category    = category
    event.start_date  = start_date
    event.end_date    = end_date
    event.description = description or None
    db.commit()
    return RedirectResponse(url=f"/events/{event_id}?tab=pledges&flash_success=Event+updated", status_code=303)


# ── DELETE EVENT ───────────────────────────────────────────────────────────
@app.post("/events/{event_id}/delete")
async def delete_event_post(request: Request, event_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    event = db.query(Event).filter(Event.event_id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if form.get("confirm_name", "").strip() != (event.event_name or ""):
        return _err_redirect(event_id, "pledges", "deleteEventModal", "flash_error",
                              "Event name did not match. Deletion cancelled.")

    pledge_ids = [p.pledge_id for p in db.query(Pledge.pledge_id).filter(Pledge.event_id == event_id).all()]
    if pledge_ids:
        db.query(Payment).filter(Payment.pledge_id.in_(pledge_ids)).delete(synchronize_session=False)
        db.query(Pledge).filter(Pledge.event_id == event_id).delete(synchronize_session=False)
    db.delete(event)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


# ── CREATE PLEDGE (cash/labh AND in-kind — routed by pledge_type_group) ────
@app.post("/events/{event_id}/pledges/create")
async def create_pledge_post(request: Request, event_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    group    = form.get("pledge_type_group", "cash")
    donor_id = form.get("donor_id", "").strip()

    if group == "in_kind":
        item_name = form.get("item_name", "").strip()
        quantity  = form.get("quantity", "").strip()
        if not donor_id or not item_name or not quantity:
            return _err_redirect(event_id, "pledges", "addInKindPledgeModal", "inkind_error",
                                  "Donor, item name, and quantity are required.")
        category_map = {"donation": PledgeCategory.DONATION, "role": PledgeCategory.ROLE}
        pledge = Pledge(
            donor_id=int(donor_id), event_id=event_id,
            pledge_type=PledgeType.IN_KIND,
            pledge_category=category_map.get(form.get("pledge_category", "donation"), PledgeCategory.DONATION),
            item_name=item_name,
            item_category=form.get("item_category", "").strip() or None,
            quantity=float(quantity),
            unit=form.get("unit", "").strip() or None,
            market_value=float(form.get("market_value") or 0) or None,
            description=form.get("description", "").strip() or None,
            status=PledgeStatus.PENDING,
        )
    else:
        promised_amount = form.get("promised_amount", "").strip()
        if not donor_id or not promised_amount:
            return _err_redirect(event_id, "pledges", "addCashPledgeModal", "pledge_error",
                                  "Donor and promised amount are required.")
        type_map     = {"cash": PledgeType.CASH, "labh": PledgeType.LABH}
        category_map = {"donation": PledgeCategory.DONATION, "role": PledgeCategory.ROLE}
        pledge = Pledge(
            donor_id=int(donor_id), event_id=event_id,
            pledge_type=type_map.get(form.get("pledge_type", "cash"), PledgeType.CASH),
            pledge_category=category_map.get(form.get("pledge_category", "donation"), PledgeCategory.DONATION),
            promised_amount=float(promised_amount),
            description=form.get("description", "").strip() or None,
            status=PledgeStatus.PENDING,
        )

    db.add(pledge)
    db.commit()
    return RedirectResponse(url=f"/events/{event_id}?tab=pledges&flash_success=Pledge+added", status_code=303)


# ── EDIT PLEDGE (modal-based, no separate page) ─────────────────────────────
@app.post("/events/{event_id}/pledges/{pledge_id}/edit")
async def edit_pledge_post(request: Request, event_id: int, pledge_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    pledge = db.query(Pledge).filter(Pledge.pledge_id == pledge_id, Pledge.event_id == event_id).first()
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")

    if pledge.pledge_type == PledgeType.IN_KIND:
        pledge.item_name     = form.get("item_name", pledge.item_name).strip()
        pledge.item_category = form.get("item_category", "").strip() or None
        qty = form.get("quantity", "").strip()
        if qty:
            pledge.quantity = float(qty)
        pledge.unit = form.get("unit", "").strip() or None
        mv = form.get("market_value", "").strip()
        if mv:
            pledge.market_value = float(mv)
    else:
        amt = form.get("promised_amount", "").strip()
        if amt:
            pledge.promised_amount = float(amt)
        type_map = {"cash": PledgeType.CASH, "labh": PledgeType.LABH}
        if form.get("pledge_type") in type_map:
            pledge.pledge_type = type_map[form.get("pledge_type")]

    pledge.description = form.get("description", pledge.description)
    db.commit()
    return RedirectResponse(url=f"/events/{event_id}?tab=pledges&flash_success=Pledge+updated", status_code=303)


# ── RECORD PAYMENT (updates pledge status automatically) ───────────────────
@app.post("/events/{event_id}/payments/create")
async def create_payment_post(request: Request, event_id: int, db: Session = Depends(get_db)):
    form      = await request.form()
    pledge_id = form.get("pledge_id", "").strip()
    amount    = form.get("amount", "").strip()

    if not pledge_id or not amount:
        return _err_redirect(event_id, "pledges", "recordPaymentModal", "payment_error",
                              "Pledge and amount are required.")

    pledge = db.query(Pledge).filter(Pledge.pledge_id == int(pledge_id)).first()
    if not pledge:
        return _err_redirect(event_id, "pledges", "recordPaymentModal", "payment_error", "Pledge not found.")

    donor_name = None
    if pledge.donor_id:
        donor = db.query(Donor).filter(Donor.donor_id == pledge.donor_id).first()
        if donor:
            donor_name = f"{donor.first_name or ''} {donor.last_name or ''}".strip()

    mode_map = {"cash": PaymentMode.CASH, "upi": PaymentMode.UPI, "cheque": PaymentMode.CHEQUE, "neft": PaymentMode.NEFT}
    payment_date_str = form.get("payment_date", "").strip()
    payment_date = None
    if payment_date_str:
        try:
            payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            payment_date = None

    payment = Payment(
        pledge_id=pledge.pledge_id,
        donor_name=donor_name,
        amount=float(amount),
        payment_mode=mode_map.get(form.get("payment_mode", "cash"), PaymentMode.CASH),
        payment_ref=form.get("payment_ref", "").strip() or None,
        receipt_no=form.get("receipt_no", "").strip() or None,
        description=form.get("description", "").strip() or None,
        recorded_by=form.get("recorded_by", "").strip() or None,
        payment_date=payment_date or datetime.now(timezone.utc),
    )
    db.add(payment)
    db.flush()

    total_received = float(db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.pledge_id == pledge.pledge_id).scalar())
    target = float(pledge.promised_amount or pledge.market_value or 0)

    if target > 0 and total_received >= target:
        pledge.status = PledgeStatus.COMPLETED
    elif total_received > 0:
        pledge.status = PledgeStatus.PARTIAL
    else:
        pledge.status = PledgeStatus.PENDING

    db.commit()
    return RedirectResponse(url=f"/events/{event_id}?tab=payments&flash_success=Payment+recorded", status_code=303)


# ── ASSIGN ROLE ──────────────────────────────────────────────────────────────
@app.post("/events/{event_id}/roles/create")
async def create_role_post(request: Request, event_id: int, db: Session = Depends(get_db)):
    form      = await request.form()
    role_name = form.get("role_name", "").strip()
    donor_id  = form.get("donor_id", "").strip()

    if not role_name or not donor_id:
        return _err_redirect(event_id, "roles", "assignRoleModal", "role_error",
                              "Role name and donor are required.")

    target_amount = form.get("target_amount", "").strip()
    role = Pledge(
        donor_id=int(donor_id), event_id=event_id,
        pledge_type=PledgeType.CASH, pledge_category=PledgeCategory.ROLE,
        item_name=role_name,
        promised_amount=float(target_amount) if target_amount else None,
        description=form.get("description", "").strip() or None,
        status=PledgeStatus.PENDING,
    )
    db.add(role)
    db.commit()
    return RedirectResponse(url=f"/events/{event_id}?tab=roles&flash_success=Role+assigned", status_code=303)


# ── EDIT ROLE (modal-based) ──────────────────────────────────────────────────
@app.post("/events/{event_id}/roles/{role_id}/edit")
async def edit_role_post(request: Request, event_id: int, role_id: int, db: Session = Depends(get_db)):
    form = await request.form()
    role = db.query(Pledge).filter(
        Pledge.pledge_id == role_id,
        Pledge.event_id == event_id,
        Pledge.pledge_category == PledgeCategory.ROLE
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    role.item_name = form.get("role_name", role.item_name).strip()
    target_amount = form.get("target_amount", "").strip()
    if target_amount:
        role.promised_amount = float(target_amount)
    donor_id = form.get("donor_id", "").strip()
    if donor_id:
        role.donor_id = int(donor_id)
    role.description = form.get("description", role.description)
    db.commit()
    return RedirectResponse(url=f"/events/{event_id}?tab=roles&flash_success=Role+updated", status_code=303)


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