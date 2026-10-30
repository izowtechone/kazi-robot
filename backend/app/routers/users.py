from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User
from ..schemas import UserCreate, UserUpdate, UserOut
from ..security import hash_password
from ..deps import require

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(require("admin"))):
    return db.query(User).order_by(User.id).all()

@router.post("", response_model=UserOut, status_code=201)
def create(body: UserCreate, db: Session = Depends(get_db), _=Depends(require("admin"))):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email already exists")
    u = User(email=body.email.lower(), full_name=body.full_name, role=body.role, hashed_password=hash_password(body.password))
    db.add(u); db.commit()
    return u

@router.patch("/{uid}", response_model=UserOut)
def update_user(uid: int, body: UserUpdate, db: Session = Depends(get_db), me: User = Depends(require("admin"))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    if u.id == me.id and (body.role not in (None, "admin") or body.is_active is False):
        raise HTTPException(400, "You cannot demote or deactivate yourself")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "password":
            u.hashed_password = hash_password(v)
        else:
            setattr(u, k, v)
    db.commit()
    return u

@router.delete("/{uid}", status_code=204)
def delete(uid: int, db: Session = Depends(get_db), me: User = Depends(require("admin"))):
    if uid == me.id:
        raise HTTPException(400, "You cannot delete yourself")
    u = db.get(User, uid)
    if u:
        db.delete(u); db.commit()
