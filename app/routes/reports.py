from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from jinja2 import pass_context
from urllib.parse import urlencode
import csv
import io

from app.database import get_db
from app.models import (
    Event, Donor, Family, Pledge, Payment, User,
    PledgeCategory, PledgeType, PledgeStatus
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ── Template filters (this router has its own Jinja2Templates instance,
#    so filters/globals must be registered here too) ──────────────────────────

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


def format_datetime(value):
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        return value.strftime("%d %b %Y, %I:%M %p")
    except Exception:
        return "—"


@pass_context
def qs_with(context, key: str, value) -> str:
    """Build a querystring preserving all current params, overriding `key`.
    Uses @pass_context so templates can call qs_with('type','payment')
    without explicitly passing request."""
    request = context["request"]
    params = dict(request.query_params)
    params[key] = str(value)
    return urlencode(params)


@pass_context
def qs_without(context, key: str) -> str:
    """Build a querystring preserving all current params, dropping `key`."""
    request = context["request"]
    params = dict(request.query_params)
    params.pop(key, None)
    return urlencode(params)


templates.env.filters["format_amount"]   = format_amount
templates.env.filters["format_date"]     = format_date
templates.env.filters["format_datetime"] = format_datetime
templates.env.globals["qs_with"]         = qs_with
templates.env.globals["qs_without"]      = qs_without


def make_user():
    """Placeholder until auth is wired up — same as main.py."""
    return type("User", (), {"name": "Admin", "role": "admin", "user_id": None})()


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def end_of_day(dt):
    if not dt:
        return None
    return dt.replace(hour=23, minute=59, second=59)


# ── Build unified activity feed from existing tables ───────────────────────────

def build_activities(db: Session, type_filter=None, event_id=None,
                      from_date=None, to_date=None, q=None):
    activities = []

    # ── Payments ──
    if not type_filter or type_filter == "payment":
        query = db.query(Payment, Pledge, Event).join(
            Pledge, Payment.pledge_id == Pledge.pledge_id
        ).outerjoin(Event, Pledge.event_id == Event.event_id)

        if event_id:
            query = query.filter(Pledge.event_id == event_id)
        if from_date:
            query = query.filter(Payment.created_at >= from_date)
        if to_date:
            query = query.filter(Payment.created_at <= to_date)
        if q:
            query = query.filter(
                func.lower(Payment.donor_name).contains(q.lower()) |
                func.lower(Payment.receipt_no or "").contains(q.lower())
            )

        for payment, pledge, event in query.all():
            mode = payment.payment_mode.value if payment.payment_mode else "—"
            activities.append({
                "action_type":        "PAYMENT_ADDED",
                "created_at":         payment.created_at,
                "description":        f"Payment of ₹{payment.amount:,.0f} ({mode}) recorded for {payment.donor_name or 'donor'}"
                                       + (f" — Receipt #{payment.receipt_no}" if payment.receipt_no else ""),
                "amount":             float(payment.amount or 0),
                "event_id":           pledge.event_id,
                "event_name":         event.event_name if event else None,
                "performed_by_name":  payment.recorded_by or "—",
                "performed_by_role":  None,
            })

    # ── Pledges (donations) ──
    if not type_filter or type_filter == "pledge":
        query = db.query(Pledge, Donor, Event).outerjoin(
            Donor, Pledge.donor_id == Donor.donor_id
        ).outerjoin(Event, Pledge.event_id == Event.event_id).filter(
            Pledge.pledge_category == PledgeCategory.DONATION
        )

        if event_id:
            query = query.filter(Pledge.event_id == event_id)
        if from_date:
            query = query.filter(Pledge.created_at >= from_date)
        if to_date:
            query = query.filter(Pledge.created_at <= to_date)
        if q:
            query = query.filter(
                func.lower((Donor.first_name or "") + " " + (Donor.last_name or "")).contains(q.lower())
            )

        for pledge, donor, event in query.all():
            donor_name = "—"
            if donor:
                donor_name = "Anonymous" if donor.is_anonymous else f"{donor.first_name} {donor.last_name}".strip()
            activities.append({
                "action_type":        "PLEDGE_ADDED",
                "created_at":         pledge.created_at,
                "description":        f"Pledge of ₹{(pledge.promised_amount or 0):,.0f} added for {donor_name}"
                                       + (f" — {pledge.description}" if pledge.description else ""),
                "amount":             float(pledge.promised_amount or 0),
                "event_id":           pledge.event_id,
                "event_name":         event.event_name if event else None,
                "performed_by_name":  "—",
                "performed_by_role":  None,
            })

    # ── In-kind / goods pledges ──
    if not type_filter or type_filter == "goods":
        query = db.query(Pledge, Donor, Event).outerjoin(
            Donor, Pledge.donor_id == Donor.donor_id
        ).outerjoin(Event, Pledge.event_id == Event.event_id).filter(
            Pledge.pledge_type == PledgeType.IN_KIND
        )

        if event_id:
            query = query.filter(Pledge.event_id == event_id)
        if from_date:
            query = query.filter(Pledge.created_at >= from_date)
        if to_date:
            query = query.filter(Pledge.created_at <= to_date)

        for pledge, donor, event in query.all():
            donor_name = "—"
            if donor:
                donor_name = "Anonymous" if donor.is_anonymous else f"{donor.first_name} {donor.last_name}".strip()
            qty = f"{pledge.quantity} {pledge.unit or ''}".strip()
            activities.append({
                "action_type":        "GOODS_RECEIVED",
                "created_at":         pledge.created_at,
                "description":        f"{qty} of {pledge.item_name or 'goods'} pledged by {donor_name}"
                                       + (f" (₹{pledge.market_value:,.0f} value)" if pledge.market_value else ""),
                "amount":             float(pledge.market_value or 0),
                "event_id":           pledge.event_id,
                "event_name":         event.event_name if event else None,
                "performed_by_name":  "—",
                "performed_by_role":  None,
            })

    # ── Roles added ──
    if not type_filter or type_filter == "role":
        query = db.query(Pledge, Event).outerjoin(
            Event, Pledge.event_id == Event.event_id
        ).filter(Pledge.pledge_category == PledgeCategory.ROLE)

        if event_id:
            query = query.filter(Pledge.event_id == event_id)
        if from_date:
            query = query.filter(Pledge.created_at >= from_date)
        if to_date:
            query = query.filter(Pledge.created_at <= to_date)
        if q:
            query = query.filter(func.lower(Pledge.item_name or "").contains(q.lower()))

        for pledge, event in query.all():
            activities.append({
                "action_type":        "ROLE_ADDED",
                "created_at":         pledge.created_at,
                "description":        f"Role '{pledge.item_name}' added"
                                       + (f" — target ₹{pledge.promised_amount:,.0f}" if pledge.promised_amount else ""),
                "amount":             float(pledge.promised_amount or 0) if pledge.promised_amount else None,
                "event_id":           pledge.event_id,
                "event_name":         event.event_name if event else None,
                "performed_by_name":  "—",
                "performed_by_role":  None,
            })

    # ── Donors added ──
    if not type_filter or type_filter == "donor":
        query = db.query(Donor)
        if from_date:
            query = query.filter(Donor.created_at >= from_date)
        if to_date:
            query = query.filter(Donor.created_at <= to_date)
        if q:
            query = query.filter(
                func.lower(Donor.first_name + " " + Donor.last_name).contains(q.lower())
            )
        if not event_id:
            for donor in query.all():
                name = "Anonymous donor" if donor.is_anonymous else f"{donor.first_name} {donor.last_name}".strip()
                activities.append({
                    "action_type":        "DONOR_ADDED",
                    "created_at":         donor.created_at,
                    "description":        f"Donor '{name}' added to the system"
                                           + (f" — {donor.mobile}" if donor.mobile else ""),
                    "amount":             None,
                    "event_id":           None,
                    "event_name":         None,
                    "performed_by_name":  "—",
                    "performed_by_role":  None,
                })

    # ── Families added ──
    if not type_filter or type_filter == "family":
        query = db.query(Family)
        if from_date:
            query = query.filter(Family.created_at >= from_date)
        if to_date:
            query = query.filter(Family.created_at <= to_date)
        if q:
            query = query.filter(func.lower(Family.family_name).contains(q.lower()))
        if not event_id:
            for family in query.all():
                activities.append({
                    "action_type":        "FAMILY_ADDED",
                    "created_at":         family.created_at,
                    "description":        f"Family '{family.family_name}' added"
                                           + (f" — {family.family_members_count} members" if family.family_members_count else ""),
                    "amount":             None,
                    "event_id":           None,
                    "event_name":         None,
                    "performed_by_name":  "—",
                    "performed_by_role":  None,
                })

    # ── Events created ──
    if not type_filter or type_filter == "event":
        query = db.query(Event)
        if event_id:
            query = query.filter(Event.event_id == event_id)
        if from_date:
            query = query.filter(Event.created_at >= from_date)
        if to_date:
            query = query.filter(Event.created_at <= to_date)
        if q:
            query = query.filter(func.lower(Event.event_name).contains(q.lower()))
        for event in query.all():
            activities.append({
                "action_type":        "EVENT_CREATED",
                "created_at":         event.created_at,
                "description":        f"Event '{event.event_name}' created ({event.category or 'Uncategorized'})",
                "amount":             None,
                "event_id":           event.event_id,
                "event_name":         event.event_name,
                "performed_by_name":  "—",
                "performed_by_role":  None,
            })

    # ── User actions ──
    # NOTE: queried with explicit columns only — the User model currently
    # defines first_name/last_name but the real `users` table doesn't have
    # those columns yet, so db.query(User) would crash. Fix the model or
    # run a migration to add those columns, then this can go back to
    # db.query(User) if you want full user objects.
    if not type_filter or type_filter == "user":
        query = db.query(
            User.user_id, User.username, User.role, User.created_at
        )
        if from_date:
            query = query.filter(User.created_at >= from_date)
        if to_date:
            query = query.filter(User.created_at <= to_date)
        if not event_id:
            for user in query.all():
                activities.append({
                    "action_type":        "USER_CREATED",
                    "created_at":         user.created_at,
                    "description":        f"User '{user.username}' created with role '{user.role}'",
                    "amount":             None,
                    "event_id":           None,
                    "event_name":         None,
                    "performed_by_name":  "—",
                    "performed_by_role":  user.role,
                })

    activities.sort(key=lambda a: a["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return activities


def compute_summary(activities):
    payments = [a for a in activities if a["action_type"] == "PAYMENT_ADDED"]
    pledges  = [a for a in activities if a["action_type"] == "PLEDGE_ADDED"]
    donors   = [a for a in activities if a["action_type"] == "DONOR_ADDED"]
    families = [a for a in activities if a["action_type"] == "FAMILY_ADDED"]
    events   = [a for a in activities if a["action_type"] == "EVENT_CREATED"]
    roles    = [a for a in activities if a["action_type"] == "ROLE_ADDED"]

    return {
        "total_activities":      len(activities),
        "total_payments":        len(payments),
        "total_payment_amount":  sum(a["amount"] or 0 for a in payments),
        "total_pledges":         len(pledges),
        "total_pledge_amount":   sum(a["amount"] or 0 for a in pledges),
        "total_donors_added":    len(donors),
        "total_families_added":  len(families),
        "total_events_added":    len(events),
        "total_roles_added":     len(roles),
    }


# ── Page route ───────────────────────────────────────────────────────────────

@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    type: str = None,
    event_id: int = None,
    from_date: str = None,
    to_date: str = None,
    user_id: int = None,
    q: str = None,
    page: int = 1,
    db: Session = Depends(get_db)
):
    fd = parse_date(from_date)
    td = end_of_day(parse_date(to_date))

    activities = build_activities(
        db, type_filter=type, event_id=event_id,
        from_date=fd, to_date=td, q=q
    )

    summary = compute_summary(activities)

    page_size = 25
    total = len(activities)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    paged_activities = activities[start:end]

    pagination = {
        "page": page,
        "total": total,
        "start": start + 1 if total else 0,
        "end": end,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "pages": list(range(1, total_pages + 1)),
    }

    all_events = db.query(Event).order_by(Event.event_name).all()
    all_users = db.query(
        User.user_id, User.username, User.role
    ).order_by(User.username).all()
    all_donors = db.query(Donor).order_by(Donor.first_name).all()

    return templates.TemplateResponse(request, "report.html", {
        "current_user":  make_user(),
        "activities":    paged_activities,
        "summary":       summary,
        "pagination":    pagination,
        "all_events":    all_events,
        "all_users":     all_users,
        "all_donors":    all_donors,
    })


# ── Export route ─────────────────────────────────────────────────────────────

@router.get("/reports/export")
def export_report(
    request: Request,
    scope: str = "all",
    export_event_id: int = None,
    export_type: str = None,
    export_from_date: str = None,
    export_to_date: str = None,
    export_donor_id: int = None,
    format: str = "csv",
    db: Session = Depends(get_db)
):
    user = make_user()
    if user.role not in ("admin", "manager"):
        return HTMLResponse("Forbidden — export requires admin or manager role.", status_code=403)

    event_id  = export_event_id if scope == "event" else None
    type_filter = export_type if scope == "type" else None
    fd = parse_date(export_from_date) if scope == "date_range" else None
    td = end_of_day(parse_date(export_to_date)) if scope == "date_range" else None

    activities = build_activities(
        db, type_filter=type_filter, event_id=event_id,
        from_date=fd, to_date=td
    )

    if scope == "donor" and export_donor_id:
        donor = db.query(Donor).filter(Donor.donor_id == export_donor_id).first()
        if donor:
            donor_name = f"{donor.first_name} {donor.last_name}".strip()
            activities = [a for a in activities if donor_name.lower() in a["description"].lower()]

    filename_base = f"dravya_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Date & Time", "Type", "Description", "Event", "Amount", "Performed By"])
        for a in activities:
            writer.writerow([
                a["created_at"].strftime("%d %b %Y %H:%M") if a["created_at"] else "",
                a["action_type"],
                a["description"],
                a["event_name"] or "",
                a["amount"] if a["amount"] is not None else "",
                a["performed_by_name"] or "",
            ])
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"}
        )

    elif format == "xlsx":
        try:
            from openpyxl import Workbook
        except ImportError:
            return HTMLResponse(
                "Excel export needs openpyxl. Run: pip install openpyxl && pip freeze > requirements.txt",
                status_code=500
            )
        wb = Workbook()
        ws = wb.active
        ws.title = "Activity Report"
        ws.append(["Date & Time", "Type", "Description", "Event", "Amount", "Performed By"])
        for a in activities:
            ws.append([
                a["created_at"].strftime("%d %b %Y %H:%M") if a["created_at"] else "",
                a["action_type"],
                a["description"],
                a["event_name"] or "",
                a["amount"] if a["amount"] is not None else "",
                a["performed_by_name"] or "",
            ])
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"}
        )

    elif format == "pdf":
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
        except ImportError:
            return HTMLResponse(
                "PDF export needs reportlab. Run: pip install reportlab && pip freeze > requirements.txt",
                status_code=500
            )
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
        styles = getSampleStyleSheet()
        elements = [Paragraph("Dravya — Activity Report", styles["Title"])]

        data = [["Date", "Type", "Description", "Event", "Amount", "By"]]
        for a in activities:
            data.append([
                a["created_at"].strftime("%d %b %Y") if a["created_at"] else "",
                a["action_type"].replace("_", " ").title(),
                (a["description"] or "")[:60],
                a["event_name"] or "—",
                f"₹{a['amount']:,.0f}" if a["amount"] else "—",
                a["performed_by_name"] or "—",
            ])

        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c2710c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#f0d9b5")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fffbf2")]),
        ]))
        elements.append(table)
        doc.build(elements)
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"}
        )

    return HTMLResponse("Unsupported format.", status_code=400)