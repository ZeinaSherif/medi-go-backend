import os
import requests
import tempfile
import easyocr
import tensorflow as tf
from PIL import Image, ImageEnhance
from io import BytesIO
from datetime import datetime
import numpy as np
import re
import arabic_reshaper
from bidi.algorithm import get_display
from typing import Dict, List, Tuple, Optional, Union

# ─── CONFIGURATION ───────────────────────────────────────────────────
MODEL_PATH = "multitask_lab_reports_model.h5"  # Path to your pre-trained model
IMG_SIZE = (256, 256)  # Resize image to this size for model input
VALIDITY_THRESHOLD = 0.5  # Minimum threshold for validity score
DOMAIN_THRESHOLD = 0.5  # Minimum threshold for domain score

# ─── Comprehensive Medical Tests Dictionary with Normal Ranges ────────
MEDICAL_TESTS = {
    # Complete Blood Count (CBC)
    "CBC": {
        "synonyms": ["CBC", "Complete Blood Count", "صورة دم كاملة", "تعداد الدم الكامل"],
        "normal_range": "Varies by component"
    },
    "WBC": {
        "synonyms": ["WBC", "White Blood Cells", "Leukocytes", "كريات الدم البيضاء"],
        "normal_range": "4,500-11,000 cells/μL",
        "unit": "cells/μL"
    },
    "RBC": {
        "synonyms": ["RBC", "Red Blood Cells", "Erythrocytes", "كريات الدم الحمراء"],
        "normal_range": "Male: 4.7-6.1 million/μL\nFemale: 4.2-5.4 million/μL",
        "unit": "million/μL"
    },
    "Hemoglobin": {
        "synonyms": ["Hemoglobin", "Hb", "HGB", "هيموجلوبين"],
        "normal_range": "Male: 13.5-17.5 g/dL\nFemale: 12.0-15.5 g/dL",
        "unit": "g/dL"
    },
    "Hematocrit": {
        "synonyms": ["Hematocrit", "HCT", "PCV", "هماتوكريت"],
        "normal_range": "Male: 38.8%-50.0%\nFemale: 34.9%-44.5%",
        "unit": "%"
    },
    "Platelets": {
        "synonyms": ["Platelets", "PLT", "Thrombocytes", "الصفائح الدموية"],
        "normal_range": "150,000-450,000/μL",
        "unit": "/μL"
    },

    # Liver Function Tests
    "ALT": {
        "synonyms": ["ALT", "SGPT", "Alanine Aminotransferase", "إنزيم الكبد"],
        "normal_range": "7-55 U/L",
        "unit": "U/L"
    },
    "AST": {
        "synonyms": ["AST", "SGOT", "Aspartate Aminotransferase"],
        "normal_range": "8-48 U/L",
        "unit": "U/L"
    },
    "ALP": {
        "synonyms": ["ALP", "Alkaline Phosphatase", "الفوسفاتاز القلوي"],
        "normal_range": "45-115 U/L",
        "unit": "U/L"
    },
    "Bilirubin": {
        "synonyms": ["Bilirubin", "Total Bilirubin", "بيليروبين"],
        "normal_range": "0.1-1.2 mg/dL",
        "unit": "mg/dL"
    },

    # Kidney Function Tests
    "Creatinine": {
        "synonyms": ["Creatinine", "Cr", "كرياتينين"],
        "normal_range": "Male: 0.74-1.35 mg/dL\nFemale: 0.59-1.04 mg/dL",
        "unit": "mg/dL"
    },
    "Urea": {
        "synonyms": ["Urea", "BUN", "Blood Urea Nitrogen", "يوريا"],
        "normal_range": "7-20 mg/dL",
        "unit": "mg/dL"
    },

    # Diabetes Tests
    "Glucose": {
        "synonyms": ["Glucose", "Blood Glucose", "FBS", "FBG", "سكر الدم"],
        "normal_range": "Fasting: 70-99 mg/dL\nPostprandial: <140 mg/dL",
        "unit": "mg/dL"
    },
    "HbA1c": {
        "synonyms": ["HbA1c", "A1C", "Glycated Hemoglobin", "الهيموجلوبين السكري"],
        "normal_range": "<5.7%",
        "unit": "%"
    },

    # Lipid Profile
    "Cholesterol": {
        "synonyms": ["Cholesterol", "Total Cholesterol", "TC", "كوليسترول"],
        "normal_range": "<200 mg/dL",
        "unit": "mg/dL"
    },
    "Triglycerides": {
        "synonyms": ["Triglycerides", "TAG", "TG", "الدهون الثلاثية"],
        "normal_range": "<150 mg/dL",
        "unit": "mg/dL"
    },
    "HDL": {
        "synonyms": ["HDL", "High-Density Lipoprotein", "بروتين دهني عالي الكثافة"],
        "normal_range": ">40 mg/dL (Male)\n>50 mg/dL (Female)",
        "unit": "mg/dL"
    },
    "LDL": {
        "synonyms": ["LDL", "Low-Density Lipoprotein", "بروتين دهني منخفض الكثافة"],
        "normal_range": "<100 mg/dL (Optimal)",
        "unit": "mg/dL"
    },

    # Thyroid Tests
    "TSH": {
        "synonyms": ["TSH", "Thyroid Stimulating Hormone", "هرمون الغدة الدرقية"],
        "normal_range": "0.4-4.0 mIU/L",
        "unit": "mIU/L"
    },
    "T3": {
        "synonyms": ["T3", "Triiodothyronine"],
        "normal_range": "100-200 ng/dL",
        "unit": "ng/dL"
    },
    "T4": {
        "synonyms": ["T4", "Thyroxine", "ثيروكسين"],
        "normal_range": "5.0-12.0 μg/dL",
        "unit": "μg/dL"
    },

    # Electrolytes
    "Sodium": {
        "synonyms": ["Sodium", "Na", "Na+", "صوديوم"],
        "normal_range": "135-145 mEq/L",
        "unit": "mEq/L"
    },
    "Potassium": {
        "synonyms": ["Potassium", "K", "K+", "بوتاسيوم"],
        "normal_range": "3.5-5.0 mEq/L",
        "unit": "mEq/L"
    },
    "Calcium": {
        "synonyms": ["Calcium", "Ca", "كالسيوم"],
        "normal_range": "8.5-10.2 mg/dL",
        "unit": "mg/dL"
    },

    # Other Tests
    "CRP": {
        "synonyms": ["CRP", "C-Reactive Protein", "بروتين سي التفاعلي"],
        "normal_range": "<1.0 mg/L (Low risk)",
        "unit": "mg/L"
    },
    "ESR": {
        "synonyms": ["ESR", "Erythrocyte Sedimentation Rate", "سرعة الترسيب"],
        "normal_range": "Male: 0-15 mm/hr\nFemale: 0-20 mm/hr",
        "unit": "mm/hr"
    },
    "Urine Analysis": {
        "synonyms": ["Urine Analysis", "Urinalysis", "تحليل البول"],
        "normal_range": "Varies by parameter"
    }
}

