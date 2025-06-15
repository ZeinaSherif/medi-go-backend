import uuid
import pandas as pd
import re
import sys
import io
from datetime import datetime
from firebase_config import db
from models.schema import (
    UserCreate, AllergyCreate, DiagnosisCreate,
    MeasurementCreate, MedicationCreate, SurgeryCreate,
    FamilyHistoryCreate
)

# -------------------- Utility Functions --------------------

def convert_arabic_to_english_numerals(text):
    """
    Convert Arabic numerals to English numerals.
    """
    if not isinstance(text, str):
        return text
    arabic_to_english = {
        '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
        '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
    }
    for ar, en in arabic_to_english.items():
        text = text.replace(ar, en)
    return re.sub(r'[^\d]', '', text)

def generate_id():
    """
    Generate a unique ID.
    """
    return str(uuid.uuid4())

def calculate_bmi(weight, height):
    """
    Calculate BMI given weight (kg) and height (cm).
    """
    height_meters = height / 100
    return round(weight / (height_meters ** 2), 2)

# -------------------- Firestore Interactions --------------------

def add_document(collection_name, document_id, data):
    """
    Add or update a document in Firestore.
    """
    db.collection(collection_name).document(document_id).set(data)

# -------------------- Main Processing Function --------------------

def add_user_data_from_excel(excel_file_path):
    """
    Read user data from an Excel file and add it to Firestore.
    """
    df = pd.read_excel(excel_file_path, dtype=str, engine='openpyxl')
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    column_mapping = {
        'Id': None, 'Name': None, 'Email': None, 'Password': None,
        'Phone': None, 'Blood Group': None, 'Address': None,
        'City': None, 'Marital Status': None, 'Gender': None,
        'Age': None, 'Smoking?': None, 'Weight': None, 'Height': None,
        'Is chronic?': None, 'Chronic Disease': None, 'Allergy': None,
        'Long term medication?': None, 'Medication': None, 'Surgery': None,
        'Family History Disease': None
    }

    # Map columns dynamically
    for expected_col in column_mapping.keys():
        for actual_col in df.columns:
            if expected_col.lower() in actual_col.lower():
                column_mapping[expected_col] = actual_col
                break

    print("\nColumn Mapping:")
    for expected, actual in column_mapping.items():
        print(f"{expected}: {actual}")

    for index, row in df.iterrows():
        try:
            def get_column_value(column_name, default=''):
                mapped_col = column_mapping.get(column_name)
                return str(row[mapped_col]).strip() if mapped_col and mapped_col in row else default

            # User creation
            user_id = convert_arabic_to_english_numerals(get_column_value('Id'))
            age = convert_arabic_to_english_numerals(get_column_value('Age'))
            birthdate = str(datetime.now(egypt_tz)).year - int(age)) if age else None

            gender = get_column_value('Gender').lower()
            if gender in ['ذكر', 'male', 'm']:
                gender = 'male'
            elif gender in ['انثى', 'female', 'f']:
                gender = 'female'

            user_data = UserCreate(
                national_id=user_id,
                full_name=get_column_value('Name'),
                email=get_column_value('Email'),
                password=get_column_value('Password'),
                birthdate=birthdate,
                gender=gender,
                phone_number=get_column_value('Phone'),
                blood_group=get_column_value('Blood Group'),
                address=get_column_value('Address'),
                city=get_column_value('City'),
                marital_status=get_column_value('Marital Status')
            )
            add_document("SurveyUsers", user_data.national_id, user_data.dict())

            # Allergies
            allergy = get_column_value('Allergy')
            if allergy and allergy.lower() != 'لا':
                allergy_data = AllergyCreate(
                    user_id=user_id,
                    allergen_name=allergy,
                    reaction_type="Unknown",
                    severity="Unknown"
                )
                add_document(f"SurveyUsers/{user_id}/Allergies", allergy_data.allergen_name, allergy_data.dict())

            # Chronic Diseases
            if get_column_value('Is chronic?').lower() in ['yes', 'نعم']:
                chronic_disease = get_column_value('Chronic Disease')
                if chronic_disease:
                    diagnosis_data = DiagnosisCreate(
                        user_id=user_id,
                        disease_name=chronic_disease,
                        diagnosis_date=str(datetime.now(egypt_tz)).date()),
                        diagnosed_by="Unknown",
                        is_chronic=True
                    )
                    add_document(f"SurveyUsers/{user_id}/Diagnoses", diagnosis_data.disease_name, diagnosis_data.dict())

            # Measurements (BMI)
            weight = float(convert_arabic_to_english_numerals(get_column_value('Weight', 0)))
            height = float(convert_arabic_to_english_numerals(get_column_value('Height', 0)))
            if weight and height:
                measurement_data = MeasurementCreate(
                    user_id=user_id,
                    measurement_type="BMI",
                    value=str(calculate_bmi(weight, height)),
                    unit="kg/m2",
                    measured_on=str(datetime.now(egypt_tz)).date())
                )
                add_document(f"SurveyUsers/{user_id}/Measurements", measurement_data.measurement_type, measurement_data.dict())

            # Medications
            medication = get_column_value('Medication')
            if medication and get_column_value('Long term medication?').lower() in ['yes', 'نعم']:
                medication_data = MedicationCreate(
                    user_id=user_id,
                    medication_name=medication,
                    dosage="Unknown",
                    frequency="Long-term",
                    start_date=str(datetime.now(egypt_tz)).date()),
                    prescribing_doctor="Unknown"
                )
                add_document(f"SurveyUsers/{user_id}/Medications", medication_data.medication_name, medication_data.dict())

            # Surgeries
            surgery = get_column_value('Surgery')
            if surgery and surgery.lower() != 'لا':
                surgery_data = SurgeryCreate(
                    user_id=user_id,
                    surgery_name=surgery,
                    surgery_date=str(datetime.now(egypt_tz)).date()),
                    surgeon_name="Unknown",
                    hospital_name="Unknown"
                )
                add_document(f"SurveyUsers/{user_id}/Surgeries", surgery_data.surgery_name, surgery_data.dict())

            # Family History
            family_history = get_column_value('Family History Disease')
            if family_history and family_history.lower() != 'لا':
                family_history_data = FamilyHistoryCreate(
                    user_id=user_id,
                    disease_name=family_history,
                    relation="Unknown",
                    notes="Unknown"
                )
                add_document(f"SurveyUsers/{user_id}/FamilyHistory", family_history_data.disease_name, family_history_data.dict())

            print(f"Successfully added user: {user_data.full_name}")

        except Exception as e:
            print(f"Error processing row {index}: {e}")
            print("Row data:", row)

# -------------------- Main Execution --------------------

def main():
    excel_file_path = r"F:\firebase_fastapi_project\Electronic Medical Record.xlsx"
    add_user_data_from_excel(excel_file_path)
    print("Data migration completed!")

if __name__ == "__main__":
    main()
