from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Event, Donor, Pledge, Payment
from datetime import datetime, timezone

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    events = db.query(Event).all()
    total_donors = db.query(Donor).count()
    now = datetime.now(timezone.utc)

    events_data = []
    for event in events:
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

        total_promised = db.query(
            func.coalesce(func.sum(Pledge.promised_amount), 0)
        ).filter(Pledge.event_id == event.event_id).scalar()

        total_received = db.query(
            func.coalesce(func.sum(Payment.amount), 0)
        ).join(Pledge, Payment.pledge_id == Pledge.pledge_id)\
         .filter(Pledge.event_id == event.event_id).scalar()

        event_donors = db.query(
            func.count(func.distinct(Pledge.donor_id))
        ).filter(Pledge.event_id == event.event_id).scalar()

        events_data.append({
            "event_id": event.event_id,
            "event_name": event.event_name,
            "category": event.category,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "status": status,
            "total_promised": float(total_promised),
            "total_received": float(total_received),
            "total_donors": event_donors,
        })

    active_events = sum(1 for e in events_data if e["status"] == "active")
    total_received_all = sum(e["total_received"] for e in events_data)
    total_pending_all = sum(
        e["total_promised"] - e["total_received"] for e in events_data
    )

    return {
        "summary": {
            "active_events": active_events,
            "total_received": total_received_all,
            "total_pending": total_pending_all,
            "total_donors": total_donors,
        },
        "events": events_data,
    }