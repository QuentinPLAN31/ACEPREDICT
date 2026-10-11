"""Lance uniquement la synchro des pages SEO (création, résultats, IndexNow).
Usage : python -m scripts.sync_match_pages"""
from app.database import SessionLocal
from app.services.seo_pages import sync_match_pages


def main():
    db = SessionLocal()
    try:
        print(sync_match_pages(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
