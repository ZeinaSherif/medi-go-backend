from fastapi import APIRouter, HTTPException
from models.schema import HeightWeightCreate
from firebase_config import db
from datetime import datetime
import pytz

router = APIRouter(prefix="/measurements", tags=["Measurements"])
egypt_tz = pytz.timezone("Africa/Cairo")

# ------------------ Add or Update Body Measurement (Height/Weight) ------------------

@router.post("/body/{national_id}")
def add_or_update_height_weight(national_id: str, entry: HeightWeightCreate):
    height = entry.height
    weight = entry.weight
    added_by = entry.added_by

    if not height or not weight:
        raise HTTPException(status_code=400, detail="Height and weight are required")

    bmi = round(weight / ((height / 100) ** 2), 2)
    user_ref = db.collection("Users").document(national_id)

    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    measurements_doc = user_ref.collection("ClinicalIndicators").document("measurements")
    existing_doc = measurements_doc.get()

    # If record exists, ensure only the creator can update it
    if existing_doc.exists:
        existing_data = existing_doc.to_dict()
        if existing_data.get("added_by") != added_by:
            raise HTTPException(status_code=403, detail="You are not authorized to update this record")

    # Save or overwrite
    data = {
        "height": height,
        "weight": weight,
        "bmi": bmi,
        "added_by": added_by,
        "date": datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    }

    measurements_doc.set(data)
    return {"message": "Body measurement saved", "bmi": bmi}


@router.get("/body/{national_id}")
def get_height_weight(national_id: str):
    doc = db.collection("Users").document(national_id).collection("ClinicalIndicators").document("measurements").get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Body measurements not found")
    return doc.to_dict()
