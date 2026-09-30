from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Centre, CentreTest, DiagnosticTest
from app.schemas import (
    CentreCreate,
    CentreDetail,
    CentreOut,
    CentreTestCreate,
    CentreTestOut,
    DiagnosticTestCreate,
    DiagnosticTestOut,
)
from app.security import get_admin_user

router = APIRouter(tags=["Centres & Tests"])


@router.get("/centres", response_model=list[CentreOut])
def list_centres(
    location: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Centre)
    if location:
        query = query.filter(Centre.location.ilike(f"%{location}%"))
    return query.order_by(Centre.id).offset(skip).limit(limit).all()


@router.get("/centres/{centre_id}", response_model=CentreDetail)
def get_centre(centre_id: int, db: Session = Depends(get_db)):
    centre = (
        db.query(Centre)
        .options(joinedload(Centre.tests).joinedload(CentreTest.test))
        .filter(Centre.id == centre_id)
        .first()
    )
    if not centre:
        raise HTTPException(status_code=404, detail="Centre not found")
    return centre


@router.post(
    "/centres",
    response_model=CentreOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_admin_user)],
)
def create_centre(data: CentreCreate, db: Session = Depends(get_db)):
    centre = Centre(name=data.name.strip(), location=data.location.strip())
    db.add(centre)
    db.commit()
    db.refresh(centre)
    return centre


@router.post(
    "/centres/{centre_id}/tests",
    response_model=CentreTestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_admin_user)],
)
def add_test_to_centre(centre_id: int, data: CentreTestCreate, db: Session = Depends(get_db)):
    if not db.get(Centre, centre_id):
        raise HTTPException(status_code=404, detail="Centre not found")
    if not db.get(DiagnosticTest, data.test_id):
        raise HTTPException(status_code=404, detail="Test not found")

    existing = db.query(CentreTest).filter_by(centre_id=centre_id, test_id=data.test_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="This test is already added to the centre")

    centre_test = CentreTest(centre_id=centre_id, test_id=data.test_id, price=data.price)
    db.add(centre_test)
    db.commit()
    db.refresh(centre_test)
    return centre_test


@router.get("/tests", response_model=list[DiagnosticTestOut])
def list_tests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return db.query(DiagnosticTest).order_by(DiagnosticTest.id).offset(skip).limit(limit).all()


@router.post(
    "/tests",
    response_model=DiagnosticTestOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_admin_user)],
)
def create_test(data: DiagnosticTestCreate, db: Session = Depends(get_db)):
    name = data.name.strip()
    if db.query(DiagnosticTest).filter(DiagnosticTest.name.ilike(name)).first():
        raise HTTPException(status_code=409, detail="A test with this name already exists")

    test = DiagnosticTest(name=name, description=data.description)
    db.add(test)
    db.commit()
    db.refresh(test)
    return test
