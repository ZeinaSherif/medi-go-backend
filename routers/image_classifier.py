import io
import tensorflow as tf
import numpy as np
from PIL import Image
import requests
from io import BytesIO

# Load model once at startup
model = tf.keras.models.load_model("fixed_radiology_image_classifier.h5")

def classify_radiology_image(image_bytes, img_size=(224, 224)):
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        image = image.resize(img_size)
        img_array = np.expand_dims(np.array(image) / 255.0, axis=0)
        prediction = model.predict(img_array)
        confidence = float(prediction[0][0])
        is_valid = confidence > 0.5
        return {"is_valid": is_valid, "confidence": round(confidence, 4)}
    except Exception as e:
        return {"is_valid": None, "confidence": None, "error": str(e)}