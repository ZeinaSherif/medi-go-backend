import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud import storage as gcs_storage
from deep_translator import GoogleTranslator
import os

# === Step 1: Download the credentials file from Firebase Storage ===

# Define local path and GCS details
LOCAL_CREDENTIALS_PATH = "firebase_key.json"
GCS_BUCKET_NAME = "medi-go-eb65e.appspot.com"
GCS_BLOB_PATH = "models/medi-go-eb65e-firebase-adminsdk-fbsvc-f2861214c4.json"

# Create a Google Cloud Storage client
gcs_client = gcs_storage.Client()

# Access the bucket and blob
gcs_bucket = gcs_client.bucket(GCS_BUCKET_NAME)
blob = gcs_bucket.blob(GCS_BLOB_PATH)

# Download the blob to local file
blob.download_to_filename(LOCAL_CREDENTIALS_PATH)

# === Step 2: Initialize Firebase Admin SDK ===

cred = credentials.Certificate(LOCAL_CREDENTIALS_PATH)

if not firebase_admin._apps:
    app = firebase_admin.initialize_app(cred, {
        'storageBucket': GCS_BUCKET_NAME
    })

# === Step 3: Access Firestore and Storage ===

db = firestore.client()
bucket = storage.bucket()
