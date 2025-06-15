# ✅ user_role.py — Role Management with Access Scope
from fastapi import APIRouter, HTTPException
from typing import List
from firebase_config import db
from models.schema import BaseModel

router = APIRouter(prefix="/roles", tags=["Roles"])

# --- Role Models ---
class RoleCreate(BaseModel):
    role_name: str
    role_id: int
    access_scope: dict

class RoleResponse(BaseModel):
    role_name: str
    role_id: int
    access_scope: dict

# --- Predefined Roles ---
ALLOWED_ROLES = {
    "patient": {
        "role_id": 1,
        "access_scope": {
            "view": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements", "medications", "lab_tests", "diagnosis", "rad_tests", "surgeries", "risk_predictions"],
            "edit": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements"]
        }
    },
    "hospital": {
        "role_id": 2,
        "access_scope": {
            "view": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements", "medications", "lab_tests", "diagnosis", "rad_tests", "surgeries", "risk_predictions"],
            "edit": ["measurements", "medications", "allergies", "lab_tests", "rad_tests", "diagnosis", "surgeries"]
        }
    },
    "laboratory": {
        "role_id": 3,
        "access_scope": {
            "view": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements", "medications", "lab_tests", "diagnosis", "rad_tests", "surgeries", "risk_predictions"],
            "edit": ["lab_tests"]
        }
    },
    "radiology": {
        "role_id": 4,
        "access_scope": {
            "view": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements", "medications", "lab_tests", "diagnosis", "rad_tests", "surgeries", "risk_predictions"],
            "edit": ["rad_tests"]
        }
    },
    "pharmacy": {
        "role_id": 5,
        "access_scope": {
            "view": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements", "medications", "lab_tests", "diagnosis", "rad_tests", "surgeries", "risk_predictions"],
            "edit": ["medications"]
        }
    },
    "clinic": {
        "role_id": 6,
        "access_scope": {
            "view": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements", "medications", "lab_tests", "diagnosis", "rad_tests", "surgeries", "risk_predictions"],
            "edit": ["measurements", "medications", "allergies", "diagnosis", "surgeries"]
        }
    },
    "visitor": {
        "role_id": 7,
        "access_scope": {
            "view": ["personal_details", "emergency_contacts", "allergies", "family_history", "measurements", "medications", "lab_tests", "diagnosis", "rad_tests", "surgeries", "risk_predictions"],
            "edit": []
        }
    }
}

@router.post("/roles/populate", response_model=List[RoleResponse])
async def populate_roles():
    """
    Populate the Roles collection in Firestore with predefined roles.
    """
    roles_list = []
    for role_name, data in ALLOWED_ROLES.items():
        role_data = {
            "role_name": role_name,
            "role_id": data["role_id"],
            "access_scope": data["access_scope"]
        }

        role_ref = db.collection("Roles").document(str(data["role_id"]))
        if not role_ref.get().exists:
            role_ref.set(role_data)
            roles_list.append(RoleResponse(**role_data))

    return roles_list

@router.get("/roles", response_model=List[RoleResponse])
async def get_all_roles():
    """
    Retrieve all roles from Firestore.
    """
    try:
        roles_ref = db.collection("Roles").stream()
        return [RoleResponse(**doc.to_dict()) for doc in roles_ref]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch roles: {str(e)}")