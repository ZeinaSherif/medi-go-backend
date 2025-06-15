from firebase_admin import storage, firestore
import json
import firebase_admin
from firebase_admin import credentials, storage
from deep_translator import GoogleTranslator
# Initialize Firebase Admin SDK with credentials
cred = credentials.Certificate(r"D:\Graduation Project\Final Graduation Project (4)\Final Graduation Project\medi-go-eb65e-firebase-adminsdk-fbsvc-f2861214c4.json")

# Initialize the app only if it hasn't been initialized yet
if not firebase_admin._apps:
    app = firebase_admin.initialize_app(cred, {
        'storageBucket': 'medi-go-eb65e.firebasestorage.app' 
})
db = firestore.client()
# Now we can access the bucket
bucket = storage.bucket() 
# English onboarding text
# English text
