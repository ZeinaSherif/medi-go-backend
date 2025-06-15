from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from typing import Optional, List, Dict, Literal
from datetime import date as dt_date, datetime
import pytz
from firebase_config import db
# ----------------- Literal Types -----------------
AllowedRoles = Literal["patient", "hospital", "laboratory", "radiology", "pharmacy", "clinic", "visitor"]
Gender = Literal["male", "female"]
BloodGroup = Literal["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
MaritalStatus = Literal["single", "married", "divorced", "widowed"]
AgeGroup = Literal["Young", "Middle-aged", "Older"]
SmokerStatus = Literal["Non-smoker", "Light smoker", "Moderate smoker", "Heavy smoker"]
BpCategory = Literal["Low", "Normal", "Elevated", "Stage 1", "Stage 2"]
BmiCategory = Literal["Underweight", "Normal", "Overweight", "Obese"]

egypt_tz = pytz.timezone("Africa/Cairo")

# ----------------- Helper Functions -----------------
def get_biomarker_value(biomarkers: dict, canonical_name: str, default: float = 0.0) -> float:
    """
    Retrieve a biomarker value from OCR results using synonyms.
    """
    synonyms = MEDICAL_TESTS.get(canonical_name, {}).get("synonyms", [])
    for test in biomarkers.get("results", []):
        item_name = test.get("item", "").strip().lower()
        for syn in synonyms:
            if syn.strip().lower() == item_name:
                try:
                    return float(test.get("value", default))
                except ValueError:
                    return default
    return default
def calculate_age(birthdate_str: str) -> int:
    birthdate = datetime.fromisoformat(birthdate_str).date()
    today = datetime.today().date()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))

def fetch_patient_name(user_ref):
    doc = user_ref.get()
    return doc.to_dict().get("full_name", "Unknown") if doc.exists else "Unknown"

def resolve_added_by_name(added_by_id: str) -> str:
    # Check if it's a facility
    facility_docs = db.collection("Facilities").where("facility_id", "==", added_by_id).limit(1).stream()
    for doc in facility_docs:
        return doc.to_dict().get("facility_name", "Unknown Facility")
        
    # Check if it's a doctor
    doctor_docs = db.collection("Doctors").where("doctor_id", "==", added_by_id).limit(1).stream()
    for doc in doctor_docs:
        return doc.to_dict().get("doctor_name", "Unknown Doctor")
        
    return "Patient"  # Fallback

# ----------------- Field Validators -----------------
def validate_phone_number(value: str) -> str:
    digits = ''.join(filter(str.isdigit, value))
    if len(digits) != 11 or not digits.startswith("0"):
        raise ValueError("Phone number must be exactly 11 digits and start with 0")
    return digits

def validate_national_id(value: str) -> str:
    if len(value) != 14 or not value.isdigit():
        raise ValueError("National ID must be exactly 14 digits")
    return value

# ----------------- Users -----------------
class UserCreate(BaseModel):
    national_id: str
    password: str
    full_name: str
    profile_photo: Optional[str] = None
    birthdate: str = Field(..., example=dt_date.today().isoformat())
    phone_number: str
    email:str
    gender: Gender
    blood_group: BloodGroup
    marital_status: MaritalStatus
    address: str
    region: str
    city: str
    current_smoker: bool = False
    cigs_per_day: int = 0
    doctoremail: Optional[str] = None

    @field_validator("national_id")
    @classmethod
    def nid_valid(cls, v): return validate_national_id(v)

    @field_validator("phone_number")
    @classmethod
    def phone_valid(cls, v): return validate_phone_number(v)

    @field_validator("cigs_per_day")
    @classmethod
    def cigs_logic(cls, v, info):
        current_smoker = info.data.get("current_smoker")
        if current_smoker and v <= 0:
            raise ValueError("Smokers must have cigs_per_day > 0")
        if not current_smoker and v != 0:
            raise ValueError("Non-smokers must have cigs_per_day = 0")
        return v

class UserResponse(BaseModel):
    national_id:  Optional[str] = None
    password: Optional[str] = None
    full_name: Optional[str] = None
    profile_photo: Optional[str] = None
    birthdate: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    marital_status: Optional[str] = None
    address: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    current_smoker: Optional[bool] = None
    cigs_per_day: Optional[int] = None
    age: Optional[int] = None
    
