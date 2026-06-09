from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Family
from app.schemas import FamilyCreate, FamilyUpdate, FamilyOut

router = APIRouter(prefix="/families", tags=["Families"])


# CREATE
@router.post("/", response_model=FamilyOut, status_code=status.HTTP_201_CREATED)
def create_family(payload: FamilyCreate, db: Session = Depends(get_db)):
    family = Family(**payload.model_dump())
    db.add(family)
    db.commit()
    db.refresh(family)
    return family


# GET ALL
@router.get("/", response_model=list[FamilyOut])
def get_families(db: Session = Depends(get_db)):
    return db.query(Family).all()


# GET ONE
@router.get("/{family_id}", response_model=FamilyOut)
def get_family(family_id: int, db: Session = Depends(get_db)):
    family = db.query(Family).filter(Family.family_id == family_id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    return family


# UPDATE
@router.put("/{family_id}", response_model=FamilyOut)
def update_family(family_id: int, payload: FamilyUpdate, db: Session = Depends(get_db)):
    family = db.query(Family).filter(Family.family_id == family_id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(family, key, value)

    db.commit()
    db.refresh(family)
    return family


# DELETE
@router.delete("/{family_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_family(family_id: int, db: Session = Depends(get_db)):
    family = db.query(Family).filter(Family.family_id == family_id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    db.delete(family)
    db.commit()