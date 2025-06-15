from fastapi import APIRouter, HTTPException
from firebase_config import db

router = APIRouter(prefix="/facilities", tags=["Facilities"])

@router.get("/{facility_id}/procedures")
def get_facility_procedure_patients(facility_id: str):
    # 🔍 Find the Firestore document where facility_id field == provided ID
    query = db.collection("Facilities").where("facility_id", "==", facility_id).limit(1).stream()
    facility_doc = next(query, None)

    if not facility_doc:
        raise HTTPException(status_code=404, detail="Facility not found by ID")

    facility_doc_id = facility_doc.id  # E.g. "louran hospital"
    procedures_ref = db.collection("Facilities").document(facility_doc_id).collection("PatientsMadeProcedures")

    # ✅ List all patients (even if only subcollections exist)
    patient_docs = procedures_ref.list_documents()

    results = []
    for doc_ref in patient_docs:
        patient_id = doc_ref.id
        categories = {}

        for proc_type in ["radiology", "bloodbiomarkers"]:  # Add more if needed
            records_ref = procedures_ref.document(patient_id).collection(proc_type)
            records = [{**r.to_dict(), "id": r.id} for r in records_ref.stream()]
            if records:
                categories[proc_type] = records

        if categories:
            results.append({
                "patient_id": patient_id,
                "procedures": categories
            })

    return results or {
        "message": f"No procedures found under facility: {facility_doc_id}",
        "data": []
    }