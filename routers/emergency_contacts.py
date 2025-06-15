from fastapi import APIRouter, HTTPException
from models.schema import EmergencyContact
from firebase_config import db
from datetime import datetime
import pytz

router = APIRouter(prefix="/emergency-contacts", tags=["Emergency Contacts"])
egypt_tz = pytz.timezone("Africa/Cairo")

# ---------------------- Add Emergency Contact ----------------------
@router.post("/{national_id}")
def add_contact(national_id: str, entry: EmergencyContact):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    record_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    data = entry.dict()
    data["id"] = record_id
    data["user_id"] = national_id
    data["timestamp"] = record_id

    user_ref.collection("emergency_contacts").document(record_id).set(data)
    return {"message": "Emergency contact added", "record_id": record_id}

# ---------------------- Get All Emergency Contacts ----------------------
@router.get("/{national_id}")
def get_contacts(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("emergency_contacts").stream()
    return [doc.to_dict() for doc in docs]

# ---------------------- Update Emergency Contact ----------------------
@router.put("/{national_id}/{record_id}")
def update_contact(national_id: str, record_id: str, entry: EmergencyContact):
    user_ref = db.collection("Users").document(national_id)
    record_ref = user_ref.collection("emergency_contacts").document(record_id)

    if not record_ref.get().exists:
        raise HTTPException(status_code=404, detail="Record not found")

    data = entry.dict()
    data["id"] = record_id
    data["user_id"] = national_id
    data["timestamp"] = record_id

    record_ref.set(data)
    return {"message": "Emergency contact updated", "record_id": record_id}

# ---------------------- Delete Emergency Contact ----------------------
@router.delete("/{national_id}/{record_id}")
def delete_contact(national_id: str, record_id: str):
    user_ref = db.collection("Users").document(national_id)
    record_ref = user_ref.collection("emergency_contacts").document(record_id)

    if not record_ref.get().exists:
        raise HTTPException(status_code=404, detail="Record not found")

    record_ref.delete()
    return {"message": "Emergency contact deleted"}
