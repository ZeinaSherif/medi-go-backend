from fastapi import APIRouter, HTTPException
from firebase_config import db, bucket
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle
from io import BytesIO
import uuid
from datetime import datetime
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_CENTER
import requests
from PIL import Image
import tempfile
import os

router = APIRouter(prefix="/pdf", tags=["PDF Generator"])

def fetch_all_user_data(user_id: str):
    """Fetch all medical data for a user from Firestore"""
    user_ref = db.collection("Users").document(user_id)
    doc = user_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    data = {
        "basic_info": doc.to_dict(),
        "allergies": [],
        "biomarkers": [],
        "diagnoses": [],
        "emergency_contacts": [],
        "family_history": [],
        "hypertension": [],
        "measurements": None,
        "medications": [],
        "radiology": [],
        "surgeries": [],
        "risk_assessment": None  # ADD THIS LINE
    }
    
    # Fetch direct collections (not under ClinicalIndicators)
    direct_collections = [
        ("diagnoses", "diagnoses"),
        ("emergency_contacts", "emergency_contacts"),
        ("family_history", "family_history"),
        ("medications", "medications"),
        ("surgeries", "surgeries")
    ]
    
    for collection_name, path in direct_collections:
        try:
            coll_ref = user_ref.collection(path)
            docs = coll_ref.stream()
            data[collection_name] = [doc.to_dict() for doc in docs]
            print(f"Fetched {len(data[collection_name])} records from {collection_name}")
        except Exception as e:
            print(f"Error fetching {collection_name}: {str(e)}")
            continue
    
    # Fetch ClinicalIndicators subcollections
    clinical_indicators_ref = user_ref.collection("ClinicalIndicators")
    
    # Fetch measurements (document under ClinicalIndicators)
    try:
        measurements_doc = clinical_indicators_ref.document("measurements").get()
        if measurements_doc.exists:
            data["measurements"] = measurements_doc.to_dict()
            print(f"Fetched measurements data")
    except Exception as e:
        print(f"Error fetching measurements: {str(e)}")
    
    # Fetch subcollections under ClinicalIndicators
    clinical_subcollections = [
        ("allergies", "allergies"),
        ("biomarkers", "bloodbiomarkers"),
        ("hypertension", "Hypertension"),
        ("radiology", "radiology")
    ]
    
    for collection_name, subcoll_name in clinical_subcollections:
        try:
            # Try to get the Records subcollection
            records_ref = clinical_indicators_ref.document(subcoll_name).collection("Records")
            docs = list(records_ref.stream())
            
            if docs:
                data[collection_name] = [doc.to_dict() for doc in docs]
                print(f"Fetched {len(data[collection_name])} records from ClinicalIndicators/{subcoll_name}/Records")
            else:
                # If no Records subcollection, try direct documents under the subcollection
                direct_docs = list(clinical_indicators_ref.collection(subcoll_name).stream())
                if direct_docs:
                    data[collection_name] = [doc.to_dict() for doc in direct_docs]
                    print(f"Fetched {len(data[collection_name])} records from ClinicalIndicators/{subcoll_name}")
                else:
                    print(f"No data found in ClinicalIndicators/{subcoll_name}")
                    
        except Exception as e:
            print(f"Error fetching {collection_name} from ClinicalIndicators/{subcoll_name}: {str(e)}")
            continue
    # Fetch risk assessment data
    try:
        risk_docs = user_ref.collection("risk_predictions") \
            .order_by("timestamp", direction="DESCENDING").limit(1).stream()
        risk_data = next(risk_docs, None)
        if risk_data:
            data["risk_assessment"] = risk_data.to_dict()
            print(f"Fetched risk assessment data")
    except Exception as e:
        print(f"Error fetching risk assessment: {str(e)}")
    # Debug: Print data summary
    for key, value in data.items():
        if isinstance(value, list):
            print(f"{key}: {len(value)} items")
        elif isinstance(value, dict):
            print(f"{key}: {len(value)} fields")
        else:
            print(f"{key}: {type(value)}")
    
    return data

