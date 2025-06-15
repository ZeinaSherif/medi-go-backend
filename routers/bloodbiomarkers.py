from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Body
from datetime import datetime
import pytz, uuid
from firebase_config import db, bucket
from models.schema import resolve_added_by_name, fetch_patient_name
from routers.doctor_assignments import is_doctor_assigned, auto_assign_reviewer
from routers.ocr_utils import process_medical_report

router = APIRouter(prefix="/biomarkers", tags=["Blood BioMarkers"])
egypt_tz = pytz.timezone("Africa/Cairo")


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


@router.post("/{national_id}/ocr")
async def add_biomarker_via_ocr(
    national_id: str,
    image: UploadFile = File(...),
    added_by: str = Form(...)
):
    try:
        image_bytes = await image.read()
        report = process_medical_report(image_bytes)

        if report.get("error"):
            raise HTTPException(status_code=400, detail=report["error"])
        if not report["is_valid"] or not report["is_medical"]:
            raise HTTPException(status_code=422, detail="Image is not valid or not medical")

        filename = f"{uuid.uuid4().hex}_{image.filename}"
        storage_path = f"lab_tests/{filename}"
        blob = bucket.blob(storage_path)
        blob.upload_from_string(image_bytes, content_type=image.content_type)
        token = uuid.uuid4().hex
        blob.metadata = {"firebaseStorageDownloadTokens": token}
        blob.patch()
        image_url = f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/{storage_path.replace('/', '%2F')}?alt=media&token={token}"

        extracted_tests = []
        for test in report["results"]:
            extracted_tests.append({
                "item": test.get("item") or test.get("synonym", ""),
                "value": test.get("value"),
                "unit": test.get("unit", ""),
                "reference_range": test.get("reference_range", ""),
                "flag": test.get("flag", False)
            })

        extracted_date = report.get("patient_info", {}).get("date")
        if not extracted_date:
            extracted_date = datetime.now(egypt_tz).date()
        elif isinstance(extracted_date, str):
            try:
                extracted_date = datetime.strptime(extracted_date, "%Y-%m-%d").date()
            except ValueError:
                extracted_date = datetime.now(egypt_tz).date()

        current_timestamp = datetime.now(egypt_tz)

        biomarker_entry = {
            "extracted_date": extracted_date.isoformat(),
            "added_date": current_timestamp.isoformat(),
            "results": extracted_tests,
            "added_by": added_by,
            "image_url": image_url
        }

        if is_valid_facility_or_doctor(added_by):
            user_ref = db.collection("Users").document(national_id)
            if not user_ref.get().exists:
                raise HTTPException(status_code=404, detail="User not found")

            full_record = {
                **biomarker_entry,
                "added_by_name": resolve_added_by_name(added_by),
                "patient_name": fetch_patient_name(user_ref)
            }

            timestamp_id = current_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            db.collection("Users").document(national_id) \
                .collection("ClinicalIndicators").document("bloodbiomarkers") \
                .collection("Records").document(timestamp_id).set(full_record)

            store_procedure_under_facility(added_by, national_id, "bloodbiomarkers", full_record)

            return {
                "message": "✅ Biomarker added directly by doctor/facility",
                "image_url": image_url,
                "timestamp": timestamp_id,
                "added_by": added_by
            }

        doctor_name = is_doctor_assigned(national_id)
        assigned_to = doctor_name or auto_assign_reviewer(national_id)["assigned_to"]
        doc_id = uuid.uuid4().hex

        db.collection("PendingApprovals").document(assigned_to) \
            .collection("bloodbiomarkers").document(doc_id).set({
                "national_id": national_id,
                "record": biomarker_entry,
                "data_type": "bloodbiomarkers",
                "assigned_to": assigned_to,
                "assigned_doctor_name": doctor_name,
                "submitted_at": current_timestamp.isoformat()
            })

        return {
            "status": "submitted_for_approval",
            "assigned_to": assigned_to,
            "doc_id": doc_id,
            "image_url": image_url,
            "validity_score": report.get("validity_score"),
            "domain_score": report.get("domain_score"),
            "results": extracted_tests
        }

    except Exception as e:
        print(f"Error processing biomarker OCR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@router.get("/{national_id}")
def get_biomarkers(national_id: str):
    try:
        user_ref = db.collection("Users").document(national_id)
        records_ref = user_ref.collection("ClinicalIndicators") \
                              .document("bloodbiomarkers") \
                              .collection("Records")
        records = records_ref.stream()
        result = []

        for r in records:
            data = r.to_dict()
            data['id'] = r.id
            result.append(data)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.put("/{national_id}/edit")
def edit_biomarker_record(
    national_id: str,
    timestamp_id: str = Body(...),
    updated_results: list = Body(...)
):
    try:
        record_ref = db.collection("Users").document(national_id) \
            .collection("ClinicalIndicators").document("bloodbiomarkers") \
            .collection("Records").document(timestamp_id)

        if not record_ref.get().exists:
            raise HTTPException(status_code=404, detail="Biomarker record not found")

        # Update only the results field (other metadata like image_url remains intact)
        record_ref.update({"results": updated_results})

        return {"message": "Biomarker results updated successfully", "timestamp": timestamp_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating biomarker: {str(e)}")


@router.post("/{national_id}/manual")
def add_manual_biomarker(
    national_id: str,
    added_by: str = Body(...),
    item: str = Body(...),
    value: str = Body(...),
    unit: str = Body(""),
    reference_range: str = Body(""),
):
    try:
        record = {
            "item": item,
            "value": value,
            "unit": unit,
            "reference_range": reference_range,
            "flag": False
        }

        # Get latest biomarker document
        records_ref = db.collection("Users").document(national_id) \
            .collection("ClinicalIndicators").document("bloodbiomarkers") \
            .collection("Records")

        docs = list(records_ref.stream())
        if not docs:
            raise HTTPException(status_code=404, detail="No existing record found to append to")

        # Sort by timestamp id (assuming YYYY-MM-DD HH:MM:SS format)
        docs.sort(key=lambda d: d.id, reverse=True)
        latest_doc_ref = docs[0].reference
        latest_data = docs[0].to_dict()

        # Append new result
        latest_data["results"].append(record)
        latest_doc_ref.set(latest_data)

        return {"message": "Manual result added to latest test", "timestamp": docs[0].id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
