from fastapi import APIRouter, HTTPException
from models.schema import SurgeryEntry
from firebase_config import db
from datetime import datetime, date as dt_date
import pytz

router = APIRouter(prefix="/surgeries", tags=["Surgeries"])
egypt_tz = pytz.timezone("Africa/Cairo")


# ---------------------- Add Surgery ----------------------
@router.post("/{national_id}")
def add_surgery(national_id: str, entry: SurgeryEntry):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    record_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    data = entry.dict()

    if isinstance(data["surgery_date"], dt_date):
        data["surgery_date"] = datetime.combine(data["surgery_date"], datetime.min.time())

    data["id"] = record_id
    data["user_id"] = national_id
    data["timestamp"] = record_id

    user_ref.collection("surgeries").document(record_id).set(data)
    return {"message": "Surgery entry added", "record_id": record_id}


# ---------------------- Get All Surgeries ----------------------
@router.get("/{national_id}")
def get_surgeries(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("surgeries").stream()
    return [doc.to_dict() for doc in docs]


# ---------------------- Update Surgery ----------------------
@router.put("/{national_id}/{record_id}")
def update_surgery(national_id: str, record_id: str, entry: SurgeryEntry):
    user_ref = db.collection("Users").document(national_id)
    record_ref = user_ref.collection("surgeries").document(record_id)

    if not record_ref.get().exists:
        raise HTTPException(status_code=404, detail="Record not found")

    existing = record_ref.get().to_dict()
    if entry.added_by != existing.get("added_by"):
        raise HTTPException(status_code=403, detail="Unauthorized to update this surgery")

    data = entry.dict()
    if isinstance(data["surgery_date"], dt_date):
        data["surgery_date"] = datetime.combine(data["surgery_date"], datetime.min.time())

    data["id"] = record_id
    data["user_id"] = national_id
    data["timestamp"] = record_id

    record_ref.set(data)
    return {"message": "Surgery updated", "record_id": record_id}


# ---------------------- Delete Surgery ----------------------
@router.delete("/{national_id}/{record_id}")
def delete_surgery(national_id: str, record_id: str, added_by: str):
    user_ref = db.collection("Users").document(national_id)
    record_ref = user_ref.collection("surgeries").document(record_id)
    doc = record_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    if doc.to_dict().get("added_by") != added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this record.")

    record_ref.delete()
    return {"message": "Surgery entry deleted"}