def download_and_process_image(image_url, max_width=4*inch, max_height=3*inch):
    """Download image from URL and process it for PDF inclusion - IMPROVED QUALITY"""
    try:
        if not image_url or not isinstance(image_url, str):
            return None
            
        # Skip if it's not a valid URL
        if not (image_url.startswith('http://') or image_url.startswith('https://')):
            return None
            
        # Download image
        response = requests.get(image_url, timeout=10, stream=True)
        response.raise_for_status()
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        # Process image with PIL - IMPROVED FOR BETTER QUALITY
        with Image.open(temp_path) as img:
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Get original dimensions
            original_width, original_height = img.size
            aspect_ratio = original_width / original_height
            
            # Calculate new dimensions - KEEP LARGER SIZES
            if aspect_ratio > 1:  # Landscape
                new_width = min(max_width, original_width * 0.8)  # Allow larger images
                new_height = new_width / aspect_ratio
            else:  # Portrait or square
                new_height = min(max_height, original_height * 0.8)  # Allow larger images
                new_width = new_height * aspect_ratio
            
            # Only resize if the image is significantly larger than target
            if original_width > max_width * 1.5 or original_height > max_height * 1.5:
                # Resize with high quality resampling
                img_resized = img.resize((int(new_width), int(new_height)), Image.Resampling.LANCZOS)
            else:
                # Keep original size if it's not too large
                img_resized = img
                new_width = original_width
                new_height = original_height
            
            # Save with higher quality
            processed_path = temp_path.replace('.jpg', '_processed.jpg')
            img_resized.save(processed_path, 'JPEG', quality=95, optimize=False)  # Higher quality
        
        # Clean up original temp file
        os.unlink(temp_path)
        
        return {
            'path': processed_path,
            'width': new_width,
            'height': new_height
        }
        
    except Exception as e:
        print(f"Error processing image {image_url}: {str(e)}")
        return None

def draw_image_if_available(c, image_url, x, y, max_width=4*inch, max_height=3*inch, caption=""):
    if not image_url:
        return y

    image_info = download_and_process_image(image_url, max_width, max_height)
    if not image_info:
        return y

    try:
        actual_width = min(image_info['width'], max_width)
        actual_height = min(image_info['height'], max_height)
        if image_info['width'] > max_width or image_info['height'] > max_height:
            scale = min(max_width / image_info['width'], max_height / image_info['height'])
            actual_width *= scale
            actual_height *= scale

        if y - actual_height < 1.5 * inch:
            draw_footer(c, c.getPageNumber())
            c.showPage()
            y = 10.5 * inch

        draw_x = x
        if actual_width < max_width:
            draw_x = x + (max_width - actual_width) / 2

        c.drawImage(image_info['path'], draw_x, y - actual_height,
                    width=actual_width, height=actual_height)

        if caption:
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.HexColor("#4A5568"))
            caption_width = c.stringWidth(caption, "Helvetica", 10)
            caption_x = x + (max_width - caption_width) / 2
            c.drawString(caption_x, y - actual_height - 0.25 * inch, caption)

        os.unlink(image_info['path'])

        return y - actual_height - (0.4 * inch if caption else 0.3 * inch)

    except Exception as e:
        print(f"Error drawing image: {str(e)}")
        if image_info and os.path.exists(image_info['path']):
            os.unlink(image_info['path'])
        return y



