from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import Optional
from firebase_config import db
from models.schema import DoctorAssignment

router = APIRouter(prefix="/doctor-assignments", tags=["Doctor Assignments"])
@router.post("/")
def assign_doctor(assignment: DoctorAssignment):
    doc_id = f"{assignment.doctor_email}_{assignment.patient_national_id}"
    doctor_query = db.collection("Doctors").where("email", "==", assignment.doctor_email).limit(1).stream()
    doctor_doc = next(doctor_query, None)

    assigned_to = "admin"

    if doctor_doc:
        # ✅ Doctor exists → save in Doctors/{email}/AssignedPatients/
        assigned_to = assignment.doctor_email

        db.collection("Doctors").document(assignment.doctor_email) \
            .collection("AssignedPatients") \
            .document(assignment.patient_national_id).set({
                "patient_national_id": assignment.patient_national_id,
                "assigned_at": datetime.now().isoformat()
            })

        return {
            "assigned_to": assigned_to,
            "message": f"✅ Doctor {assignment.doctor_email} assigned to patient {assignment.patient_national_id} and saved under AssignedPatients"
        }

    else:
        # ❌ Doctor not registered → save fallback + notify admin
        db.collection("DoctorAssignments").document(doc_id).set({
            "doctor_email": assignment.doctor_email,
            "doctor_name": assignment.doctor_name,
            "patient_national_id": assignment.patient_national_id,
            "assigned_to": assigned_to,
            "status": "pending",
            "timestamp": datetime.now().isoformat()
        })

        db.collection("AdminNotifications").document("unregistered_doctors") \
            .collection("Notifications").document(doc_id).set({
                "patient_national_id": assignment.patient_national_id,
                "doctor_email": assignment.doctor_email,
                "message": f"Patient {assignment.patient_national_id} was assigned to unregistered doctor {assignment.doctor_email}",
                "timestamp": datetime.now().isoformat()
            })

        return {
            "assigned_to": assigned_to,
            "message": f"Unregistered doctor. Assignment saved to fallback.",
            "admin_alert": "Admin notified for unregistered doctor."
        }


def is_doctor_assigned(patient_national_id: str) -> Optional[str]:
    # First check fallback DoctorAssignments
    docs = db.collection("DoctorAssignments") \
        .where("patient_national_id", "==", patient_national_id) \
        .stream()
    for doc in docs:
        return doc.to_dict().get("doctor_email")

    # If not found, check all registered doctors
    doctors = db.collection("Doctors").stream()
    for doctor in doctors:
        doctor_email = doctor.id
        assigned_doc = db.collection("Doctors") \
            .document(doctor_email) \
            .collection("AssignedPatients") \
            .document(patient_national_id).get()
        if assigned_doc.exists:
            return doctor_email

    return None

@router.get("/check")
def check_doctor(patient_national_id: str):
    # First, check fallback DoctorAssignments
    docs = db.collection("DoctorAssignments") \
        .where("patient_national_id", "==", patient_national_id) \
        .stream()

    for doc in docs:
        fallback = doc.to_dict()
        return {
            "email": fallback.get("doctor_email"),
            "name": fallback.get("doctor_name", "Unknown")
        }

    # Second, check registered doctors' AssignedPatients
    doctors = db.collection("Doctors").stream()
    for doctor in doctors:
        doctor_email = doctor.id
        assigned_doc = db.collection("Doctors") \
            .document(doctor_email) \
            .collection("AssignedPatients") \
            .document(patient_national_id).get()

        if assigned_doc.exists:
            doctor_data = db.collection("Doctors").document(doctor_email).get().to_dict()
            return {
                "email": doctor_email,
                "name": doctor_data.get("doctor_name", "Unknown")
            }

    raise HTTPException(status_code=404, detail="No doctor assigned to this patient.")


def auto_assign_reviewer(patient_national_id: str) -> dict:
    user_ref = db.collection("Users").document(patient_national_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise ValueError("User not found")

    user_data = user_doc.to_dict()
    user_region = user_data.get("region", "").strip().lower()

    facility_query = db.collection("Facilities") \
        .where("region", "==", user_region) \
        .where("role", "==", "hospital") \
        .limit(1).stream()
    facility_doc = next(facility_query, None)
    if facility_doc:
        return {"assigned_to": facility_doc.id, "assigned_type": "facility"}

    doctor_query = db.collection("Doctors") \
        .where("region", "==", user_region).limit(1).stream()
    doctor_doc = next(doctor_query, None)
    if doctor_doc:
        return {"assigned_to": doctor_doc.id, "assigned_type": "doctor"}

    return {"assigned_to": "admin", "assigned_type": "admin"}

@router.get("/{doctor_email}/patients")
def get_patients_for_doctor(doctor_email: str):
    # Check in fallback DoctorAssignments
    assignments = db.collection("DoctorAssignments") \
        .where("doctor_email", "==", doctor_email).stream()
    
    patients = [doc.to_dict() for doc in assignments]

    # Check in registered doctor subcollection
    doctor_ref = db.collection("Doctors").document(doctor_email)
    if doctor_ref.get().exists:
        assigned = doctor_ref.collection("AssignedPatients").stream()
        patients += [doc.to_dict() for doc in assigned]

    return patients
@router.get("/doctors")
def search_doctors(email: str = ""):
    docs = db.collection("Doctors").where("email", ">=", email).stream()
    return [doc.to_dict() for doc in docs]


# @router.post("/migrate-fallbacks")
# def migrate_doctor_assignments_to_registered_doctors():
#     assignments = db.collection("DoctorAssignments").stream()
#     migrated = []

#     for doc in assignments:
#         data = doc.to_dict()
#         doctor_email = data.get("doctor_email")
#         patient_id = data.get("patient_national_id")

#         if not doctor_email or not patient_id:
#             continue

#         doctor_ref = db.collection("Doctors").document(doctor_email)
#         if not doctor_ref.get().exists:
#             continue

#         user_ref = db.collection("Users").document(patient_id)
#         user_doc = user_ref.get()
#         full_name = user_doc.to_dict().get("full_name", "Unknown") if user_doc.exists else "Unknown"

#         doctor_ref.collection("AssignedPatients").document(patient_id).set({
#             "patient_national_id": patient_id,
#             "full_name": full_name,
#             "assigned_at": datetime.now().isoformat()
#         })

#         db.collection("DoctorAssignments").document(doc.id).delete()
#         migrated.append(patient_id)

#     return {
#         "migrated": migrated,
#         "count": len(migrated),
#         "message": f"✅ Migrated {len(migrated)} fallback assignments to registered doctors."
#     }
