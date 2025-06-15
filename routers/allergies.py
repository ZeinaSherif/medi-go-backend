from fastapi import APIRouter, HTTPException, Request
from models.schema import Allergy
from datetime import datetime
from firebase_config import db
import pytz

router = APIRouter(prefix="/allergies", tags=["Allergies"])
egypt_tz = pytz.timezone("Africa/Cairo")

@router.post("/{national_id}")
def add_allergy(national_id: str, entry: Allergy):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    timestamp_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

    data = entry.dict()
    data["date"] = timestamp_id

    # Use allergen_name as document ID to overwrite duplicates, or change to unique ID if needed
    doc_id = entry.allergen_name

    user_ref \
        .collection("ClinicalIndicators") \
        .document("allergies") \
        .collection("Records") \
        .document(doc_id) \
        .set(data)

    return {"message": "Allergy added", "id": doc_id}


@router.get("/{national_id}")
def get_allergies(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref \
        .collection("ClinicalIndicators") \
        .document("allergies") \
        .collection("Records") \
        .stream()

    return [{**doc.to_dict(), "id": doc.id} for doc in docs]


@router.put("/{national_id}/{record_id}")
def update_allergy(national_id: str, record_id: str, entry: Allergy):
    allergy_ref = db.collection("Users") \
        .document(national_id) \
        .collection("ClinicalIndicators") \
        .document("allergies") \
        .collection("Records") \
        .document(record_id)

    doc = allergy_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    existing_added_by = doc.to_dict().get("added_by")
    if existing_added_by != entry.added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to update this record")

    updated_data = entry.dict()
    updated_data["date"] = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

    allergy_ref.update(updated_data)

    return {"message": "Allergy updated", "id": record_id}


@router.delete("/{national_id}/{record_id}")
def delete_allergy(national_id: str, record_id: str, request: Request):
    added_by = request.query_params.get("added_by")
    if not added_by:
        raise HTTPException(status_code=400, detail="Missing added_by for permission check")

    allergy_ref = db.collection("Users") \
        .document(national_id) \
        .collection("ClinicalIndicators") \
        .document("allergies") \
        .collection("Records") \
        .document(record_id)

    doc = allergy_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    if doc.to_dict().get("added_by") != added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this record")

    allergy_ref.delete()
    return {"message": "Allergy deleted", "id": record_id}
