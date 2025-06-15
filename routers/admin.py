from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
import random
import string
from models.schema import FacilityCreateRequest, Facility, DoctorsCreateRequest, Doctors
from firebase_config import db
from routers.user_role import ALLOWED_ROLES
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

router = APIRouter(prefix="", tags=["Admin"])

# Optional: Enable CORS for frontend access
origins = ["*"]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

@router.get("/facilities")
def search_facilities(name: str = Query("", alias="name"), id: str = Query("", alias="id")):
    facilities_ref = db.collection("Facilities").stream()
    results = []
    for doc in facilities_ref:
        data = doc.to_dict()
        if name.lower() in data.get("facility_name", "").lower() or id == data.get("facility_id"):
            data["id"] = doc.id
            results.append(data)
    return results

@router.get("/clinicians")
def search_doctors(name: str = Query("", alias="name"), id: str = Query("", alias="id")):
    doctors_ref = db.collection("Doctors").stream()
    results = []
    for doc in doctors_ref:
        data = doc.to_dict()
        if name.lower() in data.get("doctor_name", "").lower() or id == data.get("doctor_id"):
            data["id"] = doc.id
            results.append(data)
    return results

@router.post("/facility/{admin_id}")
def create_facility(admin_id: str, data: FacilityCreateRequest):
    if data.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    facility_id = ''.join(random.choices(string.digits, k=5))
    password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=6))
    access_scope = ALLOWED_ROLES[data.role]["access_scope"]

    facility_data = Facility(
        facility_id=facility_id,
        password=password,
        admin_id=admin_id,
        facility_name=data.facility_name,
        city=data.city,
        region=data.region,
        address=data.address,
        role=data.role,
        access_scope=access_scope,
        email=data.email,
        phone_number=data.phone_number,
    )

    doc_ref = db.collection("Facilities").document(data.facility_name)
    if doc_ref.get().exists:
        raise HTTPException(status_code=400, detail="Facility name already exists")

    doc_ref.set(facility_data.dict())
    return {"message": "Facility created successfully", "login_id": facility_id, "password": password}

@router.put("/facility/{facility_id}")
def update_facility(facility_id: str, updated_data: dict):
    doc_ref = db.collection("Facilities").document(facility_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Facility not found")
    doc_ref.update(updated_data)
    return {"message": "Facility updated successfully"}

@router.delete("/facility/{facility_id}")
def delete_facility(facility_id: str):
    doc_ref = db.collection("Facilities").document(facility_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Facility not found")
    doc_ref.delete()
    return {"message": "Facility deleted successfully"}

@router.post("/doctors/{admin_id}")
def create_doctor(admin_id: str, data: DoctorsCreateRequest):
    doctor_id = ''.join(random.choices(string.digits, k=5))
    password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=6))

    doctor_data = Doctors(
        doctor_id=doctor_id,
        password=password,
        admin_id=admin_id,
        doctor_name=data.doctor_name,
        specialization=data.specialization,
        city=data.city,
        region=data.region,
        address=data.address,
        email=data.email,
        phone_number=data.phone_number,
    )

    doc_ref = db.collection("Doctors").document(data.email)
    if doc_ref.get().exists:
        raise HTTPException(status_code=400, detail="Doctor already exists by email")

    # Save doctor
    doc_ref.set(doctor_data.dict())

    # Migrate fallback assignments to new doctor record
    assignments = db.collection("DoctorAssignments") \
        .where("doctor_email", "==", data.email).stream()

    migrated = []
    for doc in assignments:
        assignment_data = doc.to_dict()
        patient_id = assignment_data.get("patient_national_id")
        if not patient_id:
            continue

        user_ref = db.collection("Users").document(patient_id)
        user_doc = user_ref.get()
        full_name = user_doc.to_dict().get("full_name", "Unknown") if user_doc.exists else "Unknown"

        doc_ref.collection("AssignedPatients").document(patient_id).set({
            "patient_national_id": patient_id,
            "full_name": full_name,
            "assigned_at": datetime.now().isoformat()
        })

        db.collection("DoctorAssignments").document(doc.id).delete()
        migrated.append(patient_id)

    # ✅ Remove notifications after doctor is registered
    notif_ref = db.collection("AdminNotifications") \
        .document("unregistered_doctors") \
        .collection("Notifications")

    to_delete = notif_ref.where("doctor_email", "==", data.email).stream()
    deleted_notif_ids = []
    for notif in to_delete:
        notif.reference.delete()
        deleted_notif_ids.append(notif.id)

    return {
        "message": "Doctor created successfully",
        "login_id": doctor_id,
        "password": password,
        "migrated_patients": migrated,
        "migrated_count": len(migrated),
        "deleted_notifications": deleted_notif_ids
    }

@router.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: str, updated_data: dict):
    doc_ref = db.collection("Doctors").document(doctor_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Doctor not found")
    doc_ref.update(updated_data)
    return {"message": "Doctor updated successfully"}

@router.delete("/doctors/{doctor_id}")
def delete_doctor(doctor_id: str):
    doc_ref = db.collection("Doctors").document(doctor_id)
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="Doctor not found")
    doc_ref.delete()
    return {"message": "Doctor deleted successfully"}

@router.get("/notifications")
def get_admin_notifications():
    notif_ref = db.collection("AdminNotifications").document("unregistered_doctors") \
                  .collection("Notifications").order_by("timestamp", direction="DESCENDING").stream()

    notifications = []
    for doc in notif_ref:
        data = doc.to_dict()
        data["id"] = doc.id
        notifications.append(data)

    return {"notifications": notifications}