# ----------------- Doctors -----------------
class Doctors(BaseModel):
    doctor_id: str
    password: str
    admin_id: str
    doctor_name: str
    specialization: str
    city: str
    region: str
    address: str
    email: EmailStr
    phone_number: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(egypt_tz))

class DoctorsCreateRequest(BaseModel):
    doctor_name: str
    specialization: str
    city: str
    region: str
    address: str
    email: EmailStr
    phone_number: str

# ----------------- Facility -----------------
class Facility(BaseModel):
    facility_id: str
    password: str
    admin_id: str
    facility_name: str
    city: str
    region: str
    address: str
    role: AllowedRoles
    access_scope: Dict[str, List[str]]
    email: EmailStr
    phone_number: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(egypt_tz))

    @field_validator("phone_number")
    @classmethod
    def phone_valid(cls, v): return validate_phone_number(v)

class FacilityPatientLink(BaseModel):
    facility_id: str
    patient_national_id: str

class FacilityCreateRequest(BaseModel):
    facility_name: str
    city: str
    region: str
    address: str
    role: str
    email: EmailStr
    phone_number: str

# ----------------- Emergency Contacts -----------------
class EmergencyContact(BaseModel):
    full_name: str
    relationship: str
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def phone_valid(cls, v): return validate_phone_number(v)

# ----------------- Doctor Assignments -----------------
class DoctorAssignment(BaseModel):
    doctor_email: str
    doctor_name: str
    patient_national_id: str
    
# ----------------- QR Code -----------------
class QRCodeCreate(BaseModel):
    user_id: str
    last_accessed: Optional[datetime] = None
    expiration_date: datetime
    qr_image: str

class QRCodeResponse(QRCodeCreate): pass

class VisitorQRCode(BaseModel):
    visitor_name: str
    qr_code_value: str

# ----------------- Allergies -----------------
class Allergy(BaseModel):
    allergen_name: str
    reaction_type: str
    severity: str
    notes: Optional[str] = None
    added_by: Optional[str] = None

# ----------------- Diagnosis -----------------
class DiagnosisEntry(BaseModel):
    disease_name: str
    diagnosis_date: dt_date
    diagnosed_by: str
    is_chronic: bool
    details_notes: Optional[str] = None
    added_by: Optional[str] = None

# ----------------- Family History -----------------
class FamilyHistoryEntry(BaseModel):
    disease_name: str
    age_of_onset: int
    relative_relationship: str
    notes: Optional[str] = None
    added_by: Optional[str] = None

# ----------------- Surgeries -----------------
class SurgeryEntry(BaseModel):
    procedure_name: str
    surgeon_name: str
    surgery_date: dt_date
    procedure_notes: Optional[str] = None
    added_by: Optional[str] = None

# ----------------- Radiology -----------------
class RadiologyTestInput(BaseModel):
    radiology_name: str
    date: Optional[dt_date] = Field(default_factory=dt_date.today)
    report_notes: Optional[str] = None
    added_by: str

class RadiologyTest(RadiologyTestInput):
    patient_name: Optional[str] = None
    added_by_name: Optional[str] = None
    image_validity: Optional[bool] = None
    image_confidence: Optional[float] = None
    image_url: Optional[str] = None
    
# ----------------- Blood BioMarkers -----------------
class TestResultItem(BaseModel):
    item: str
    value: str
    reference_range: Optional[str] = None
    unit: Optional[str] = None
    flag: Optional[bool] = False

class BloodBiomarkerInput(BaseModel):
    test_name: str
    date: Optional[dt_date] = Field(default_factory=dt_date.today)
    results: List[TestResultItem]
    added_by: str

class BloodBioMarker(BloodBiomarkerInput):
    patient_name: Optional[str] = None
    added_by_name: Optional[str] = None
   
    # ----------------- Medications -----------------
class MedicationEntry(BaseModel):
    trade_name: str
    scientific_name: str
    dosage: str
    frequency: str
    certain_duration: bool
    start_date: Optional[dt_date] = None
    end_date: Optional[dt_date] = None
    current: bool
    prescribing_doctor: str
    notes: Optional[str] = None
    added_by: str
    bp_medication: Optional[bool] = None

    @model_validator(mode="after")
    def validate_dates_and_flags(cls, values):
        certain_duration = values.certain_duration
        current = values.current
        start_date = values.start_date
        end_date = values.end_date

        # ✅ Ensure mutual exclusivity
        if certain_duration == current:
            raise ValueError("Only one of 'certain_duration' or 'current' must be True.")

        if certain_duration:
            if not start_date or not end_date:
                raise ValueError("Start and end dates must be provided for medications taken for a certain duration.")
        elif current:
            if not start_date:
                raise ValueError("Start date must be provided for currently taken medications.")
            if end_date is not None:
                raise ValueError("End date must be left empty for current medications.")

        return values

