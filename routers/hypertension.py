from fastapi import APIRouter, HTTPException, Request
from models.schema import HypertensionEntry
from firebase_config import db
from datetime import datetime
import pytz

egypt_tz = pytz.timezone("Africa/Cairo")
router = APIRouter(prefix="/hypertension", tags=["Hypertension"])


@router.post("/{national_id}")
def add_bp(national_id: str, entry: HypertensionEntry):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    timestamp_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")

    pulse_pressure = entry.sys_value - entry.dia_value

    data = {
        "sys_value": entry.sys_value,
        "dia_value": entry.dia_value,
        "pulse_pressure": pulse_pressure,
        "added_by": entry.added_by,
        "timestamp": timestamp_id
    }

    user_ref.collection("ClinicalIndicators") \
        .document("Hypertension") \
        .collection("Records") \
        .document(timestamp_id) \
        .set(data)

    return {"message": "Blood pressure record added", "id": timestamp_id}


@router.get("/{national_id}")
def get_bp(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("ClinicalIndicators") \
        .document("Hypertension") \
        .collection("Records").stream()

    return [{**doc.to_dict(), "id": doc.id} for doc in docs]


@router.put("/{national_id}/{record_id}")
def update_bp(national_id: str, record_id: str, entry: HypertensionEntry):
    record_ref = db.collection("Users") \
        .document(national_id) \
        .collection("ClinicalIndicators") \
        .document("Hypertension") \
        .collection("Records") \
        .document(record_id)

    doc = record_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    existing = doc.to_dict()
    if existing.get("added_by") != entry.added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to update this record")

    pulse_pressure = entry.sys_value - entry.dia_value

    record_ref.update({
        "sys_value": entry.sys_value,
        "dia_value": entry.dia_value,
        "pulse_pressure": pulse_pressure
    })

    return {"message": "Blood pressure record updated", "id": record_id}


@router.delete("/{national_id}/{record_id}")
def delete_bp(national_id: str, record_id: str, request: Request):
    added_by = request.query_params.get("added_by")

    record_ref = db.collection("Users") \
        .document(national_id) \
        .collection("ClinicalIndicators") \
        .document("Hypertension") \
        .collection("Records") \
        .document(record_id)

    doc = record_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Record not found")

    if doc.to_dict().get("added_by") != added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this record")

    record_ref.delete()
    return {"message": "Record deleted", "id": record_id}
