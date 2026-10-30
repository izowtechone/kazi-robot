from datetime import datetime, date
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, HttpUrl, ConfigDict

class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime | None

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(None, max_length=255)
    password: str = Field(min_length=10, max_length=200)
    role: Literal["admin", "editor", "viewer"] = "viewer"

class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    password: str | None = Field(None, min_length=10, max_length=200)
    role: Literal["admin", "editor", "viewer"] | None = None
    is_active: bool | None = None

class SourceIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    type: Literal["rss", "api", "html"]
    url: HttpUrl
    country: Literal["Tanzania", "Kenya", "Uganda", "Rwanda", "Burundi"] | None = None
    enabled: bool = True
    reliability: int = Field(80, ge=0, le=100)
    interval_minutes: int | None = Field(None, ge=5, le=10080)
    config: dict = {}

class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    url: str
    country: str | None
    enabled: bool
    reliability: int
    interval_minutes: int | None
    config: dict
    last_run_at: datetime | None
    last_status: str | None
    last_message: str | None
    consecutive_failures: int

class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_id: int | None
    title: str
    employer: str | None
    country: str | None
    location: str | None
    category: str | None
    description: str | None
    qualifications: str | None
    how_to_apply: str | None
    apply_url: str | None
    published_at: datetime | None
    deadline: date | None
    source_url: str
    status: str
    rejection_reasons: list
    wp_post_id: int | None
    wp_link: str | None
    publish_attempts: int
    last_error: str | None
    created_at: datetime | None

class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    level: str
    event: str
    message: str
    job_id: int | None
    source_id: int | None
    created_at: datetime | None
