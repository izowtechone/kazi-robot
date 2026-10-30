from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User
from ..schemas import Login, UserOut
from ..security import verify_password, create_token
from ..deps import current_user
from ..limiter import limiter
from ..logs import record

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, body: Login, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email.lower()).first()
    if not u or not u.is_active or not verify_password(body.password, u.hashed_password):
        record(db, "WARNING", "login_failed", f"Failed login for {body.email} from {request.client.host if request.client else '?'}")
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_token(u.id, u.role), "token_type": "bearer", "user": UserOut.model_validate(u)}

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
