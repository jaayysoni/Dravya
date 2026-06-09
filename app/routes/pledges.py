from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Pledge, Donor, Event
from app.schemas import PledgeCreate, PledgeUpdate, PledgeOut

router = APIRouter(prefix="/pledges", tags=["Pledges"])


# CREATE
@router.post("/", response_model=PledgeOut, status_code=status.HTTP_201_CREATED)
def create_pledge(payload: PledgeCreate, db: Session = Depends(get_db)):
    if payload.donor_id is not None:
        donor = db.query(Donor).filter(Donor.donor_id == payload.donor_id).first()
        if not donor:
            raise HTTPException(status_code=404, detail="Donor not found")

    if payload.event_id is not None:
        event = db.query(Event).filter(Event.event_id == payload.event_id).first()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

    pledge = Pledge(**payload.model_dump())
    db.add(pledge)
    db.commit()
    db.refresh(pledge)
    return pledge


# GET ALL
@router.get("/", response_model=list[PledgeOut])
def get_pledges(db: Session = Depends(get_db)):
    return db.query(Pledge).all()


# GET ONE
@router.get("/{pledge_id}", response_model=PledgeOut)
def get_pledge(pledge_id: int, db: Session = Depends(get_db)):
    pledge = db.query(Pledge).filter(Pledge.pledge_id == pledge_id).first()
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")
    return pledge


# UPDATE
@router.put("/{pledge_id}", response_model=PledgeOut)
def update_pledge(pledge_id: int, payload: PledgeUpdate, db: Session = Depends(get_db)):
    pledge = db.query(Pledge).filter(Pledge.pledge_id == pledge_id).first()
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pledge, key, value)

    db.commit()
    db.refresh(pledge)
    return pledge


# DELETE
@router.delete("/{pledge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pledge(pledge_id: int, db: Session = Depends(get_db)):
    pledge = db.query(Pledge).filter(Pledge.pledge_id == pledge_id).first()
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")

    db.delete(pledge)
    db.commit()