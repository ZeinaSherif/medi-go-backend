from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from datetime import date, datetime
import pytz, uuid
from models.schema import RadiologyTest, resolve_added_by_name, fetch_patient_name
from routers.doctor_assignments import is_doctor_assigned, auto_assign_reviewer
from firebase_config import db, bucket
from routers.image_classifier import classify_radiology_image

router = APIRouter(prefix="/radiology", tags=["Radiology"])
egypt_tz = pytz.timezone("Africa/Cairo")

def convert_dates(obj):
    if isinstance(obj, dict):
        return {k: convert_dates(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_dates(v) for v in obj]
    elif isinstance(obj, (date, datetime)):
        return obj.strftime("%Y-%m-%d")
    else:
        return obj

def is_valid_facility_or_doctor(added_by_id: str) -> bool:
    facilities = db.collection("Facilities").where("facility_id", "==", added_by_id).stream()
    if any(True for _ in facilities):
        return True
    doctors = db.collection("Doctors").where("doctor_id", "==", added_by_id).stream()
    if any(True for _ in doctors):
        return True
    return False

def store_procedure_under_facility(facility_id: str, patient_id: str, procedure_type: str, procedure_data: dict):
    facility_docs = db.collection("Facilities").where("facility_id", "==", facility_id).stream()
    facility_doc = next(facility_docs, None)
    if not facility_doc:
        return
    facility_doc_id = facility_doc.id
    timestamp = datetime.now(egypt_tz).strftime("%Y-%m-%d %H:%M:%S")
    db.collection("Facilities").document(facility_doc_id) \
        .collection("PatientsMadeProcedures").document(patient_id) \
        .collection(procedure_type).document(timestamp).set(procedure_data)

@router.post("/{national_id}")
async def add_radiology(
    national_id: str,
    image: UploadFile = File(...),
    radiology_name: str = Form(...),
    added_by: str = Form(...),
    report_notes: str = Form(None),
    date_str: str = Form(None)
):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    # Read image bytes
    image_bytes = await image.read()

    # Classify the image
    try:
        classification = classify_radiology_image(image_bytes=image_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification error: {str(e)}")

    if classification.get("is_valid") is not True:
        raise HTTPException(status_code=422, detail="Image is not valid radiology scan")

    # Upload image to Firebase Storage
    filename = f"{uuid.uuid4().hex}_{image.filename}"
    storage_path = f"radiology_tests/{filename}"
    blob = bucket.blob(storage_path)
    blob.upload_from_string(image_bytes, content_type=image.content_type)

    # Generate access token and attach to metadata
    token = uuid.uuid4().hex
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.patch()

# Correct image URL with token
    image_url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/"
            f"{storage_path.replace('/', '%2F')}?alt=media&token={token}")

    # Handle date
    if date_str:
        try:
            radiology_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use yyyy-mm-dd")
    else:
        radiology_date = datetime.now(egypt_tz).date()

    current_timestamp = datetime.now(egypt_tz)
    entry_dict = {
        "radiology_name": radiology_name,
        "date": radiology_date.strftime("%Y-%m-%d"),
        "report_notes": report_notes or "",
        "added_by": added_by,
        "image_url": image_url,
        "image_validity": classification.get("is_valid"),
        "image_confidence": classification.get("confidence"),
    }

    if is_valid_facility_or_doctor(added_by):
        full_record = {
            **entry_dict,
            "added_by_name": resolve_added_by_name(added_by),
            "patient_name": fetch_patient_name(user_ref),
        }

        timestamp_id = current_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        db.collection("Users").document(national_id) \
            .collection("ClinicalIndicators").document("radiology") \
            .collection("Records").document(timestamp_id).set(full_record)

        store_procedure_under_facility(added_by, national_id, "radiology", full_record)

        return {
            "message": "✅ Radiology record added directly by facility/doctor",
            "added_by": added_by,
            "added_by_name": full_record["added_by_name"],
            "timestamp": timestamp_id,
            "date": full_record["date"],
            "image_url": image_url,
            "patient_name": full_record["patient_name"],
            "radiology_name": radiology_name
        }

    # Approval Flow
    doctor_name = is_doctor_assigned(national_id)
    assigned_to = doctor_name or auto_assign_reviewer(national_id)["assigned_to"]
    doc_id = uuid.uuid4().hex

    db.collection("PendingApprovals").document(assigned_to).collection("radiology").document(doc_id).set({
        "national_id": national_id,
        "record": entry_dict,
        "data_type": "radiology",
        "assigned_to": assigned_to,
        "assigned_doctor_name": doctor_name,
        "submitted_at": current_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    })

    return {
        "status": "submitted_for_approval",
        "assigned_to": assigned_to,
        "doc_id": doc_id,
        "image_url": image_url,
        "classification": classification
    }

@router.get("/{national_id}")
def get_radiology(national_id: str):
    user_ref = db.collection("Users").document(national_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    docs = user_ref.collection("ClinicalIndicators").document("radiology").collection("Records").stream()
    records = []
    for doc in docs:
        record = doc.to_dict()
        records.append(record)
    return records