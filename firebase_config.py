import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud import storage as gcs_storage
from deep_translator import GoogleTranslator
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Step 1: Download the credentials file from Firebase Storage ===
# Define local path and GCS details
LOCAL_CREDENTIALS_PATH = "firebase_key.json"
GCS_BUCKET_NAME = "medi-go-eb65e.firebasestorage.app"  # Fixed bucket name
GCS_BLOB_PATH = "models/medi-go-eb65e-firebase-adminsdk-fbsvc-f2861214c4.json"

try:
    # Create a Google Cloud Storage client
    gcs_client = gcs_storage.Client()
    
    # Access the bucket and blob
    gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)
    blob = gcs_bucket.blob(GCS_BLOB_PATH)
    
    # Check if blob exists before downloading
    if not blob.exists():
        raise FileNotFoundError(f"Blob {GCS_BLOB_PATH} does not exist in bucket {GCS_BUCKET_NAME}")
    
    # Download the blob to local file
    logger.info(f"Downloading Firebase credentials from {GCS_BUCKET_NAME}/{GCS_BLOB_PATH}")
    blob.download_to_filename(LOCAL_CREDENTIALS_PATH)
    logger.info("Firebase credentials downloaded successfully")
    
    # === Step 2: Initialize Firebase Admin SDK ===
    cred = credentials.Certificate(LOCAL_CREDENTIALS_PATH)
    
except Exception as e:
    logger.error(f"Failed to download Firebase credentials: {e}")
    logger.info("Falling back to Application Default Credentials")
    # Use Application Default Credentials as fallback
    cred = credentials.ApplicationDefault()

# Initialize Firebase app if not already initialized
if not firebase_admin._apps:
    app = firebase_admin.initialize_app(cred, {
        'storageBucket': 'medi-go-eb65e.firebasestorage.app'  # Use the correct bucket name
    })
    logger.info("Firebase Admin SDK initialized successfully")

# === Step 3: Access Firestore and Storage ===
db = firestore.client()
bucket = storage.bucket()

logger.info("Firebase configuration completed")
