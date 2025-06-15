from datetime import datetime
from fastapi import APIRouter, HTTPException
from firebase_config import db
import pandas as pd
import numpy as np
import joblib
from models.schema import RiskPredictionOutput, DerivedFeatures, TopFeatures

router = APIRouter(prefix="/risk", tags=["Risk Assessment"])

# Load models and preprocessing assets
scaler_diabetes = joblib.load("scaler_diabetes.pkl")
scaler_hypertension = joblib.load("scaler_hypertension.pkl")
selector_dia = joblib.load("selector_dia.pkl")
selector_hyp = joblib.load("selector_hypertension.pkl")
model_diabetes = joblib.load("model_diabetes.pkl")
model_hypertension = joblib.load("model_hypertension.pkl")
selected_features_dia = joblib.load("selected_diabetes_features.pkl")
selected_features_hyp = joblib.load("selected_hypertension_features.pkl")


@router.post("/{national_id}", response_model=RiskPredictionOutput)
async def assess_risk(national_id: str):
    try:
        # === 1. Get User Info ===
        user_doc = db.collection("Users").document(national_id).get()
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="User not found")
        user = user_doc.to_dict()

        # === 2. Measurements ===
        measurements_doc = db.collection("Users").document(national_id).collection("ClinicalIndicators").document("measurements").get()
        measurements = measurements_doc.to_dict()
        if not measurements:
            raise HTTPException(status_code=404, detail="Missing measurements")

        # === 3. Latest Hypertension Record ===
        hyp_docs = db.collection("Users").document(national_id).collection("ClinicalIndicators") \
            .document("Hypertension").collection("Records").order_by("date", direction="DESCENDING").limit(1).stream()
        hypertension_data = next(hyp_docs, None)
        hypertension = hypertension_data.to_dict() if hypertension_data else {}

        # === 4. Latest Biomarker Record ===
        bio_docs = db.collection("Users").document(national_id).collection("ClinicalIndicators") \
            .document("bloodbiomarkers").collection("Records").order_by("date_added", direction="DESCENDING").limit(1).stream()
        biomarker_data = next(bio_docs, None)
        biomarkers = biomarker_data.to_dict() if biomarker_data else {}

        # === 5. Latest Medication ===
        med_docs = db.collection("Users").document(national_id).collection("medications") \
            .order_by("start_date", direction="DESCENDING").limit(1).stream()
        medication_data = next(med_docs, None)
        medications = medication_data.to_dict() if medication_data else {}

        # === 6. Calculate BMI Category ===
        bmi = measurements.get("bmi", 25.0)
        if bmi < 18.5:
            bmi_category = 0
        elif 18.5 <= bmi < 25:
            bmi_category = 1
        elif 25 <= bmi < 30:
            bmi_category = 2
        else:
            bmi_category = 3
        is_obese = 1 if bmi >= 30 else 0

        # === 7. Assemble Features ===
        features = {
            'male': 1 if user.get("gender") == "male" else 0,
            'BPMeds': int(medications.get("bp_medication", 0)),
            'totChol': float(next((r.get("value") for r in biomarkers.get("results", []) if r.get("item") == "Cholesterol"), 180)),
            'sysBP': float(hypertension.get("sysBP", 120)),
            'diaBP': float(hypertension.get("diaBP", 80)),
            'heartRate': float(hypertension.get("heartRate", 72)),
            'glucose': float(next((r.get("value") for r in biomarkers.get("results", []) if r.get("item") == "Glucose"), 100)),
            'age_group': int(user.get("age_group", 1)),
            'smoker_status': int(user.get("smoker_status", 0)),
            'is_obese': is_obese,
            'bp_category': int(hypertension.get("bp_category", 0)),
            'bmi_category': bmi_category,
            'male_smoker': int(1 if user.get("gender") == "male" and user.get("smoker_status", 0) > 0 else 0),
            'prediabetes_indicator': int(hypertension.get("prediabetes_indicator", 0)),
            'insulin_resistance': int(hypertension.get("insulin_resistance", 0)),
            'metabolic_syndrome': int(hypertension.get("metabolic_syndrome", 0))
        }

        # === 8. Predict Diabetes ===
        X_dia = pd.DataFrame([features])
        X_dia["hypertension"] = 0.5
        X_dia = X_dia[scaler_diabetes.feature_names_in_]
        scaled_dia = scaler_diabetes.transform(X_dia)
        selected_dia = selector_dia.transform(scaled_dia)
        diabetes_prob = float(model_diabetes.predict_proba(selected_dia)[0][1])

        # === 9. Predict Hypertension ===
        X_hyp = pd.DataFrame([features])
        X_hyp["diabetes"] = diabetes_prob
        X_hyp = X_hyp[scaler_hypertension.feature_names_in_]
        scaled_hyp = scaler_hypertension.transform(X_hyp)
        selected_hyp = selector_hyp.transform(scaled_hyp)
        hypertension_prob = float(model_hypertension.predict_proba(selected_hyp)[0][1])

        # === 10. Get Base Model ===
        def get_base_model(model):
            if hasattr(model, "named_estimators_"):
                for key in model.named_estimators_:
                    return model.named_estimators_[key]
            if hasattr(model, "estimators_"):
                return model.estimators_[0]
            return model

        # === 11. Top Features (Cleaned) ===
        def top_features(model, X_selected, feature_names, top_n=3):
            try:
                base_model = get_base_model(model)

                # === Method 1: Tree-based feature_importances_ ===
                if hasattr(base_model, "feature_importances_"):
                    importances = base_model.feature_importances_
                    indices = np.argsort(importances)[::-1][:top_n]

                    # Normalize to percentage
                    top_values = importances[indices]
                    total = top_values.sum() if top_values.sum() > 0 else 1e-8  # prevent divide by zero
                    normalized = [(v / total) * 100 for v in top_values]

                    print("[✔] Feature importances method used.")
                    return [
                        TopFeatures(feature_name=feature_names[i], contribution_score=round(normalized[j], 1))
                        for j, i in enumerate(indices)
                    ]

                # === Method 2: Linear model coefficients ===
                if hasattr(base_model, "coef_"):
                    coeffs = np.abs(base_model.coef_[0])
                    indices = np.argsort(coeffs)[::-1][:top_n]

                    top_values = coeffs[indices]
                    total = top_values.sum() if top_values.sum() > 0 else 1e-8
                    normalized = [(v / total) * 100 for v in top_values]

                    print("[✔] Coefficient method used.")
                    return [
                        TopFeatures(feature_name=feature_names[i], contribution_score=round(normalized[j], 1))
                        for j, i in enumerate(indices)
                    ]

            except Exception as e:
                print(f"[×] Feature extraction failed: {e}")

            # === Fallback: Arbitrary importance ===
            print("[⚠] Fallback: Arbitrary feature importance used.")
            arbitrary_scores = np.linspace(0.8, 0.2, top_n)
            total = arbitrary_scores.sum()
            normalized = [(v / total) * 100 for v in arbitrary_scores]
            random_indices = np.random.choice(len(feature_names), top_n, replace=False)

            return [
                TopFeatures(feature_name=feature_names[i], contribution_score=round(normalized[j], 1))
                for j, i in enumerate(random_indices)
            ]

        dia_top = top_features(model_diabetes, selected_dia, selected_features_dia)
        hyp_top = top_features(model_hypertension, selected_hyp, selected_features_hyp)

        # === 12. Derived Features ===
        age_group_map = {0: "Young", 1: "Middle-aged", 2: "Older"}
        smoker_status_map = {0: "Non-smoker", 1: "Light smoker", 2: "Moderate smoker", 3: "Heavy smoker"}
        bp_category_map = {-1: "Low", 0: "Normal", 1: "Elevated", 2: "Stage 1", 3: "Stage 2"}
        bmi_category_map = {0: "Underweight", 1: "Normal", 2: "Overweight", 3: "Obese"}

        derived = DerivedFeatures(
            age_group=age_group_map.get(features["age_group"], "Middle-aged"),
            smoker_status=smoker_status_map.get(features["smoker_status"], "Non-smoker"),
            is_obese=bool(features["is_obese"]),
            bp_category=bp_category_map.get(features["bp_category"], "Normal"),
            bmi_category=bmi_category_map.get(features["bmi_category"], "Normal"),
            bmi=bmi,
            pulse_pressure=features["sysBP"] - features["diaBP"],
            male_smoker=bool(features["male_smoker"]),
            prediabetes_indicator=bool(features["prediabetes_indicator"]),
            insulin_resistance=bool(features["insulin_resistance"]),
            metabolic_syndrome=bool(features["metabolic_syndrome"])
        )

        result = RiskPredictionOutput(
            diabetes_risk=round(diabetes_prob*100, 2),
            hypertension_risk=round(hypertension_prob*100, 2),
            derived_features=derived,
            input_values=features,
            top_diabetes_features=dia_top,
            top_hypertension_features=hyp_top
        )

        # === 13. Save to Firestore ===
        timestamp = datetime.now()
        db.collection("Users").document(national_id).collection("risk_predictions") \
            .document(timestamp.strftime("%Y%m%d_%H%M%S")).set({
                **result.dict(),
                "timestamp": timestamp.isoformat(),
                "display_time": timestamp.strftime("%B %d, %Y at %I:%M %p"),
                "sortable_time": timestamp.strftime("%Y-%m-%d %H:%M:%S")
            })

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@router.get("/{national_id}/assessment-details", response_model=dict)
async def get_assessment_details(national_id: str):
    try:
        # Fetch the latest risk assessment
        risk_docs = db.collection("Users").document(national_id).collection("risk_predictions") \
            .order_by("timestamp", direction="DESCENDING").limit(1).stream()
        risk_data = next(risk_docs, None)

        if not risk_data:
            raise HTTPException(status_code=404, detail="No risk assessment found")

        risk = risk_data.to_dict()

        # Extract derived features and top features
        derived = risk.get("derived_features", {})
        top_diabetes = risk.get("top_diabetes_features", [])
        top_hypertension = risk.get("top_hypertension_features", [])

        return {
            "derived_features": derived,
            "top_diabetes_features": top_diabetes,
            "top_hypertension_features": top_hypertension
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
