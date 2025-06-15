from fastapi import APIRouter, HTTPException, Body
from firebase_config import db
from typing import Optional

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login")
def login(user_id: str = Body(...), password: Optional[str] = Body(None)):
    # === Admin login ===
    if user_id == "admin" and password == "admin":
        return {"role": "admin", "message": "Admin logged in"}

    # === Patient login by national ID ===
    elif len(user_id) == 14 and user_id.isdigit():
        user_ref = db.collection("Users").document(user_id)
        doc = user_ref.get()
        if doc.exists and doc.to_dict().get("password") == password:
            data = doc.to_dict()
            return {
                "role": "patient",
                "message": "Patient logged in",
                "doctoremail": data.get("doctoremail", ""),
                "full_name": data.get("full_name", "")
            }
        raise HTTPException(status_code=401, detail="Invalid patient credentials")

    # === Doctor login using doctor_id ===
    doctor_query = db.collection("Doctors").where("doctor_id", "==", user_id).limit(1).stream()
    doctor_doc = next(doctor_query, None)
    if doctor_doc:
        data = doctor_doc.to_dict()
        if data.get("password") == password:
            return {
                "role": "doctor",
                "message": "Doctor login successful",
                "doctor_id": data.get("doctor_id"),
                "doctor_name": data.get("doctor_name"),
                "email": data.get("email"),
                "region": data.get("region")
            }
        raise HTTPException(status_code=401, detail="Invalid doctor credentials")

    # === Facility login ===
    facility_query = db.collection("Facilities").where("facility_id", "==", user_id).limit(1).stream()
    facility_doc = next(facility_query, None)
    if facility_doc:
        data = facility_doc.to_dict()
        if data.get("password") == password:
            return {
                "role": "facility",
                "message": "Facility logged in",
                "facility_id": data.get("facility_id"),
                "facility_type": data.get("role"),
                "facility_name": data.get("facility_name")
            }

    raise HTTPException(status_code=401, detail="Invalid credentials")
