from fastapi import APIRouter, HTTPException
from models.schema import DiagnosisEntry
from firebase_config import db
from datetime import datetime
import pytz

router = APIRouter(prefix="/diagnoses", tags=["Diagnoses"])
egypt_tz = pytz.timezone("Africa/Cairo")


# ---------------------- Add Diagnosis ----------------------
@router.post("/{national_id}")
def add_diagnosis(national_id: str, entry: DiagnosisEntry):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    doc_id = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    data = entry.dict()
    data["diagnosis_date"] = entry.diagnosis_date.strftime("%Y-%m-%d")
    data["timestamp"] = doc_id
    data["id"] = doc_id
    data["user_id"] = national_id

    user_ref.collection("diagnoses").document(doc_id).set(data)
    return {"message": "Diagnosis added", "doc_id": doc_id}


# ---------------------- Get Diagnoses ----------------------
@router.get("/{national_id}")
def get_diagnoses(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    diagnoses_ref = user_ref.collection("diagnoses")
    docs = diagnoses_ref.stream()
    diagnoses = [doc.to_dict() for doc in docs]
    return diagnoses


# ---------------------- Update Diagnosis ----------------------
@router.put("/{national_id}/{record_id}")
def update_diagnosis(national_id: str, record_id: str, entry: DiagnosisEntry):
    user_ref = db.collection("Users").document(national_id)
    record_ref = user_ref.collection("diagnoses").document(record_id)

    if not record_ref.get().exists:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    data = entry.dict()
    data["diagnosis_date"] = entry.diagnosis_date.strftime("%Y-%m-%d")
    data["timestamp"] = record_id
    data["id"] = record_id
    data["user_id"] = national_id

    record_ref.set(data)
    return {"message": "Diagnosis updated", "record_id": record_id}


# ---------------------- Delete Diagnosis ----------------------
@router.delete("/{national_id}/{record_id}")
def delete_diagnosis(national_id: str, record_id: str, added_by: str):
    user_ref = db.collection("Users").document(national_id)
    record_ref = user_ref.collection("diagnoses").document(record_id)
    doc = record_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Diagnosis not found")

    if doc.to_dict().get("added_by") != added_by:
        raise HTTPException(status_code=403, detail="You are not authorized to delete this diagnosis.")

    record_ref.delete()
    return {"message": "Diagnosis deleted", "record_id": record_id}
