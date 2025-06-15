from fastapi import APIRouter, HTTPException, Request
from models.schema import FamilyHistoryEntry
from firebase_config import db
from datetime import datetime
import pytz

router = APIRouter(prefix="/family-history", tags=["Family History"])
egypt_tz = pytz.timezone("Africa/Cairo")


# ---------------------- Add Family History ----------------------
@router.post("/{national_id}")
def add_family_history(national_id: str, entry: FamilyHistoryEntry):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    record_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    data = entry.dict()
    data["id"] = record_id
    data["user_id"] = national_id
    data["timestamp"] = record_id

    user_ref.collection("family_history").document(record_id).set(data)
    return {"message": "Family history entry added", "record_id": record_id}


# ---------------------- Get All Family History ----------------------
@router.get("/{national_id}")
def get_family_history(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("family_history").stream()
    return [doc.to_dict() for doc in docs]


# ---------------------- Update Family History ----------------------
@router.put("/{national_id}/{record_id}")
def update_family_history(national_id: str, record_id: str, entry: FamilyHistoryEntry):
    record_ref = db.collection("Users") \
        .document(national_id) \
        .collection("family_history") \
        .document(record_id)

    doc = record_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    if doc.to_dict().get("added_by") != entry.added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to update this record.")

    data = entry.dict()
    data["id"] = record_id
    data["user_id"] = national_id
    data["timestamp"] = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

    record_ref.set(data)
    return {"message": "Family history entry updated", "record_id": record_id}


# ---------------------- Delete Family History ----------------------
@router.delete("/{national_id}/{record_id}")
def delete_family_history(national_id: str, record_id: str, request: Request):
    added_by = request.query_params.get("added_by")
    if not added_by:
        raise HTTPException(status_code=400, detail="Missing 'added_by' for permission check.")

    record_ref = db.collection("Users").document(national_id).collection("family_history").document(record_id)
    doc = record_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    if doc.to_dict().get("added_by") != added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this record.")

    record_ref.delete()
    return {"message": "Family history entry deleted", "record_id": record_id}
