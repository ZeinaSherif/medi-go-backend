from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from pydantic import BaseModel
from datetime import datetime
from models.schema import QRCodeCreate,QRCodeResponse
from firebase_config import db, bucket
import uuid

router = APIRouter(prefix="/qrcode", tags=["QR Codes"])

# Firestore reference
def get_qr_code_doc_ref(user_id: str):
    return db.collection("Users").document(user_id).collection("QRCodeAccess").document("single_qr_code")

# Upload image to Firebase Storage
async def save_uploaded_image(user_id: str, file: UploadFile) -> str:
    try:
        file_bytes = await file.read()
        file_name = f"{user_id}_qrcode.png"
        blob = bucket.blob(f"qr_codes/{file_name}")

        download_token = str(uuid.uuid4())
        metadata = {"firebaseStorageDownloadTokens": download_token}

        blob.upload_from_string(
            file_bytes,
            content_type="image/png",
            predefined_acl='publicRead'
        )
        blob.metadata = metadata
        blob.patch()

        image_url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/"
            f"{blob.name.replace('/', '%2F')}?alt=media&token={download_token}"
        )
        return image_url

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload to storage failed: {str(e)}")
    
@router.post("/", response_model=QRCodeResponse)
async def create_and_save_qr_code(
    user_id: str = Form(...),
    last_accessed: str = Form(...),
    expiration_date: str = Form(...),
    qr_image: UploadFile = File(...),
    pdf_url: str = Form(...),  # PDF URL to store in the QR data
):
    try:
        # Upload QR image and get its URL
        image_url = await save_uploaded_image(user_id, qr_image)
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # Include PDF URL in the qr_data field
        qr_data = f"{pdf_url}"  # Store PDF URL in qr_data

        # Data to save in Firestore
        data = {
            "user_id": user_id,
            "last_accessed": timestamp,
            "expiration_date": expiration_date,
            "qr_image": image_url,
            "qr_data": qr_data,  # Save qr_data including the PDF URL
        }

        # Save the data in Firestore under the QRCodeAccess collection
        doc_ref = get_qr_code_doc_ref(user_id)
        doc_ref.set(data)

        # Return the response with the QR code data
        return QRCodeResponse(
            user_id=user_id,
            last_accessed=timestamp,
            expiration_date=expiration_date,
            qr_image=image_url,
            pdf_url=pdf_url,  # Include the PDF URL in the response
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/{user_id}", response_model=QRCodeResponse)
async def get_qr_code(user_id: str):
    try:
        doc_ref = get_qr_code_doc_ref(user_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise HTTPException(status_code=404, detail="QR code not found")

        data = doc.to_dict()
        return QRCodeResponse(**data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve QR: {str(e)}")