# ----------------- Hypertension -----------------
class HypertensionEntry(BaseModel):
    sys_value: int
    dia_value: int
    added_by: Optional[str] = None

# ----------------- Measurements -----------------
class HeightWeightCreate(BaseModel):
    height: Optional[float] = None
    weight: Optional[float] = None
    added_by: Optional[str] = None

    @field_validator("height", "weight")
    @classmethod
    def validate_positive(cls, value):
        if value is not None and value <= 0:
            raise ValueError("Must be positive")
        return value

# ----------------- Risk Prediction -----------------
# ----------------- Radiology -----------------
class RadiologyTestInput(BaseModel):
    radiology_name: str
    date: Optional[dt_date] = Field(default_factory=dt_date.today)
    report_notes: Optional[str] = None
    added_by: str

class RadiologyTest(RadiologyTestInput):
    patient_name: Optional[str] = None
    added_by_name: Optional[str] = None
    image_validity: Optional[bool] = None
    image_confidence: Optional[float] = None
    image_filename: Optional[str] = None 

# ----------------- Blood BioMarkers -----------------
class TestResultItem(BaseModel):
    item: str
    value: str
    reference_range: Optional[str] = None
    unit: Optional[str] = None
    flag: Optional[bool] = False

class BloodBiomarkerInput(BaseModel):
    test_name: str
    date: Optional[dt_date] = Field(default_factory=dt_date.today)
    results: List[TestResultItem]
    added_by: str

class BloodBioMarker(BloodBiomarkerInput):
    patient_name: Optional[str] = None
    added_by_name: Optional[str] = None
    # ----------------- Medications -----------------

    @model_validator(mode="after")
    def validate_dates_and_flags(cls, values):
        certain_duration = values.certain_duration
        current = values.current
        start_date = values.start_date
        end_date = values.end_date

        # ✅ Ensure mutual exclusivity
        if certain_duration == current:
            raise ValueError("Only one of 'certain_duration' or 'current' must be True.")

        if certain_duration:
            if not start_date or not end_date:
                raise ValueError("Start and end dates must be provided for medications taken for a certain duration.")
        elif current:
            if not start_date:
                raise ValueError("Start date must be provided for currently taken medications.")
            if end_date is not None:
                raise ValueError("End date must be left empty for current medications.")

        return values

# ----------------- Risk Assessment -----------------
class DerivedFeatures(BaseModel):
    age_group: AgeGroup
    smoker_status: SmokerStatus
    is_obese: bool
    bp_category: BpCategory
    bmi_category: BmiCategory
    bmi: float
    pulse_pressure: float
    male_smoker: bool
    prediabetes_indicator: bool
    insulin_resistance: bool
    metabolic_syndrome: bool

class TopFeatures(BaseModel):
    feature_name: str
    contribution_score: float
    
class BiomarkerEntry(BaseModel):
    item: str
    value: float
    unit: Optional[str] = None

class RiskPredictionOutput(BaseModel):
    diabetes_risk: float
    hypertension_risk: float
    derived_features: DerivedFeatures
    input_values: dict
    top_diabetes_features: List[TopFeatures]
    top_hypertension_features: List[TopFeatures]
    biomarker_chart_data: Optional[List[BiomarkerEntry]] = None

class RiskAssessmentEntry(BaseModel):
    risk_category: str
    prediction_date: dt_date
    risk_score: int
    primary_risk_factors: str
    recommended_actions: str

# ----------------- Roles -----------------
class RoleCreate(BaseModel):
    role_name: str
    role_id: int
    access_scope: Dict[str, List[str]]

class RoleResponse(RoleCreate):
    pass

class QRCodeCreate(BaseModel):
    user_id: str
    last_accessed: str
    expiration_date: str
    qr_image: str

class QRCodeResponse(BaseModel):
    user_id: str
    last_accessed: str
    expiration_date: str
    qr_image: str