from fastapi import APIRouter, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
import smtplib
from email.message import EmailMessage
import os

router = APIRouter(prefix="", tags=["email"])

@router.post("/send-email")
async def send_email_with_attachment(
    to: str = Form(...),
    subject: str = Form(...),
    text: str = Form(...),
    image: UploadFile = Form(...)
):
    try:
        # Read image bytes
        image_bytes = await image.read()

        # Build email
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = os.getenv("EMAIL_FROM")  # e.g. your Gmail
        msg['To'] = to
        msg.set_content(text)

        # Add the image as attachment
        msg.add_attachment(image_bytes, maintype='image', subtype='png', filename="qr_code.png")

        # SMTP credentials (set in Render environment)
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        smtp_user = os.getenv("EMAIL_FROM")
        smtp_password = os.getenv("EMAIL_PASSWORD")

        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        return JSONResponse(status_code=200, content={"message": "✅ Email sent successfully"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
