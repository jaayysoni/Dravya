from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Donor, Family
from app.schemas import DonorCreate, DonorUpdate, DonorOut

router = APIRouter(prefix="/donors", tags=["Donors"])


# CREATE
@router.post("/", response_model=DonorOut, status_code=status.HTTP_201_CREATED)
def create_donor(payload: DonorCreate, db: Session = Depends(get_db)):
    if payload.family_id:
        family = db.query(Family).filter(Family.family_id == payload.family_id).first()
        if not family:
            raise HTTPException(status_code=404, detail="Family not found")

    donor = Donor(**payload.model_dump())
    db.add(donor)
    db.commit()
    db.refresh(donor)
    return donor


# GET ALL
@router.get("/", response_model=list[DonorOut])
def get_donors(db: Session = Depends(get_db)):
    return db.query(Donor).all()


# GET ONE
@router.get("/{donor_id}", response_model=DonorOut)
def get_donor(donor_id: int, db: Session = Depends(get_db)):
    donor = db.query(Donor).filter(Donor.donor_id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    return donor


# UPDATE
@router.put("/{donor_id}", response_model=DonorOut)
def update_donor(donor_id: int, payload: DonorUpdate, db: Session = Depends(get_db)):
    donor = db.query(Donor).filter(Donor.donor_id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(donor, key, value)

    db.commit()
    db.refresh(donor)
    return donor


# DELETE
@router.delete("/{donor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_donor(donor_id: int, db: Session = Depends(get_db)):
    donor = db.query(Donor).filter(Donor.donor_id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")

    db.delete(donor)
    db.commit()