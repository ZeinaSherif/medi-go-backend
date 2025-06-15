# translate.py
from fastapi import APIRouter, HTTPException
from firebase_admin import firestore
from .translations import translations  # ✅ relative import


router = APIRouter(tags=["Translations"])
db = firestore.client()
@router.post("/translations/upload_all")
async def upload_all_translations():
    try:
        print("Uploading translations...")
        for locale, content in translations.items():
            print(f"Uploading {locale} with {len(content)} keys")
            db.collection("translations").document(locale).set(content, merge=True)
        return {"message": "All translations uploaded successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/translations/{locale}")
async def get_translations(locale: str):
    doc = db.collection("translations").document(locale).get()
    if doc.exists:
        return {"locale": locale, "translations": doc.to_dict()}
    raise HTTPException(status_code=404, detail=f"No translations for '{locale}'")