# ─── Patient Information Patterns ────────────────────────────────────
PATIENT_INFO_PATTERNS = {
    "patient_name": [r"(?:Patient|Name|اسم المريض)\s*[:\-=\]\s]*\s*([^\n]+)", r"^(?!.*\d)(?:[آ-ي]+\s+)+[آ-ي]+$", r"^(?!.*\d)(?:[A-Za-z]+\s+)+[A-Za-z]+$"],
    "patient_id": [r"(?:Patient\s*ID|ID|الرقم القومي|الكود|كود المريض)\s*[:\-=\]\s]*\s*(\S+)", r"\b\d{14}\b"],  # Egyptian national ID pattern
    "date": [r"(?:Date|تاريخ|التاريخ)\s*[:\-=\]\s]*\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})", r"\b\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b"],  # Date pattern
}

# ─── Initialize EasyOCR Reader ──────────────────────────────────────
reader = easyocr.Reader(['en', 'ar'])

# ─── Load Classification Model ──────────────────────────────────────
model = tf.keras.models.load_model(MODEL_PATH)

# ─── UTILITIES ──────────────────────────
def preprocess_arabic_text(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def enhance_image_quality(image):
    image = ImageEnhance.Contrast(image).enhance(1.5)
    image = ImageEnhance.Sharpness(image).enhance(2.0)
    image = ImageEnhance.Brightness(image).enhance(1.2)
    return image

def classify_image(image: Image.Image):
    arr = np.array(image.resize(IMG_SIZE)) / 255.0
    v_prob, d_prob = model.predict(arr[np.newaxis], verbose=0)
    return float(v_prob[0, 0]), float(d_prob[0, 0])

def extract_text_with_easyocr(image: Image.Image) -> str:
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return "\n".join([res[1] for res in reader.readtext(np.array(image))])

def normalize_unit(unit: str) -> str:
    unit = unit.replace(" ", "").replace("?", "").replace(":", "").replace("’", "").replace("‘", "").lower()
    replacements = {
        "mgdl": "mg/dL", "gdl": "g/dL", "mgdL": "mg/dL",
        "mmoll": "mmol/L", "mmol": "mmol/L",
        "x103/l": "x10^3/μL", "x102/l": "x10^2/μL",
        "x10/ل": "x10^3/μL", "9/dl": "g/dL"
    }
    for key, value in replacements.items():
        if key in unit:
            return value
    return unit


def is_abnormal(value_str: str, range_str: str) -> Optional[bool]:
    try:
        val = float(value_str)
        match = re.search(r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)", range_str.replace(",", ""))
        if match:
            low = float(match.group(1))
            high = float(match.group(2))
            return not (low <= val <= high)
    except:
        pass
    return None

# ─── EXTRACTION FUNCTIONS ───────────────
def extract_patient_name(text: str) -> str:
    patterns = [r"(?:اسم المريض|اسم|Patient Name)[':\-=\]\s]*\s*([^\n]+)"]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            cleaned = re.sub(r'[\d\W_]+', ' ', name).strip()
            return preprocess_arabic_text(cleaned)
    return "Unknown"


def extract_date(text: str) -> Optional[str]:
    pattern = r"(?:Date|تاريخ|التاريخ)\s*[:\-=\]\s]*\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})"
    match = re.search(pattern, text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
        except:
            return match.group(1)
    return None


def extract_patient_id(text: str) -> Optional[str]:
    pattern = r"\b\d{14}\b"
    match = re.search(pattern, text)
    return match.group(0) if match else None

# ─── IS MEDICAL REPORT CHECK ────────────
def is_medical_report(text: str) -> bool:
    text_lower = text.lower()
    for test_data in MEDICAL_TESTS.values():
        for syn in test_data["synonyms"]:
            if syn.lower() in text_lower:
                return True
    medical_indicators = [
        "medical report", "lab results", "test results",
        "تقرير طبي", "نتائج التحليل", "مختبر", "تحليل"
    ]
    return any(ind in text_lower for ind in medical_indicators)

def extract_medical_tests(text: str) -> List[Dict[str, str]]:
    results = []
    seen = set()
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for i in range(len(lines) - 2):
        current_line = lines[i].lower()
        next_line = lines[i + 1]
        third_line = lines[i + 2]

        for canon, test_data in MEDICAL_TESTS.items():
            for synonym in test_data["synonyms"]:
                if synonym.lower() in current_line:
                    # Try to extract numeric value from next line
                    value_match = re.search(r"([\d\.,]+)", next_line)
                    value = value_match.group(1).replace(",", ".") if value_match else ""

                    # Try to extract reference range and unit from third line
                    range_match = re.search(r"(\d+\.?\d*)\s*[-–~]\s*(\d+\.?\d*)\s*(.*)", third_line.replace(",", ""))
                    if not value:
                        continue

                    # Extract unit and range if possible
                    unit = normalize_unit(range_match.group(3)) if range_match else test_data.get("unit", "")
                    reference_range = f"{range_match.group(1)} - {range_match.group(2)}" if range_match else ""
                    flag = is_abnormal(value, reference_range)

                    key = f"{canon}-{value}-{reference_range}"
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "item": canon,
                            "value": value,
                            "reference_range": reference_range,
                            "unit": unit,
                            "flag": flag if flag is not None else False
                        })
    return results



