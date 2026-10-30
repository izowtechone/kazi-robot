"""Run on backend start: creates first admin and the sample test source if missing."""
from .db import SessionLocal
from .models import User, Source
from .config import settings
from .security import hash_password

def main():
    db = SessionLocal()
    try:
        if not db.query(User).first() and settings.admin_email and settings.admin_password:
            db.add(User(email=settings.admin_email.lower(), full_name="Administrator",
                        hashed_password=hash_password(settings.admin_password), role="admin"))
            print("Created initial admin", settings.admin_email)
        if not db.query(Source).filter(Source.name == "Sample Test Feed").first():
            db.add(Source(name="Sample Test Feed", type="rss", url="http://backend:8000/api/sample-feed.xml",
                          country="Tanzania", enabled=False, reliability=90,
                          config={"note": "Built-in demo feed for testing. Enable to try the pipeline."}))
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    main()
