# ✅ main.py for FastAPI Firestore Integration
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


# === Routers ===
from routers import (
    users,pending_approvals, doctor_assignments,
    surgeries, bloodbiomarkers, measurements, radiology, hypertension,
    medications, diagnoses, allergies, family_history,
    emergency_contacts, risk_assessment, admin, user_role, auth, facilities, qrcode,send_email,translate,pdf_generator
)

app = FastAPI(title="MediGO Backend", version="1.0")

# === Middleware ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Register Routers ===
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(qrcode.router)  
app.include_router(pending_approvals.router)
app.include_router(doctor_assignments.router)
app.include_router(facilities.router)
app.include_router(surgeries.router)
app.include_router(bloodbiomarkers.router)
app.include_router(measurements.router)
app.include_router(radiology.router)
app.include_router(hypertension.router)
app.include_router(medications.router)
app.include_router(diagnoses.router)
app.include_router(allergies.router)
app.include_router(family_history.router)
app.include_router(emergency_contacts.router)
app.include_router(risk_assessment.router)
app.include_router(user_role.router)
app.include_router(send_email.router)
app.include_router(translate.router)
app.include_router(pdf_generator.router)
@app.get("/")
def root():
    return {"message": "Welcome to the MediGO FastAPI Backend"}