# ─── MAIN PROCESSING FUNCTION ───────────
def process_medical_report(image_source: Union[str, bytes, object]) -> Dict:
    try:

        # Open image depending on input type
        if isinstance(image_source, str):
            if image_source.startswith("http"):
                response = requests.get(image_source)
                if response.status_code != 200:
                    return {"error": "Failed to fetch image from URL", "is_valid": False}
                image = Image.open(BytesIO(response.content))
            else:
                image = Image.open(image_source)
        elif isinstance(image_source, bytes):
            image = Image.open(BytesIO(image_source))
        elif hasattr(image_source, "read"):
            image = Image.open(image_source)
        else:
            return {"error": "Unsupported image source type", "is_valid": False}

        if image.size[0] < 1000 or image.size[1] < 1000:
            image = enhance_image_quality(image)

        # Predict validity
        validity_score, domain_score = classify_image(image)

        result = {
            "validity_score": validity_score,
            "domain_score": domain_score,
            "is_valid": validity_score > VALIDITY_THRESHOLD,
            "is_medical": False,
            "patient_info": {"patient_name": None, "date": None},
            "results": [],
            "ocr_text": "",
            "error": None
        }

        if not result["is_valid"]:
            result["error"] = "Image quality insufficient for reading"
            return result

        text = extract_text_with_easyocr(image)
        result["ocr_text"] = text
        result["is_medical"] = any(syn.lower() in text.lower() for test in MEDICAL_TESTS.values() for syn in test["synonyms"])

        if not result["is_medical"]:
            result["error"] = "No medical content detected"
            return result

        # Extract patient info + medical tests
        result["patient_info"]["patient_name"] = extract_patient_name(text)
        result["patient_info"]["date"] = extract_date(text)
        result["results"] = extract_medical_tests(text)

        return result

    except Exception as e:
        return {
            "error": f"Processing failed: {str(e)}",
            "is_valid": False,
            "domain_score": 0,
            "validity_score": 0,
            "is_medical": False,
            "results": [],
            "patient_info": {}
        }