def draw_patient_info_card(c, user_data, y_pos):
    """Draw an enhanced patient information card with profile photo"""
    card_x = 1 * inch
    card_y = y_pos - 1.8 * inch  # Made taller for photo
    card_width = 6.5 * inch
    card_height = 1.5 * inch  # Increased height
    
    # Card shadow (offset background)
    c.setFillColor(colors.HexColor("#E2E8F0"))
    c.rect(card_x + 0.05 * inch, card_y - 0.05 * inch, card_width, card_height, fill=1, stroke=0)
    
    # Main card background
    c.setFillColor(colors.HexColor("#F7FAFC"))
    c.rect(card_x, card_y, card_width, card_height, fill=1, stroke=0)
    
    # Card border
    c.setStrokeColor(colors.HexColor("#2C5282"))
    c.setLineWidth(1.5)
    c.rect(card_x, card_y, card_width, card_height, fill=0, stroke=1)
    
    # Left accent bar
    c.setFillColor(colors.HexColor("#2C5282"))
    c.rect(card_x, card_y, 0.2 * inch, card_height, fill=1, stroke=0)
    
    # Profile photo (if available)
    profile_photo_url = user_data.get("profile_photo")
    photo_x = card_x + 0.4 * inch
    photo_y = card_y + 0.25 * inch
    
    if profile_photo_url:
        photo_bottom = draw_image_if_available(c, profile_photo_url, photo_x, photo_y + 1*inch, 
                                             max_width=1*inch, max_height=1*inch)
        text_start_x = photo_x + 1.2 * inch  # Start text after photo
    else:
        # Default avatar placeholder
        c.setFillColor(colors.HexColor("#CBD5E0"))
        c.circle(photo_x + 0.5*inch, photo_y + 0.5*inch, 0.4*inch, fill=1)
        c.setFillColor(colors.HexColor("#718096"))
        c.circle(photo_x + 0.5*inch, photo_y + 0.7*inch, 0.15*inch, fill=1)  # Head
        c.ellipse(photo_x + 0.2*inch, photo_y + 0.1*inch, photo_x + 0.8*inch, photo_y + 0.5*inch, fill=1)  # Body
        text_start_x = photo_x + 1.2 * inch
    
    # Patient name
    patient_name = user_data.get("full_name", "Unknown Patient")
    c.setFillColor(colors.HexColor("#1A365D"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(text_start_x, card_y + 1.1 * inch, patient_name)
    
    # ID and basic info
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#4A5568"))
    
    info_lines = [
        f"ID: {user_data.get('national_id', 'N/A')}",
        f"Age: {user_data.get('age', 'N/A')} | Gender: {user_data.get('gender', 'N/A').title()}",
        f"Blood Group: {user_data.get('blood_group', 'N/A')}",
        f"Phone: {user_data.get('phone_number', 'N/A')}"
    ]
    
    for i, line in enumerate(info_lines):
        c.drawString(text_start_x, card_y + 0.8*inch - (i * 0.15*inch), line)
    
    # Report date (right aligned)
    report_date = datetime.now().strftime('%B %d, %Y')
    date_text = f"Report Date: {report_date}"
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#2C5282"))
    date_width = c.stringWidth(date_text, "Helvetica-Bold", 10)
    c.drawString(card_x + card_width - date_width - 0.3 * inch, card_y + 0.1 * inch, date_text)


def draw_section_header(c, title, y_pos, icon="", min_space_needed=1.5*inch):
    if y_pos - min_space_needed < 1.5 * inch:
        draw_footer(c, c.getPageNumber())
        c.showPage()
        y_pos = 10.5 * inch

    c.setFillColor(colors.HexColor("#EDF2F7"))
    c.rect(0.75 * inch, y_pos - 0.05 * inch, 7 * inch, 0.4 * inch, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#2C5282"))
    c.rect(0.75 * inch, y_pos - 0.05 * inch, 0.1 * inch, 0.4 * inch, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#1A365D"))
    c.setFont("Helvetica-Bold", 14)
    try:
        c.drawString(1 * inch, y_pos + 0.1 * inch, f"{icon} {title}")
    except:
        c.drawString(1 * inch, y_pos + 0.1 * inch, title)

    return y_pos - 0.7 * inch

def create_enhanced_table(c, data, y_pos, table_type="data"):
    if not data:
        return y_pos

    table_data = []
    if table_type == "data":
        for key, value in data.items():
            if value is None or key in ["id", "user_id", "timestamp", "password"]:
                continue
            table_data.append([key.replace('_', ' ').title(), str(value) if value != "" else "Not specified"])
    else:
        for item in data:
            for key, value in item.items():
                if key in ["id", "user_id", "timestamp", "added_by"] or value is None:
                    continue
                table_data.append([key.replace('_', ' ').title(), str(value) if value != "" else "Not specified"])
            if len(data) > 1:
                table_data.append(["", ""])

    if not table_data:
        return y_pos

    row_height = 0.22 * inch
    estimated_height = len(table_data) * row_height + 0.3 * inch
    if y_pos - estimated_height < 1.2 * inch:
        draw_footer(c, c.getPageNumber())
        c.showPage()
        y_pos = 10.5 * inch

    table = Table(table_data, colWidths=[2.2 * inch, 4.5 * inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#2C5282")),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor("#2D3748")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
    ]))

    table.wrapOn(c, 6.7 * inch, 8 * inch)
    table.drawOn(c, 0.9 * inch, y_pos - table._height)
    return y_pos - table._height - 0.3 * inch

def create_risk_assessment_table(c, risk_data, y_pos):
    """Create a specialized table for risk assessment with visual indicators"""
    if not risk_data:
        return y_pos
    
    # Risk scores section
    c.setFillColor(colors.HexColor("#4A5568"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y_pos, "Risk Scores:")
    y_pos -= 0.15 * inch
    
    # Create risk scores table
    diabetes_risk = risk_data.get('diabetes_risk', 0)
    hypertension_risk = risk_data.get('hypertension_risk', 0)
    def get_risk_level(risk_score):
        if risk_score < 20:
            return "Low", colors.green
        elif risk_score < 50:
            return "Moderate", colors.orange
        else:
            return "High", colors.red
    
    diabetes_level, diabetes_color = get_risk_level(diabetes_risk)
    hypertension_level, hypertension_color = get_risk_level(hypertension_risk)
    
    risk_scores_data = [
        ["Risk Type", "Score (%)", "Level"],
        ["Diabetes Risk", f"{diabetes_risk}%", diabetes_level],
        ["Hypertension Risk", f"{hypertension_risk}%", hypertension_level]
    ]
    
    risk_table = Table(risk_scores_data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
    risk_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C5282")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#2D3748")),
        ('BACKGROUND', (2, 1), (2, 1), diabetes_color),
        ('BACKGROUND', (2, 2), (2, 2), hypertension_color),
        ('TEXTCOLOR', (2, 1), (2, 2), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    risk_table.wrapOn(c, 5 * inch, 4 * inch)
    risk_table.drawOn(c, 1 * inch, y_pos - risk_table._height)
    y_pos -= risk_table._height + 0.4 * inch
    
    # Top Contributing Features
    c.setFillColor(colors.HexColor("#4A5568"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y_pos, "Top Contributing Features:")
    y_pos -= 0.15 * inch
    
    # Diabetes features
    diabetes_features = risk_data.get('top_diabetes_features', [])
    if diabetes_features:
        c.setFillColor(colors.HexColor("#2C5282"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(1 * inch, y_pos, "For Diabetes Risk:")
        y_pos -= 0.2 * inch
        
        diabetes_data = [["Feature", "Contribution (%)"]]
        for feature in diabetes_features:
            diabetes_data.append([
                feature.get('feature_name', 'N/A').replace('_', ' ').title(),
                f"{feature.get('contribution_score', 0)}%"
            ])
        
        diabetes_table = Table(diabetes_data, colWidths=[3*inch, 1.5*inch])
        diabetes_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E53E3E")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#2D3748")),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        diabetes_table.wrapOn(c, 4.5 * inch, 4 * inch)
        diabetes_table.drawOn(c, 1 * inch, y_pos - diabetes_table._height)
        y_pos -= diabetes_table._height + 0.3 * inch
    
    # Hypertension features
    hypertension_features = risk_data.get('top_hypertension_features', [])
    if hypertension_features:
        c.setFillColor(colors.HexColor("#2C5282"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(1 * inch, y_pos, "For Hypertension Risk:")
        y_pos -= 0.2 * inch
        
        hypertension_data = [["Feature", "Contribution (%)"]]
        for feature in hypertension_features:
            hypertension_data.append([
                feature.get('feature_name', 'N/A').replace('_', ' ').title(),
                f"{feature.get('contribution_score', 0)}%"
            ])
        
        hypertension_table = Table(hypertension_data, colWidths=[3*inch, 1.5*inch])
        hypertension_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#D53F8C")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#2D3748")),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        
        hypertension_table.wrapOn(c, 4.5 * inch, 4 * inch)
        hypertension_table.drawOn(c, 1 * inch, y_pos - hypertension_table._height)
        y_pos -= hypertension_table._height + 0.3 * inch
    
    # Derived features summary
    derived_features = risk_data.get('derived_features', {})
    if derived_features:
        c.setFillColor(colors.HexColor("#4A5568"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(1 * inch, y_pos, "Health Profile Summary:")
        y_pos -= 0.2 * inch
        
        # Format derived features for display
        summary_data = []
        for key, value in derived_features.items():
            if key in ['bmi', 'pulse_pressure']:
                summary_data.append([key.replace('_', ' ').title(), f"{value:.1f}"])
            elif isinstance(value, bool):
                summary_data.append([key.replace('_', ' ').title(), "Yes" if value else "No"])
            else:
                summary_data.append([key.replace('_', ' ').title(), str(value)])
        
        if summary_data:
            summary_table = Table(summary_data, colWidths=[2.5*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#2C5282")),
                ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor("#2D3748")),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            
            summary_table.wrapOn(c, 4.5 * inch, 6 * inch)
            summary_table.drawOn(c, 1 * inch, y_pos - summary_table._height)
            y_pos -= summary_table._height + 0.3 * inch
    
    return y_pos

def create_medication_table(c, medications, y_pos):
    if not medications:
        return y_pos

    table_data = [["Medication", "Dosage", "Frequency", "Prescribing Doctor"]]
    for med in medications:
        row = [
            med.get('scientific_name', med.get('trade_name', 'N/A')),
            med.get('dosage', 'N/A'),
            med.get('frequency', 'N/A'),
            med.get('prescribing_doctor', 'N/A')
        ]
        table_data.append(row)

    estimated_height = len(table_data) * 0.3 * inch + 0.4 * inch
    if y_pos - estimated_height < 1.5 * inch:
        draw_footer(c, c.getPageNumber())
        c.showPage()
        y_pos = 10.5 * inch

    table = Table(table_data, colWidths=[1.8 * inch, 1.3 * inch, 1.3 * inch, 2.3 * inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C5282")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#2D3748")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FA")]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    table.wrapOn(c, 6.7 * inch, 8 * inch)
    table.drawOn(c, 0.9 * inch, y_pos - table._height)
    return y_pos - table._height - 0.3 * inch

def should_start_new_page_for_section(section_data, section_type, current_y):
    """Determine if a section needs a new page based on its content"""
    # Sections that definitely need their own page due to images/complexity
    complex_sections = ["biomarkers", "radiology", "risk_assessment"]
    
    if section_type in complex_sections:
        return True
    
    # For simple sections, check if they can fit on current page
    if section_type == "medications":
        estimated_space = len(section_data) * 0.3 * inch + 1 * inch
    else:
        estimated_space = len(section_data) * 0.25 * inch + 1 * inch
    
    # Only start new page if section won't fit
    return current_y - estimated_space < 2 * inch


def create_biomarker_table_with_images(c, biomarkers, y_pos):
    if not biomarkers:
        return y_pos

    for i, test in enumerate(biomarkers):
        # Ensure enough space before drawing new biomarker block
        if y_pos < 4 * inch:
            draw_footer(c, c.getPageNumber())
            c.showPage()
            y_pos = 10.5 * inch

        c.setFillColor(colors.HexColor("#2C5282"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, y_pos, f"Blood Test #{i+1}")
        y_pos -= 0.15 * inch

        # Draw test info table
        test_data = []
        for key, value in test.items():
            if key not in ["results", "images", "image_url"] and value:
                test_data.append([key.replace('_', ' ').title(), str(value)])

        table = Table(test_data, colWidths=[1.8 * inch, 4 * inch])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#2C5282")),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor("#2D3748")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0"))
        ]))

        table.wrapOn(c, 5.8 * inch, 6 * inch)
        if y_pos - table._height < 1.5 * inch:
            draw_footer(c, c.getPageNumber())
            c.showPage()
            y_pos = 10.5 * inch
        table.drawOn(c, 1 * inch, y_pos - table._height)
        y_pos -= table._height + 0.2 * inch

        # Draw results
        results = test.get("results", [])
        if results:
            c.setFillColor(colors.HexColor("#4A5568"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(1 * inch, y_pos, "Test Results:")
            y_pos -= 0.2 * inch

            results_data = [["Test Item", "Value", "Unit", "Reference Range", "Status"]]
            for result in results:
                status = "⚠️ Abnormal" if result.get("flag") else "✓ Normal"
                results_data.append([
                    result.get('item', 'N/A'),
                    str(result.get('value', 'N/A')),
                    result.get('unit', ''),
                    result.get('reference_range', 'N/A'),
                    status
                ])

            results_table = Table(results_data, colWidths=[1.5*inch, 0.8*inch, 0.6*inch, 1.2*inch, 1*inch])
            results_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C5282")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ]))

            results_table.wrapOn(c, 5.1 * inch, 6 * inch)
            if y_pos - results_table._height < 1.5 * inch:
                draw_footer(c, c.getPageNumber())
                c.showPage()
                y_pos = 10.5 * inch
            results_table.drawOn(c, 1 * inch, y_pos - results_table._height)
            y_pos -= results_table._height + 0.2 * inch

        # Draw Images
        image_urls = []
        if test.get("image_url"):
            image_urls.append(test["image_url"])
        if test.get("images"):
            image_urls.extend(test["images"])

        if image_urls:
            c.setFillColor(colors.HexColor("#4A5568"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(1 * inch, y_pos, "Test Images:")
            y_pos -= 0.15 * inch

            for idx, img_url in enumerate(image_urls):
                if y_pos < 4 * inch:
                    draw_footer(c, c.getPageNumber())
                    c.showPage()
                    y_pos = 10.5 * inch

                y_pos = draw_image_if_available(c, img_url, 2 * inch, y_pos, caption=f"Test Image {idx+1}")
                y_pos -= 0.2 * inch

        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(1)
        c.line(1 * inch, y_pos, 7.5 * inch, y_pos)
        y_pos -= 0.15 * inch

    return y_pos



def create_radiology_table_with_images(c, radiology_data, y_pos):
    if not radiology_data:
        return y_pos

    for i, exam in enumerate(radiology_data):
        if y_pos < 4 * inch:
            draw_footer(c, c.getPageNumber())
            c.showPage()
            y_pos = 10.5 * inch

        c.setFillColor(colors.HexColor("#2C5282"))
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, y_pos, f"Radiology Exam #{i+1}")
        y_pos -= 0.15 * inch

        exam_data = []
        for key, value in exam.items():
            if key not in ["images", "image_url", "report_images"] and value:
                exam_data.append([key.replace('_', ' ').title(), str(value)])

        table = Table(exam_data, colWidths=[1.8 * inch, 4 * inch])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#2C5282")),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor("#2D3748")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0"))
        ]))

        table.wrapOn(c, 5.8 * inch, 6 * inch)
        if y_pos - table._height < 1.5 * inch:
            draw_footer(c, c.getPageNumber())
            c.showPage()
            y_pos = 10.5 * inch
        table.drawOn(c, 1 * inch, y_pos - table._height)
        y_pos -= table._height + 0.3 * inch

        # Images
        image_urls = []
        for key in ["image_url", "images", "report_images"]:
            if isinstance(exam.get(key), list):
                image_urls.extend(exam.get(key))
            elif exam.get(key):
                image_urls.append(exam.get(key))

        if image_urls:
            c.setFillColor(colors.HexColor("#4A5568"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(1 * inch, y_pos, "Radiology Images:")
            y_pos -= 0.15 * inch

            for idx, img_url in enumerate(image_urls):
                if y_pos < 4 * inch:
                    draw_footer(c, c.getPageNumber())
                    c.showPage()
                    y_pos = 10.5 * inch

                y_pos = draw_image_if_available(c, img_url, 2 * inch, y_pos, caption=f"Radiology Image {idx+1}")
                y_pos -= 0.2 * inch

        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(1)
        c.line(1 * inch, y_pos, 7.5 * inch, y_pos)
        y_pos -= 0.15 * inch

    return y_pos

    """Format biomarker data for better display"""
    formatted = []
    for test in biomarkers:
        entry = {
            "test_date": test.get("extracted_date", test.get("added_date", "N/A")),
            "facility": test.get("added_by_name", test.get("added_by", "N/A")),
            "test_type": test.get("test_type", "Blood Test")
        }
        
        # Format results in a more readable way
        results_summary = []
        for result in test.get("results", []):
            item = result.get('item', 'N/A')
            value = result.get('value', 'N/A')
            unit = result.get('unit', '')
            flag = " ⚠️" if result.get("flag") else " ✓"
            
            result_text = f"{item}: {value} {unit}{flag}"
            results_summary.append(result_text)
        
        entry["results"] = "; ".join(results_summary[:3])  # Limit to first 3 results
        if len(test.get("results", [])) > 3:
            entry["results"] += f" (and {len(test.get('results', [])) - 3} more...)"
        
        formatted.append(entry)
    return formatted

def draw_footer(c, page_num):
    """Draw professional footer"""
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor("#718096"))
    
    # Left side - generation info
    footer_text = f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
    c.drawString(0.75 * inch, 0.5 * inch, footer_text)
    
    # Center - confidentiality notice
    conf_text = "CONFIDENTIAL MEDICAL DOCUMENT"
    conf_width = c.stringWidth(conf_text, "Helvetica", 9)
    c.drawString((letter[0] - conf_width) / 2, 0.5 * inch, conf_text)
    
    # Right side - page number
    c.drawRightString(7.75 * inch, 0.5 * inch, f"Page {page_num}")
    
    # Footer line
    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.setLineWidth(0.5)
    c.line(0.75 * inch, 0.75 * inch, 7.75 * inch, 0.75 * inch)
    
def draw_header_with_logo(c, y_pos):
    """Draw professional header with medical cross and title"""
    # Ensure we have enough top margin
    if y_pos > 10.5 * inch:
        y_pos = 10.5 * inch
    
   
    # Main title
    c.setFillColor(colors.HexColor("#1A365D"))
    c.setFont("Helvetica-Bold", 24)
    c.drawString(1.5 * inch, y_pos - 0.6 * inch, "MEDICAL REPORT")
    
    # Subtitle
    c.setFillColor(colors.HexColor("#4A5568"))
    c.setFont("Helvetica", 12)
    c.drawString(1.5 * inch, y_pos - 0.9 * inch, "Comprehensive Health Summary")
    
    # Decorative line
    c.setStrokeColor(colors.HexColor("#2C5282"))
    c.setLineWidth(2)
    c.line(1 * inch, y_pos - 1.1 * inch, 7.5 * inch, y_pos - 1.1 * inch)
    
    # Return the new y_position after drawing the header
    return y_pos - 1.3 * inch

def draw_patient_info_card(c, user_data, y_pos):
    """Draw an enhanced patient information card"""
    card_x = 1 * inch
    card_y = y_pos - 1.5 * inch
    card_width = 6.5 * inch
    card_height = 1.2 * inch
    
    # Card shadow (offset background)
    c.setFillColor(colors.HexColor("#E2E8F0"))
    c.rect(card_x + 0.05 * inch, card_y - 0.05 * inch, card_width, card_height, fill=1, stroke=0)
    
    # Main card background
    c.setFillColor(colors.HexColor("#F7FAFC"))
    c.rect(card_x, card_y, card_width, card_height, fill=1, stroke=0)
    
    # Card border
    c.setStrokeColor(colors.HexColor("#2C5282"))
    c.setLineWidth(1.5)
    c.rect(card_x, card_y, card_width, card_height, fill=0, stroke=1)
    
    # Left accent bar
    c.setFillColor(colors.HexColor("#2C5282"))
    c.rect(card_x, card_y, 0.2 * inch, card_height, fill=1, stroke=0)
    
    # Patient name
    patient_name = user_data.get("full_name", "Unknown Patient")
    c.setFillColor(colors.HexColor("#1A365D"))
    c.setFont("Helvetica-Bold", 18)
    name_width = c.stringWidth(patient_name, "Helvetica-Bold", 18)
    c.drawString(card_x + (card_width - name_width) / 2, card_y + 0.75 * inch, patient_name)
    
    # ID and Date row
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor("#4A5568"))
    
    # Patient ID (left aligned)
    id_text = f"ID: {user_data.get('national_id', 'N/A')}"
    c.drawString(card_x + 0.4 * inch, card_y + 0.4 * inch, id_text)
    
    # Age and Gender (center)
    age = user_data.get('age', 'N/A')
    gender = user_data.get('gender', 'N/A')
    center_text = f"Age: {age} | Gender: {gender.title()}"
    center_width = c.stringWidth(center_text, "Helvetica-Bold", 11)
    c.drawString(card_x + (card_width - center_width) / 2, card_y + 0.4 * inch, center_text)
    
    # Report date (right aligned)
    report_date = datetime.now().strftime('%B %d, %Y')
    date_text = f"Report Date: {report_date}"
    date_width = c.stringWidth(date_text, "Helvetica-Bold", 11)
    c.drawString(card_x + card_width - date_width - 0.3 * inch, card_y + 0.4 * inch, date_text)
    
    # Contact info (bottom center)
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#718096"))
    contact = user_data.get('phone_number', '')
    email = user_data.get('email', '')
    contact_text = f"📞 {contact} | ✉ {email}"
    contact_width = c.stringWidth(contact_text, "Helvetica", 10)
    c.drawString(card_x + (card_width - contact_width) / 2, card_y + 0.1 * inch, contact_text)

@router.get("/{user_id}")
async def generate_medical_report_pdf(user_id: str):
    try:
        # Fetch all user data
        data = fetch_all_user_data(user_id)
        
        # Create in-memory buffer
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        page_num = 1
        
        # Page 1 - Header and Basic Info
        draw_header_with_logo(c, 10.5 * inch)
        draw_patient_info_card(c, data["basic_info"], 10.5 * inch)
        y_position = 8.5 * inch

        # Basic Information
        if data["basic_info"]:
            filtered_info = {
                k: v for k, v in data["basic_info"].items() 
                if k not in ["full_name", "national_id", "age", "gender", "phone_number", "email", "password"]
            }
            if filtered_info:
                y_position = draw_section_header(c, "Personal Information", y_position, "👤", 1.5*inch)
                y_position = create_enhanced_table(c, filtered_info, y_position)
        
        # Measurements
        if data["measurements"]:
            estimated_space = len(data["measurements"]) * 0.25 * inch + 1.5 * inch
            if y_position - estimated_space > 1.5 * inch:
                y_position = draw_section_header(c, "Body Measurements", y_position, "📏", estimated_space)
                y_position = create_enhanced_table(c, data["measurements"], y_position)
            else:
                draw_footer(c, page_num)
                c.showPage()
                page_num += 1
                y_position = 10.5 * inch
                y_position = draw_section_header(c, "Body Measurements", y_position, "📏", estimated_space)
                y_position = create_enhanced_table(c, data["measurements"], y_position)
        
        # Emergency Contacts
        if data["emergency_contacts"]:
            estimated_space = len(data["emergency_contacts"]) * 0.3 * inch + 1.5 * inch
            if y_position - estimated_space < 1.5 * inch:
                draw_footer(c, page_num)
                c.showPage()
                page_num += 1
                y_position = 10.5 * inch
            
            y_position = draw_section_header(c, "Emergency Contacts", y_position, "🚨", estimated_space)
            y_position = create_enhanced_table(c, data["emergency_contacts"], y_position, "list")
        
        draw_footer(c, page_num)
        
        # Add remaining sections
        page_num = generate_sections_optimized(c, data, page_num)
        
        # Save the PDF
        c.save()
        buffer.seek(0)
        
        # Upload to Firebase Storage
        file_name = f"{user_id}_medical_report.pdf"
        blob = bucket.blob(f"pdfs/{file_name}")
        token = str(uuid.uuid4())
        blob.metadata = {"firebaseStorageDownloadTokens": token}
        blob.upload_from_file(buffer, content_type='application/pdf')
        blob.patch()
        
        # Generate public URL
        pdf_url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/"
            f"{blob.name.replace('/', '%2F')}?alt=media&token={token}"
        )
        
        return {"pdf_url": pdf_url}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")


def generate_sections_optimized(c, data, page_num):
    """Generate sections with optimized page usage"""
    y_position = 8.5 * inch

    simple_sections = [
        ("Allergies", data["allergies"], "⚠️", "standard"),
        ("Medical Diagnoses", data["diagnoses"], "🩺", "standard"),
        ("Blood Pressure Records", data["hypertension"], "❤️", "standard"),
        ("Surgical History", data["surgeries"], "🏥", "standard"),
        ("Family Medical History", data["family_history"], "👨‍👩‍👧‍👦", "standard")
    ]
    
    medium_sections = [
        ("Current Medications", data["medications"], "💊", "medications")
    ]
    
    complex_sections = [
        ("Risk Assessment", data["risk_assessment"], "📊", "risk_assessment"),
        ("Blood Test Results", data["biomarkers"], "🔬", "biomarkers"),
        ("Radiology Reports", data["radiology"], "📡", "radiology")
    ]
    
    # Simple Sections
    for section_title, section_data, icon, section_type in simple_sections:
        if section_data:
            estimated_space = len(section_data) * 0.25 * inch + 1.5 * inch
            if y_position - estimated_space < 1.5 * inch:
                draw_footer(c, page_num)
                c.showPage()
                page_num += 1
                y_position = 10.5 * inch
                
            y_position = draw_section_header(c, section_title, y_position, icon, estimated_space)
            y_position = create_enhanced_table(c, section_data, y_position, "list")

    # Medium Sections
    for section_title, section_data, icon, section_type in medium_sections:
        if section_data:
            estimated_space = len(section_data) * 0.35 * inch + 1.5 * inch
            if y_position - estimated_space < 2 * inch:
                draw_footer(c, page_num)
                c.showPage()
                page_num += 1
                y_position = 10.5 * inch
                
            y_position = draw_section_header(c, section_title, y_position, icon, estimated_space)
            y_position = create_medication_table(c, section_data, y_position)

    # Complex Sections
    for section_title, section_data, icon, section_type in complex_sections:
        if section_data:
            draw_footer(c, page_num)
            c.showPage()
            page_num += 1
            y_position = 10.5 * inch
            y_position = draw_section_header(c, section_title, y_position, icon, 4 * inch)
            
            if section_type == "biomarkers":
                y_position = create_biomarker_table_with_images(c, section_data, y_position)
            elif section_type == "radiology":
                y_position = create_radiology_table_with_images(c, section_data, y_position)
            elif section_type == "risk_assessment":
                y_position = create_risk_assessment_table(c, section_data, y_position)
            
            draw_footer(c, page_num)

    return page_num
