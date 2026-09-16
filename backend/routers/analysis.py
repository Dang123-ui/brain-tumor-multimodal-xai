import base64
import datetime
import os
import textwrap
from io import BytesIO
from typing import Any, List

import cv2
import numpy as np
import pydicom
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from PIL import Image, ImageDraw, ImageFile, ImageFont, ImageOps
from sqlalchemy.orm import Session

import crud
import models
import schemas
from database import get_db
from services.gemini_service import GeminiXaiExplanationService
from services.rag_service import get_xai_rag_service
from review_utils import classification_review_state
from utils import get_current_user, minio_client

router = APIRouter(tags=["Analysis & XAI"])
BUCKET_NAME = "medical-data"
ImageFile.LOAD_TRUNCATED_IMAGES = True
LABEL_MAP = {
    "class_0": "Glioma",
    "class_1": "Meningioma",
    "class_2": "Pituitary tumor",
}

PROGNOSIS_ONLY_KEYS = {
    "risk_score",
    "risk_group",
    "survival_curve_data",
    "fusion_attention",
    "rna_xai",
    "multimodal_xai_explanation",
    "xai_explanation",
    "multimodal_risk_xai_path",
    "multimodal_risk_xai_meta_path",
    "multimodal_gradcam_heatmap_path",
    "multimodal_gradcam_plus_heatmap_path",
    "multimodal_layercam_heatmap_path",
}

NAVY = (18, 42, 66)
TEAL = (38, 120, 133)
RED = (177, 58, 58)
ORANGE = (185, 117, 45)
LIGHT_GRAY = (242, 245, 247)
BORDER = (220, 226, 230)
TEXT = (33, 37, 41)
TEXT_MUTED = (108, 117, 125)

# ── Brand/UI Colors ──
WHITE = (255, 255, 255)
SLATE_100 = (241, 245, 249)
SLATE_500 = (100, 116, 139)
SLATE_800 = (30, 41, 59)
SLATE_900 = (15, 23, 42)
RED_500 = (239, 68, 68)


def _merge_prognosis_only(base_payload: dict, prognosis_payload: dict | None) -> dict:
    """Add prognosis outputs without overwriting MRI core detection/seg/class fields."""
    merged = dict(base_payload or {})
    if not prognosis_payload:
        return merged
    for key in PROGNOSIS_ONLY_KEYS:
        if key in prognosis_payload and prognosis_payload.get(key) is not None:
            merged[key] = prognosis_payload.get(key)
    return merged


def _get_presigned_url(file_path: str | None) -> str | None:
    if not file_path:
        return None
    try:
        bucket_name, object_name = _parse_minio_path(file_path)
        return minio_client.presigned_get_object(
            bucket_name=bucket_name,
            object_name=object_name,
        )
    except Exception:
        return None


def _local_image_to_data_url(file_path: str | None) -> str | None:
    if not file_path or not os.path.exists(file_path):
        return None

    extension = os.path.splitext(file_path)[1].lower()
    mime_type = "image/png"
    if extension in {".jpg", ".jpeg"}:
        mime_type = "image/jpeg"

    with open(file_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("ascii")

    return f"data:{mime_type};base64,{encoded}"


def _stored_image_to_data_url(file_path: str | None) -> str | None:
    """Return a browser-readable image URL for local files or object storage paths."""
    if not file_path:
        return None

    if os.path.exists(file_path):
        return _local_image_to_data_url(file_path)

    return _get_presigned_url(file_path)


def _stored_file_exists(file_path: str | None) -> bool:
    if not file_path:
        return False
    if os.path.exists(file_path):
        return True
    try:
        bucket_name, object_name = _parse_minio_path(file_path)
        minio_client.stat_object(bucket_name, object_name)
        return True
    except Exception:
        return False


def _image_array_to_data_url(image_bgr: np.ndarray | None) -> str | None:
    if image_bgr is None or image_bgr.size == 0:
        return None

    success, encoded = cv2.imencode(".png", image_bgr)
    if not success:
        return None

    encoded_text = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/png;base64,{encoded_text}"


def _parse_minio_path(file_path: str) -> tuple[str, str]:
    normalized = file_path.lstrip("/")
    parts = normalized.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Duong dan MinIO khong hop le: {file_path}")
    return parts[0], parts[1]


def _load_image_from_minio(file_path: str | None) -> np.ndarray | None:
    if not file_path:
        return None

    try:
        bucket_name, object_name = _parse_minio_path(file_path)
        response = minio_client.get_object(bucket_name, object_name)
        try:
            file_bytes = response.read()
        finally:
            response.close()
            response.release_conn()

        return _decode_image_bytes(file_bytes)
    except Exception as e:
        print(f"Error loading image from MinIO ({file_path}): {e}")
        return None


def _decode_image_bytes(file_bytes: bytes) -> np.ndarray | None:
    dicom_image = _try_load_dicom(file_bytes)
    if dicom_image is not None:
        return dicom_image

    array = np.frombuffer(file_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is not None:
        return image

    try:
        with Image.open(BytesIO(file_bytes)) as pil_image:
            rgb_image = pil_image.convert("RGB")
            image_array = np.array(rgb_image, dtype=np.uint8)
            return cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _try_load_dicom(file_bytes: bytes) -> np.ndarray | None:
    try:
        try:
            dicom = pydicom.dcmread(BytesIO(file_bytes))
        except Exception:
            dicom = pydicom.dcmread(BytesIO(file_bytes), force=True)

        if not hasattr(dicom, "PixelData"):
            return None

        pixel_array = dicom.pixel_array.astype(np.float32)
        if pixel_array.ndim == 3:
            pixel_array = pixel_array[0]

        pixel_array -= pixel_array.min()
        max_value = pixel_array.max()
        if max_value > 0:
            pixel_array /= max_value

        image_u8 = (pixel_array * 255).astype(np.uint8)
        return cv2.cvtColor(image_u8, cv2.COLOR_GRAY2BGR)
    except Exception:
        return None


def _build_segmentation_overlays(
    original_image_bgr: np.ndarray | None,
    bbox: list[int] | None,
    seg_mask_path: str | None,
) -> tuple[str | None, str | None]:
    if original_image_bgr is None or bbox is None or not seg_mask_path or not os.path.exists(seg_mask_path):
        return None, None

    mask = cv2.imread(seg_mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None, None

    x_min, y_min, x_max, y_max = [int(value) for value in bbox]
    height, width = original_image_bgr.shape[:2]
    x_min = max(0, min(x_min, width - 1))
    y_min = max(0, min(y_min, height - 1))
    x_max = max(x_min + 1, min(x_max, width))
    y_max = max(y_min + 1, min(y_max, height))

    roi_width = x_max - x_min
    roi_height = y_max - y_min
    if roi_width <= 0 or roi_height <= 0:
        return None, None

    if mask.shape[1] != roi_width or mask.shape[0] != roi_height:
        mask = cv2.resize(mask, (roi_width, roi_height), interpolation=cv2.INTER_NEAREST)

    binary_mask = ((mask > 127).astype(np.uint8)) * 255

    mask_overlay = original_image_bgr.copy()
    roi_mask_overlay = mask_overlay[y_min:y_max, x_min:x_max]
    green_fill = np.zeros_like(roi_mask_overlay)
    green_fill[:, :] = (0, 255, 0)
    blended = cv2.addWeighted(roi_mask_overlay, 0.65, green_fill, 0.35, 0)
    roi_mask_overlay[binary_mask > 0] = blended[binary_mask > 0]

    contour_overlay = original_image_bgr.copy()
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    shifted_contours = [contour + np.array([[[x_min, y_min]]], dtype=np.int32) for contour in contours]
    cv2.drawContours(contour_overlay, shifted_contours, -1, (0, 255, 255), 2)

    return _image_array_to_data_url(mask_overlay), _image_array_to_data_url(contour_overlay)


def _display_tumor_label(label: str | None, no_tumor_detected: bool = False) -> str | None:
    if no_tumor_detected:
        return None
    if not label:
        return None
    return LABEL_MAP.get(label, label)


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


import urllib.request

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
    os.makedirs(assets_dir, exist_ok=True)
    
    font_name = "Roboto-Bold.ttf" if bold else "Roboto-Regular.ttf"
    font_url = f"https://github.com/googlefonts/roboto/raw/main/src/hinted/{font_name}"
    font_path = os.path.join(assets_dir, font_name)
    
    if not os.path.exists(font_path):
        try:
            urllib.request.urlretrieve(font_url, font_path)
        except Exception:
            pass # Fall back to default
            
    if os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            pass
            
    # Absolute fallback (no Vietnamese support, but prevents crashing)
    return ImageFont.load_default()


def _fit_report_image(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, (250, 251, 252))
    fitted = ImageOps.contain(image.convert("RGB"), size)
    x = (size[0] - fitted.width) // 2
    y = (size[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_spacing: int = 6,
) -> int:
    x, y = xy
    paragraphs = text.split("\n")
    
    for paragraph in paragraphs:
        if not paragraph.strip():
            y += font.size  # Empty line
            continue
            
        words = paragraph.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = word if not current else f"{current} {word}"
            if draw.textlength(test, font=font) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)

        for line in lines:
            draw.text((x, y), line, font=font, fill=fill)
            bbox = draw.textbbox((x, y), line, font=font)
            y = bbox[3] + line_spacing
            
    return y


def _draw_image_card(
    page: Image.Image,
    title: str,
    image: Image.Image | None,
    box: tuple[int, int, int, int],
    title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    small_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    scale: int = 1,
):
    draw = ImageDraw.Draw(page)
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=18 * scale, fill=(255, 255, 255), outline=BORDER, width=2 * scale)
    draw.text((x1 + 18 * scale, y1 + 14 * scale), title, font=title_font, fill=TEXT)

    image_area = (x1 + 18 * scale, y1 + 52 * scale, x2 - 18 * scale, y2 - 56 * scale)
    draw.rounded_rectangle(image_area, radius=12 * scale, fill=LIGHT_GRAY, outline=BORDER, width=1 * scale)
    if image is not None:
        fitted = _fit_report_image(image, (image_area[2] - image_area[0], image_area[3] - image_area[1]))
        page.paste(fitted, (image_area[0], image_area[1]))
    else:
        placeholder = "Hình ảnh không khả dụng"
        bbox = draw.textbbox((0, 0), placeholder, font=small_font)
        text_x = image_area[0] + ((image_area[2] - image_area[0]) - (bbox[2] - bbox[0])) // 2
        text_y = image_area[1] + ((image_area[3] - image_area[1]) - (bbox[3] - bbox[1])) // 2
        draw.text((text_x, text_y), placeholder, font=small_font, fill=TEXT_MUTED)


def _bgr_path_to_pil(path: str | None) -> Image.Image | None:
    if not path:
        return None

    if os.path.exists(path):
        image = cv2.imread(path, cv2.IMREAD_COLOR)
    else:
        image = _load_image_from_minio(path)

    if image is None:
        return None
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _load_image_for_report(minio_file_path: str | None = None, local_path: str | None = None) -> Image.Image | None:
    if local_path:
        return _bgr_path_to_pil(local_path)
    
    if minio_file_path:
        bgr = _load_image_from_minio(minio_file_path)
        if bgr is not None:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb)
    return None


def _build_summary_text(no_tumor_detected: bool, tumor_label: str | None, bbox_confidence: float | None) -> str:
    if no_tumor_detected:
        return (
            "Hệ thống AI không phát hiện tổn thương nội sọ đáng kể trên phim MRI này. "
            "Không có phân loại khối u nào được chỉ định."
        )
    confidence_text = _format_percent(bbox_confidence)
    if tumor_label:
        return (
            f"AI đã phát hiện một tổn thương nội sọ với độ tin cậy {confidence_text}. "
            f"Loại u dự đoán là {tumor_label}."
        )
    return "AI đã phát hiện một vùng nghi ngờ nội sọ. Kết luận cuối cùng nên được đưa ra bởi bác sĩ chuyên khoa."


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: list[str]) -> bytes:
    y = 780
    content_lines = ["BT", "/F1 12 Tf", "50 780 Td"]
    first_line = True
    for line in lines:
        safe_line = _escape_pdf_text(line)
        if not first_line:
            content_lines.append(f"0 -18 Td")
        content_lines.append(f"({safe_line}) Tj")
        first_line = False
        y -= 18
        if y < 80:
            break
    content_lines.append("ET")
    content_stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
        f"4 0 obj << /Length {len(content_stream)} >> stream\n".encode("latin-1") + content_stream + b"\nendstream endobj",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
    ]

    pdf = BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj)
        pdf.write(b"\n")

    xref_position = pdf.tell()
    pdf.write(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    pdf.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.write(f"{offset:010d} 00000 n \n".encode("latin-1"))

    pdf.write(
        (
            f"trailer << /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_position}\n%%EOF"
        ).encode("latin-1")
    )
    return pdf.getvalue()


def _build_professional_report_pdf(
    report_id: str,
    patient_code: str,
    image_id: int,
    status: str,
    processing_date: str,
    tumor_label: str | None,
    classification_confidence: float | None,
    bbox_confidence: float | None,
    bbox: list[int] | None,
    class_probabilities: list[float] | None,
    no_tumor_detected: bool,
    multimodal_available: bool,
    original_image: Image.Image | None,
    bbox_image: Image.Image | None,
    cropped_roi_image: Image.Image | None,
    mask_image: Image.Image | None,
    overlay_image: Image.Image | None,
    risk_score: float | None = None,
    risk_group: str | None = None,
    survival_curve_data: list[dict] | None = None,
    heatmap_image: Image.Image | None = None,
    gradcam_plus_image: Image.Image | None = None,
    layercam_image: Image.Image | None = None,
    detection_xai_image: Image.Image | None = None,
    segmentation_xai_image: Image.Image | None = None,
    classification_xai_image: Image.Image | None = None,
    classification_xai_explanation: str | None = None,
    xai_explanation: str | None = None,
    fusion_attention: list[float] | None = None,
    is_series: bool = False,
    num_slices: int = 1,
    key_slice_index: int = 0,
    rna_xai: list[dict] | None = None,
) -> bytes:
    # High Resolution (300 DPI)
    scale = 2
    page_size = (1240 * scale, 1754 * scale)
    page1 = Image.new("RGB", page_size, WHITE)
    page2 = Image.new("RGB", page_size, WHITE)
    draw1 = ImageDraw.Draw(page1)
    draw2 = ImageDraw.Draw(page2)

    font_title = _load_font(40 * scale, bold=True)
    font_h1 = _load_font(28 * scale, bold=True)
    font_h2 = _load_font(22 * scale, bold=True)
    font_body = _load_font(20 * scale)
    font_small = _load_font(16 * scale)
    font_label = _load_font(18 * scale, bold=True)
    font_big_number = _load_font(52 * scale, bold=True)

    # ── Page 1 Header ──
    draw1.rectangle((0, 0, page_size[0], 20 * scale), fill=TEAL)
    draw1.text((60 * scale, 50 * scale), "NeuroDiagnosis AI", font=font_title, fill=TEAL)
    draw1.text((60 * scale, 100 * scale), "BÁO CÁO CHẨN ĐOÁN UNG BƯỚU HỖ TRỢ BỞI AI", font=font_small, fill=SLATE_500)
    
    draw1.text((page_size[0] - 340 * scale, 55 * scale), f"Mã Báo Cáo: {report_id}", font=font_small, fill=SLATE_800)
    draw1.text((page_size[0] - 340 * scale, 85 * scale), f"Ngày tạo: {processing_date}", font=font_small, fill=SLATE_500)
    
    draw1.line((60 * scale, 130 * scale, page_size[0] - 60 * scale, 130 * scale), fill=SLATE_100, width=2 * scale)

    # ── Patient Info Block ──
    info_box = (60 * scale, 160 * scale, page_size[0] - 60 * scale, 280 * scale)
    draw1.rounded_rectangle(info_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)

    draw1.text((90 * scale, 180 * scale), "Mã BN (Patient ID)", font=font_small, fill=SLATE_500)
    draw1.text((90 * scale, 205 * scale), patient_code, font=font_label, fill=SLATE_800)
    
    draw1.text((360 * scale, 180 * scale), "Mã Ảnh (Image ID)", font=font_small, fill=SLATE_500)
    draw1.text((360 * scale, 205 * scale), str(image_id), font=font_label, fill=SLATE_800)
    
    draw1.text((630 * scale, 180 * scale), "Mô Thức (Modality)", font=font_small, fill=SLATE_500)
    draw1.text((630 * scale, 205 * scale), "MRI Sọ Não", font=font_label, fill=SLATE_800)
    
    draw1.text((900 * scale, 180 * scale), "Trạng Thái", font=font_small, fill=SLATE_500)
    draw1.text((900 * scale, 205 * scale), status.upper(), font=font_label, fill=TEAL if status == "done" else RED_500)

    # ── AI Result Summary ──
    draw1.text((60 * scale, 320 * scale), "1. Phân Loại Khối U bằng AI", font=font_h2, fill=TEAL)
    
    summary_box = (60 * scale, 360 * scale, page_size[0] - 60 * scale, 520 * scale)
    draw1.rounded_rectangle(summary_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)

    predicted_display = tumor_label or "Không phát hiện khối u"
    classification_display = _format_percent(classification_confidence)
    summary_text = _build_summary_text(no_tumor_detected, tumor_label, bbox_confidence).replace("Predicted tumor type", "Loại u dự đoán").replace("No lesion detected", "Không phát hiện u").replace("Confidence", "Độ tin cậy")

    draw1.text((90 * scale, 390 * scale), predicted_display, font=font_title, fill=RED_500 if not no_tumor_detected else SLATE_800)
    
    draw1.text((550 * scale, 390 * scale), "Độ tin cậy phân loại:", font=font_small, fill=SLATE_500)
    draw1.text((550 * scale, 415 * scale), classification_display, font=font_h1, fill=TEAL)
    
    draw1.text((850 * scale, 390 * scale), "Độ tin cậy phát hiện:", font=font_small, fill=SLATE_500)
    draw1.text((850 * scale, 415 * scale), _format_percent(bbox_confidence), font=font_h1, fill=TEAL)
    
    _draw_wrapped_text(draw1, summary_text, (90 * scale, 460 * scale), font_body, SLATE_800, max_width=1040 * scale)

    # ── Imaging Review ──
    draw1.text((60 * scale, 560 * scale), "2. Bằng Chứng Hình Ảnh", font=font_h2, fill=TEAL)
    _draw_image_card(page1, "MRI Gốc (Original)", original_image, (60 * scale, 600 * scale, 585 * scale, 1040 * scale), font_label, font_small, scale=scale)
    _draw_image_card(page1, "Vùng Khối U Phát Hiện (Bbox)", bbox_image, (655 * scale, 600 * scale, 1180 * scale, 1040 * scale), font_label, font_small, scale=scale)
    _draw_image_card(page1, "Vùng ROI Cắt Ngắn", cropped_roi_image, (60 * scale, 1080 * scale, 585 * scale, 1520 * scale), font_label, font_small, scale=scale)
    _draw_image_card(page1, "Mặt Nạ Phân Đoạn (Mask)", mask_image, (655 * scale, 1080 * scale, 1180 * scale, 1520 * scale), font_label, font_small, scale=scale)

    # ── Page 2 Header ──
    draw2.rectangle((0, 0, page_size[0], 20 * scale), fill=TEAL)
    draw2.text((60 * scale, 50 * scale), "NeuroDiagnosis AI - Tiếp theo", font=font_title, fill=TEAL)
    draw2.text((page_size[0] - 340 * scale, 55 * scale), f"Mã Báo Cáo: {report_id}", font=font_small, fill=SLATE_800)
    draw2.line((60 * scale, 100 * scale, page_size[0] - 60 * scale, 100 * scale), fill=SLATE_100, width=2 * scale)

    draw2.text((60 * scale, 130 * scale), "Ảnh Lồng Ghép Phân Đoạn", font=font_h2, fill=TEAL)
    _draw_image_card(page2, "Overlay / Masked ROI", overlay_image, (60 * scale, 170 * scale, 1180 * scale, 740 * scale), font_label, font_small, scale=scale)

    draw2.text((60 * scale, 780 * scale), "Thông Số Kỹ Thuật (Model Details)", font=font_h2, fill=TEAL)
    tech_box = (60 * scale, 820 * scale, 1180 * scale, 1250 * scale)
    draw2.rounded_rectangle(tech_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)
    tech_rows = [
        ("Tọa độ Bounding Box", str(bbox) if bbox else "N/A"),
        ("Độ tin cậy Bbox", _format_percent(bbox_confidence)),
        ("Xác suất các nhóm", ", ".join(f"{value * 100:.2f}%" for value in (class_probabilities or [])) or "N/A"),
        ("Nhãn dự đoán", predicted_display),
        ("Ảnh phân đoạn (Mask)", "Có" if not no_tumor_detected and mask_image is not None else "Không"),
        ("Tích hợp đa mô thức", "Sẵn sàng" if multimodal_available else "Chưa có"),
        ("Chế độ quét", f"Series ({num_slices} lát cắt)" if is_series else "Ảnh đơn (Single)"),
    ]
    if is_series:
        tech_rows.append(("Lát cắt hiển thị", f"Lát cắt số {key_slice_index + 1} (Key Slice)"))
    y = 850 * scale
    for label, value in tech_rows:
        draw2.text((90 * scale, y), label, font=font_small, fill=SLATE_500)
        _draw_wrapped_text(draw2, value, (440 * scale, y), font_small, SLATE_800, max_width=680 * scale, line_spacing=4 * scale)
        draw2.line((90 * scale, y + 35 * scale, 1150 * scale, y + 35 * scale), fill=SLATE_100, width=1 * scale)
        y += 50 * scale

    draw2.text((60 * scale, 1400 * scale), "Khuyến Cáo Y Tế", font=font_h2, fill=RED_500)
    disclaimer_box = (60 * scale, 1440 * scale, 1180 * scale, 1600 * scale)
    draw2.rounded_rectangle(disclaimer_box, radius=12 * scale, fill=(254, 242, 242), outline=(252, 165, 165), width=2 * scale)
    disclaimer_lines = [
        "Báo cáo này được tự động tạo ra bởi trí tuệ nhân tạo (AI) nhằm mục đích hỗ trợ quyết định lâm sàng.",
        "Kết quả dự đoán KHÔNG thay thế cho chẩn đoán y khoa của bác sĩ chuyên khoa. Mọi quyết định",
        "điều trị phải dựa trên đánh giá toàn diện của bác sĩ điều trị và kết quả xét nghiệm liên quan.",
    ]
    current_y = 1470 * scale
    for line in disclaimer_lines:
        current_y = _draw_wrapped_text(draw2, line, (90 * scale, current_y), font_body, SLATE_900, max_width=1040 * scale, line_spacing=8 * scale)
        current_y += 10 * scale

    # ── Page 3: Multimodal Prognosis ──────────────────────────
    all_pages = [page2]

    if detection_xai_image or segmentation_xai_image or classification_xai_image or classification_xai_explanation:
        page_xai = Image.new("RGB", page_size, WHITE)
        draw_xai = ImageDraw.Draw(page_xai)

        draw_xai.rectangle((0, 0, page_size[0], 20 * scale), fill=TEAL)
        draw_xai.text((60 * scale, 50 * scale), "MRI Core XAI", font=font_title, fill=TEAL)
        draw_xai.text((page_size[0] - 340 * scale, 55 * scale), f"Mã Báo Cáo: {report_id}", font=font_small, fill=SLATE_800)
        draw_xai.line((60 * scale, 100 * scale, page_size[0] - 60 * scale, 100 * scale), fill=SLATE_100, width=2 * scale)

        draw_xai.text((60 * scale, 130 * scale), "3. Bản đồ nhiệt giải thích MRI Core", font=font_h2, fill=TEAL)
        _draw_image_card(page_xai, "Detection / ODAM", detection_xai_image, (60 * scale, 180 * scale, 400 * scale, 650 * scale), font_label, font_small, scale=scale)
        _draw_image_card(page_xai, "Segmentation / Seg-Eigen-CAM", segmentation_xai_image, (450 * scale, 180 * scale, 790 * scale, 650 * scale), font_label, font_small, scale=scale)
        _draw_image_card(page_xai, "Classification / Finer-CAM", classification_xai_image, (840 * scale, 180 * scale, 1180 * scale, 650 * scale), font_label, font_small, scale=scale)

        if classification_xai_explanation:
            explanation_box = (60 * scale, 710 * scale, 1180 * scale, 1600 * scale)
            draw_xai.rounded_rectangle(explanation_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)
            draw_xai.text((90 * scale, 740 * scale), "Giải thích", font=font_label, fill=SLATE_900)
            _draw_wrapped_text(
                draw_xai,
                classification_xai_explanation,
                (90 * scale, 780 * scale),
                font_small,
                SLATE_800,
                max_width=1040 * scale,
                line_spacing=7 * scale,
            )

        all_pages.append(page_xai)

    if multimodal_available and risk_score is not None:
        page3 = Image.new("RGB", page_size, WHITE)
        draw3 = ImageDraw.Draw(page3)
        font_big_number = _load_font(52 * scale, bold=True)

        # ── Page 3 Header ──
        draw3.rectangle((0, 0, page_size[0], 20 * scale), fill=TEAL)
        draw3.text((60 * scale, 50 * scale), "Phân Tích Tiên Lượng Đa Mô Thức", font=font_title, fill=TEAL)
        draw3.text((page_size[0] - 340 * scale, 55 * scale), f"Mã Báo Cáo: {report_id}", font=font_small, fill=SLATE_800)
        draw3.line((60 * scale, 100 * scale, page_size[0] - 60 * scale, 100 * scale), fill=SLATE_100, width=2 * scale)

        # ── Risk Score + Risk Group cards ──
        draw3.text((60 * scale, 130 * scale), "3. Chỉ Số Rủi Ro Tiên Lượng", font=font_h2, fill=TEAL)

        # Risk Score card
        rs_box = (60 * scale, 170 * scale, 600 * scale, 395 * scale)
        draw3.rounded_rectangle(rs_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)
        draw3.text((90 * scale, 190 * scale), "Chỉ số rủi ro (Risk Score)", font=font_small, fill=SLATE_500)
        rs_display = f"{risk_score:.4f}"
        draw3.text((90 * scale, 225 * scale), rs_display, font=font_big_number, fill=SLATE_800)

        # Risk level bar
        bar_x, bar_y, bar_w, bar_h = 90 * scale, 305 * scale, 480 * scale, 22 * scale
        draw3.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=8 * scale, fill=SLATE_100)
        normalized_risk = max(0.0, min(1.0, (risk_score + 2) / 4))  # map [-2, 2] -> [0, 1]
        fill_w = int(bar_w * normalized_risk)
        if fill_w > 0:
            bar_color = RED_500 if normalized_risk > 0.6 else (245, 158, 11) if normalized_risk > 0.3 else TEAL
            draw3.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=8 * scale, fill=bar_color)
        draw3.text((90 * scale, 337 * scale), "Thấp", font=font_small, fill=TEAL)
        draw3.text((bar_x + bar_w // 2 - 25 * scale, 337 * scale), "Trung bình", font=font_small, fill=(245, 158, 11))
        draw3.text((bar_x + bar_w - 40 * scale, 337 * scale), "Cao", font=font_small, fill=RED_500)

        # Risk Group card
        rg_box = (640 * scale, 170 * scale, 1180 * scale, 395 * scale)
        draw3.rounded_rectangle(rg_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)
        draw3.text((670 * scale, 190 * scale), "Nhóm rủi ro (Risk Group)", font=font_small, fill=SLATE_500)
        rg_display = risk_group or "N/A"
        rg_color = RED_500 if rg_display == "High" else (245, 158, 11) if rg_display == "Medium" else TEAL
        draw3.text((670 * scale, 225 * scale), rg_display, font=font_big_number, fill=rg_color)

        # Data source indicators
        draw3.text((670 * scale, 305 * scale), "Dữ liệu được sử dụng:", font=font_small, fill=SLATE_500)
        draw3.text((670 * scale, 330 * scale), "Hình ảnh MRI", font=font_label, fill=TEAL)
        draw3.text((670 * scale, 355 * scale), "Dữ liệu RNA-seq / Lâm sàng", font=font_small, fill=SLATE_500)

        # ── Grad-CAM Heatmaps Grid ──
        current_y3 = 430 * scale
        draw3.text((60 * scale, current_y3), "4. Giải thích Hình ảnh XAI (Heatmaps)", font=font_h2, fill=TEAL)
        current_y3 += 50 * scale
        
        hm_h = 420 * scale
        hm_w = 340 * scale
        # Better spacing: 60 margin, 50 gap -> 60, 450, 840
        _draw_image_card(page3, "Grad-CAM", heatmap_image, (60 * scale, current_y3, 400 * scale, current_y3 + hm_h), font_label, font_small, scale=scale)
        _draw_image_card(page3, "Grad-CAM++", gradcam_plus_image, (450 * scale, current_y3, 790 * scale, current_y3 + hm_h), font_label, font_small, scale=scale)
        _draw_image_card(page3, "Layer-CAM", layercam_image, (840 * scale, current_y3, 1180 * scale, current_y3 + hm_h), font_label, font_small, scale=scale)
        
        current_y3 += hm_h + 40 * scale

        # ── Attention Weights & Explanation ──
        if fusion_attention and len(fusion_attention) >= 4:
            attn_x = 60 * scale # Default left
            attn_box = (attn_x, current_y3, 1180 * scale, current_y3 + 750 * scale)
            draw3.rounded_rectangle(attn_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)
            draw3.text((attn_box[0] + 30 * scale, current_y3 + 25 * scale), "Trọng số Attention Đa mô thức", font=font_label, fill=SLATE_900)
            draw3.text((attn_box[0] + 30 * scale, current_y3 + 55 * scale), "Mức độ đóng góp của từng loại dữ liệu vào dự đoán", font=font_small, fill=SLATE_500)

            labels = ["MRI", "WSI (Giải phẫu bệnh)", "RNA-seq", "Lâm sàng"]
            colors = [TEAL, SLATE_500, (245, 158, 11), (139, 92, 246)]
            bar_max_w = (attn_box[2] - attn_box[0]) - 320 * scale
            by = current_y3 + 100 * scale
            max_attn = max(fusion_attention[:4]) if max(fusion_attention[:4]) > 0 else 1.0
            
            for i, (lbl, clr) in enumerate(zip(labels, colors)):
                val = fusion_attention[i] if i < len(fusion_attention) else 0.0
                draw3.text((attn_box[0] + 30 * scale, by), lbl, font=font_label, fill=SLATE_800)
                bar_bg = (attn_box[0] + 250 * scale, by + 2 * scale, attn_box[0] + 250 * scale + bar_max_w, by + 22 * scale)
                draw3.rounded_rectangle(bar_bg, radius=6 * scale, fill=SLATE_100)
                fill_bar_w = int(bar_max_w * (val / max_attn))
                if fill_bar_w > 0:
                    draw3.rounded_rectangle((attn_box[0] + 250 * scale, by + 2 * scale, attn_box[0] + 250 * scale + fill_bar_w, by + 22 * scale), radius=6 * scale, fill=clr)
                pct_text = f"{val * 100:.1f}%"
                draw3.text((attn_box[0] + 260 * scale + bar_max_w, by + 2 * scale), pct_text, font=font_small, fill=SLATE_800)
                by += 60 * scale  # Increased gap to prevent overlap
            
            if xai_explanation:
                by += 20 * scale
                draw3.text((attn_box[0] + 30 * scale, by), "Giải thích lâm sàng:", font=font_label, fill=SLATE_900)
                by += 35 * scale
                by = _draw_wrapped_text(draw3, xai_explanation, (attn_box[0] + 30 * scale, by), font_small, SLATE_500, max_width=1040 * scale, line_spacing=6 * scale)

            current_y3 = by + 60 * scale
        
        # ── Survival Curve chart ──
        # Check if enough space for chart (~600 units). If not, move to page 4
        if current_y3 > 1100 * scale:
            all_pages.append(page3)
            page3 = Image.new("RGB", page_size, WHITE)
            draw3 = ImageDraw.Draw(page3)
            draw3.rectangle((0, 0, page_size[0], 20 * scale), fill=TEAL)
            draw3.text((60 * scale, 50 * scale), "Phân Tích Tiên Lượng (Tiếp)", font=font_title, fill=TEAL)
            draw3.text((page_size[0] - 340 * scale, 55 * scale), f"Mã Báo Cáo: {report_id}", font=font_small, fill=SLATE_800)
            draw3.line((60 * scale, 100 * scale, page_size[0] - 60 * scale, 100 * scale), fill=SLATE_100, width=2 * scale)
            current_y3 = 130 * scale

        sc_y = current_y3 + 10 * scale
        draw3.text((60 * scale, sc_y), "Biểu đồ sinh tồn dự đoán (Kaplan-Meier)", font=font_h2, fill=TEAL)
        sc_y += 40 * scale
        chart_height = 500 * scale
        chart_box = (60 * scale, sc_y, 1180 * scale, sc_y + chart_height)
        draw3.rounded_rectangle(chart_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)

        if survival_curve_data and len(survival_curve_data) > 1:
            chart_left = 130 * scale
            chart_top = sc_y + 50 * scale
            chart_right = 1140 * scale
            chart_bottom = sc_y + chart_height - 40 * scale
            chart_w = chart_right - chart_left
            chart_h = chart_bottom - chart_top

            # Axes
            draw3.line((chart_left, chart_bottom, chart_right, chart_bottom), fill=SLATE_800, width=2 * scale)
            draw3.line((chart_left, chart_top, chart_left, chart_bottom), fill=SLATE_800, width=2 * scale)

            # Grid lines
            for i in range(1, 5):
                gy = chart_bottom - int(chart_h * i / 4)
                draw3.line((chart_left, gy, chart_right, gy), fill=SLATE_100, width=1 * scale)
                draw3.text((chart_left - 50 * scale, gy - 8 * scale), f"{i * 25}%", font=font_small, fill=SLATE_500)
            draw3.text((chart_left - 35 * scale, chart_bottom - 8 * scale), "0%", font=font_small, fill=SLATE_500)

            # Axis labels
            draw3.text((chart_left + chart_w // 2 - 30 * scale, chart_bottom + 20 * scale), "Thời gian (Tháng)", font=font_small, fill=SLATE_500)

            # Plot data
            times = [pt.get("time", 0) for pt in survival_curve_data]
            probs = [pt.get("survival_probability", 0) for pt in survival_curve_data]
            max_time = max(times) if times else 1

            tick_count = min(6, len(times))
            for i in range(tick_count + 1):
                t_val = max_time * i / tick_count
                tx = chart_left + int(chart_w * i / tick_count)
                draw3.text((tx - 10 * scale, chart_bottom + 4 * scale), f"{t_val:.0f}", font=font_small, fill=SLATE_500)

            # Step line + fill
            points_for_fill = []
            prev_x, prev_y = None, None
            for t, p in zip(times, probs):
                x = chart_left + int(chart_w * t / max_time) if max_time > 0 else chart_left
                y = chart_bottom - int(chart_h * p)
                if prev_x is not None and prev_y is not None:
                    draw3.line((prev_x, prev_y, x, prev_y), fill=TEAL, width=3 * scale)
                    draw3.line((x, prev_y, x, y), fill=TEAL, width=3 * scale)
                    points_for_fill.append((x, prev_y))
                else:
                    points_for_fill.append((x, y))
                points_for_fill.append((x, y))
                prev_x, prev_y = x, y

            if points_for_fill:
                fill_polygon = list(points_for_fill) + [(prev_x, chart_bottom), (points_for_fill[0][0], chart_bottom)]
                try:
                    fill_overlay = Image.new("RGBA", page_size, (0, 0, 0, 0))
                    fill_draw = ImageDraw.Draw(fill_overlay)
                    fill_draw.polygon(fill_polygon, fill=(13, 148, 136, 40))
                    page3 = Image.alpha_composite(page3.convert("RGBA"), fill_overlay).convert("RGB")
                    draw3 = ImageDraw.Draw(page3)
                except Exception:
                    pass

            for t, p in zip(times, probs):
                x = chart_left + int(chart_w * t / max_time) if max_time > 0 else chart_left
                y = (sc_y + chart_height - 40 * scale) - int((chart_height - 90 * scale) * p)
                draw3.ellipse((x - 4 * scale, y - 4 * scale, x + 4 * scale, y + 4 * scale), fill=TEAL, outline="white", width=2 * scale)
        else:
            draw3.text((400 * scale, sc_y + chart_height // 2), "Chưa có dữ liệu sinh tồn", font=font_small, fill=SLATE_500)

        # ── RNA XAI Section ──
        chart_bottom = sc_y + chart_height
        if rna_xai and len(rna_xai) > 0:
            rna_y = chart_bottom + 40 * scale
            draw3.text((60 * scale, rna_y), "Phân Tích Dấu Ấn Phân Tử (RNA-seq Feature Importance)", font=font_h2, fill=TEAL)
            rna_y += 45 * scale
            
            rna_box = (60 * scale, rna_y, 1180 * scale, rna_y + 550 * scale)
            draw3.rounded_rectangle(rna_box, radius=12 * scale, fill=WHITE, outline=SLATE_100, width=2 * scale)
            
            # Headers
            draw3.text((rna_box[0] + 30 * scale, rna_y + 20 * scale), "Top 10 gene có biểu hiện thực tế đóng góp mạnh nhất vào dự đoán rủi ro của AI", font=font_small, fill=SLATE_500)
            
            # Table Headers
            ty = rna_y + 60 * scale
            draw3.text((rna_box[0] + 30 * scale, ty), "Ký hiệu Gene", font=font_label, fill=SLATE_800)
            draw3.text((rna_box[0] + 250 * scale, ty), "Độ Đóng Góp (Importance)", font=font_label, fill=SLATE_800)
            draw3.text((rna_box[0] + 680 * scale, ty), "Biểu Hiện (Expression)", font=font_label, fill=SLATE_800)
            draw3.text((rna_box[0] + 930 * scale, ty), "Ảnh Hưởng (Impact)", font=font_label, fill=SLATE_800)
            
            draw3.line((rna_box[0] + 30 * scale, ty + 25 * scale, rna_box[2] - 30 * scale, ty + 25 * scale), fill=SLATE_100, width=1 * scale)
            ty += 40 * scale
            
            # Row details
            max_imp = max(abs(pt.get("importance", 1.0)) for pt in rna_xai) if rna_xai else 1.0
            if max_imp == 0: max_imp = 1.0
            
            for item in rna_xai[:10]:
                gene_symbol = item.get("gene", "--")
                imp_val = item.get("importance", 0.0)
                expr_val = item.get("expression", 0.0)
                impact = item.get("impact", "--")
                
                # Gene name
                draw3.text((rna_box[0] + 30 * scale, ty), gene_symbol, font=font_body, fill=SLATE_800)
                
                # Contribution Bar
                bar_max_w = 320 * scale
                bar_x = rna_box[0] + 250 * scale
                draw3.rounded_rectangle((bar_x, ty + 2 * scale, bar_x + bar_max_w, ty + 20 * scale), radius=4 * scale, fill=SLATE_100)
                
                pct_w = int(bar_max_w * (abs(imp_val) / max_imp))
                bar_color = RED_500 if imp_val > 0 else TEAL
                if pct_w > 0:
                    draw3.rounded_rectangle((bar_x, ty + 2 * scale, bar_x + pct_w, ty + 20 * scale), radius=4 * scale, fill=bar_color)
                
                # Imp value text
                draw3.text((bar_x + bar_max_w + 15 * scale, ty), f"{imp_val:+.4f}", font=font_small, fill=bar_color)
                
                # Expression
                draw3.text((rna_box[0] + 680 * scale, ty), f"{expr_val:.2f}", font=font_body, fill=SLATE_800)
                
                # Impact badge
                badge_color = RED_500 if impact == "High Risk" else TEAL
                impact_text = "Tăng rủi ro" if impact == "High Risk" else "Bảo vệ"
                draw3.text((rna_box[0] + 930 * scale, ty), impact_text, font=font_label, fill=badge_color)
                
                draw3.line((rna_box[0] + 30 * scale, ty + 30 * scale, rna_box[2] - 30 * scale, ty + 30 * scale), fill=SLATE_100, width=1 * scale)
                ty += 45 * scale

        # ── Medical Disclaimer at the absolute bottom ──
        # This will be drawn on the current page (either Page 3 or Page 4)
        disc3_y = page_size[1] - 250 * scale
        draw3.text((60 * scale, disc3_y), "Khuyến Cáo Y Tế & Tiên Lượng", font=font_h2, fill=RED_500)
        draw3.rounded_rectangle((60 * scale, disc3_y + 40 * scale, 1180 * scale, disc3_y + 220 * scale), radius=12 * scale, fill=(254, 242, 242), outline=(252, 165, 165), width=2 * scale)
        _draw_wrapped_text(draw3, "Dự báo tiên lượng và biểu đồ sinh tồn dựa trên các yếu tố sinh học và dữ liệu thống kê. Kết quả mang tính chất tham khảo cho việc lập kế hoạch điều trị và không phải là cam kết chắc chắn về thời gian sống còn của bệnh nhân. Báo cáo này được tự động tạo ra bởi trí tuệ nhân tạo (AI) nhằm mục đích hỗ trợ quyết định lâm sàng. Kết quả dự đoán KHÔNG thay thế cho chẩn đoán y khoa của bác sĩ chuyên khoa. Mọi quyết định điều trị phải dựa trên đánh giá toàn diện của bác sĩ điều trị và kết quả xét nghiệm liên quan.", (90 * scale, disc3_y + 65 * scale), font_body, SLATE_900, max_width=1040 * scale, line_spacing=6 * scale)
        all_pages.append(page3)

    buffer = BytesIO()
    page1.save(buffer, format="PDF", save_all=True, append_images=all_pages, resolution=300)
    return buffer.getvalue()


def _get_latest_mri_task(db: Session, image_id: int) -> models.InferenceTask | None:
    return (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == "mri_pipeline",
            models.InferenceTask.target_id == image_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .first()
    )


def _get_latest_classification_xai_task(db: Session, image: models.Image) -> models.InferenceTask | None:
    mri_task = _get_latest_mri_task(db, image.id)
    if mri_task and isinstance(mri_task.result, dict) and mri_task.result.get("classification_xai_path"):
        return mri_task

    return (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == "prognosis",
            models.InferenceTask.target_id == image.patient_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .first()
    )


def _build_classification_xai_fallback(
    tumor_label: str | None,
    classification_confidence: float | None,
    xai_metadata: dict[str, Any] | None,
    technical_note: str | None = None,
) -> str:
    tumor_display = _display_tumor_label(tumor_label, no_tumor_detected=False) or "chưa xác định"
    if classification_confidence is None:
        confidence_text = "chưa có thông tin"
    else:
        confidence_text = f"{classification_confidence * 100:.1f}%"

    metadata = xai_metadata or {}
    method = metadata.get("method") or metadata.get("classification_method") or "Finer-CAM"
    localization = metadata.get("localization_strength") or metadata.get("focus_level")
    heatmap_shape = metadata.get("heatmap_shape") or metadata.get("shape")

    localization_text = {
        "strongly_focal": "tập trung khá rõ",
        "moderately_focal": "tập trung ở mức vừa phải",
        "diffuse": "phân bố còn lan rộng",
    }.get(str(localization), "chưa có mô tả định lượng rõ")

    shape_text = ""
    if isinstance(heatmap_shape, (list, tuple)) and len(heatmap_shape) >= 2:
        shape_text = f" Kích thước heatmap: {heatmap_shape[0]} x {heatmap_shape[1]}."

    note = ""
    if technical_note:
        note = (
            "\n\nGhi chú kỹ thuật: hệ thống chưa truy xuất được ngữ cảnh RAG/Hugging Face tại thời điểm này, "
            f"nên phần giải thích y khoa được tạo theo cơ chế fallback an toàn. Chi tiết: {technical_note}"
        )

    return (
        "1. Kết quả tóm tắt\n"
        f"- Mô hình dự đoán loại u: {tumor_display}.\n"
        f"- Độ tin cậy phân loại: {confidence_text}. Độ tin cậy này cho biết mức mô hình nghiêng về nhãn dự đoán, "
        "không phải mức độ nguy hiểm của bệnh.\n\n"
        "2. Giải thích AI/XAI và vùng heatmap mô hình dựa vào\n"
        f"- Phương pháp XAI sử dụng: {method}.\n"
        f"- Heatmap cho thấy vùng mô hình tập trung khi đưa ra dự đoán; mức tập trung hiện được ghi nhận là {localization_text}."
        f"{shape_text}\n"
        "- Heatmap chỉ mang tính định hướng vùng ảnh có ảnh hưởng tới mô hình, không phải bằng chứng giải phẫu bệnh.\n\n"
        "3. Thông tin y khoa về loại u này\n"
        "- Chưa thể tải ngữ cảnh RAG đầy đủ ở thời điểm hiện tại, nên hệ thống không bổ sung thông tin y khoa chi tiết từ nguồn ngoài.\n"
        "- Cần đối chiếu với MRI đầy đủ, triệu chứng lâm sàng và kết luận của bác sĩ chuyên khoa.\n\n"
        "4. Lưu ý an toàn\n"
        "- Kết quả AI không thay thế chẩn đoán y khoa.\n"
        "- Không dùng heatmap làm căn cứ điều trị độc lập; mọi quyết định cần dựa trên đánh giá lâm sàng toàn diện."
        f"{note}"
    )


@router.get("/records/analysis/patient/{patient_id}/full", response_model=schemas.ImageAIResultResponse)
def get_patient_full_analysis(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Endpoint đầy đủ: kết hợp AnalysisResult + InferenceTask.result
    để trả về overlay images, heatmaps, multimodal fields cho Frontend.
    """
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")

    real_id = patient.id

    # Lấy AnalysisResult mới nhất
    analysis = (
        db.query(models.AnalysisResult)
        .filter(models.AnalysisResult.patient_id == real_id)
        .order_by(models.AnalysisResult.created_at.desc())
        .first()
    )

    # Lấy InferenceTask mới nhất (prognosis hoặc mri_pipeline)
    prognosis_task = (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == "prognosis",
            models.InferenceTask.target_id == real_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .first()
    )

    # Cũng tìm MRI task nếu có (để lấy overlay images)
    mri_image = (
        db.query(models.Image)
        .filter(
            models.Image.patient_id == real_id,
            models.Image.modality.in_(["MRI", "MRI_SERIES"]),
        )
        .order_by(models.Image.scan_date.desc())
        .first()
    )

    mri_task = None
    if mri_image:
        mri_task = _get_latest_mri_task(db, mri_image.id)

    if not analysis and not prognosis_task and not mri_task:
        raise HTTPException(status_code=404, detail="Chua co ket qua phan tich cho benh nhan nay.")

    # Merge dữ liệu từ cả 2 task (prognosis có multimodal, mri có overlay images)
    result_payload = {}
    if mri_task and mri_task.result:
        result_payload.update(mri_task.result)
    if prognosis_task and prognosis_task.result:
        if result_payload:
            result_payload = _merge_prognosis_only(result_payload, prognosis_task.result)
        else:
            result_payload.update(prognosis_task.result)

    # Xác định image_id và metadata
    image_id = mri_image.id if mri_image else (analysis.image_id if analysis else 0)
    is_series = mri_image.is_series if mri_image else False
    num_slices = mri_image.num_slices if mri_image else 1
    key_slice_index = mri_image.key_slice_index if mri_image else 0

    # Xác định status
    status = "done"
    error_message = None
    task_id = None
    created_at = analysis.created_at if analysis else None
    updated_at = None

    if prognosis_task:
        status = prognosis_task.status
        error_message = prognosis_task.error_message
        task_id = prognosis_task.id
        updated_at = prognosis_task.updated_at
        if not created_at:
            created_at = prognosis_task.created_at
    elif mri_task:
        status = mri_task.status
        error_message = mri_task.error_message
        task_id = mri_task.id
        updated_at = mri_task.updated_at
        if not created_at:
            created_at = mri_task.created_at

    # Build overlay data URLs từ local paths
    no_tumor_detected = bool(result_payload.get("no_tumor_detected") or (analysis and getattr(analysis, "no_tumor_detected", False)))
    bbox = result_payload.get("bbox")
    seg_mask_path = result_payload.get("seg_mask_path")

    mask_overlay_data_url = _stored_image_to_data_url(result_payload.get("mask_overlay_path"))
    contour_overlay_data_url = _stored_image_to_data_url(result_payload.get("contour_overlay_path"))

    if mask_overlay_data_url is None or contour_overlay_data_url is None:
        original_image_bgr = _load_image_from_minio(mri_image.file_path) if mri_image else None
        fallback_mask, fallback_contour = _build_segmentation_overlays(
            original_image_bgr=original_image_bgr,
            bbox=bbox,
            seg_mask_path=seg_mask_path,
        )
        if mask_overlay_data_url is None:
            mask_overlay_data_url = fallback_mask
        if contour_overlay_data_url is None:
            contour_overlay_data_url = fallback_contour

    classification_xai_path = result_payload.get("classification_xai_path")
    classification_explanation = GeminiXaiExplanationService._format_for_display(
        result_payload.get("classification_xai_explanation") or ""
    ) or None
    xai_metadata = result_payload.get("xai_metadata") or {}
    ai_tumor_label = _display_tumor_label(
        result_payload.get("tumor_label") or (analysis.tumor_label if analysis else None),
        no_tumor_detected=no_tumor_detected,
    )
    ai_confidence = result_payload.get("classification_confidence")
    if ai_confidence is None and analysis:
        ai_confidence = analysis.classification_confidence
    review_state = classification_review_state(db, image_id, ai_tumor_label, ai_confidence)

    return schemas.ImageAIResultResponse(
        image_id=image_id,
        patient_id=real_id,
        task_id=task_id,
        status=status,
        no_tumor_detected=no_tumor_detected,
        error_message=error_message,
        bbox=bbox,
        bbox_confidence=result_payload.get("bbox_confidence"),
        tumor_label=ai_tumor_label,
        classification_confidence=ai_confidence,
        ai_tumor_label=review_state["ai_tumor_label"],
        ai_confidence=review_state["ai_confidence"],
        final_tumor_label=review_state["final_tumor_label"],
        expert_tumor_label=review_state["expert_tumor_label"],
        expert_comment=review_state["expert_comment"],
        review_required=review_state["review_required"],
        review_status=review_state["review_status"],
        review_action=review_state["review_action"],
        reviewed_at=review_state["reviewed_at"],
        class_probabilities=result_payload.get("class_probabilities"),
        bbox_overlay_data_url=_stored_image_to_data_url(result_payload.get("bbox_image_path")),
        mask_data_url=_stored_image_to_data_url(result_payload.get("seg_mask_path")),
        mask_overlay_data_url=mask_overlay_data_url,
        contour_overlay_data_url=contour_overlay_data_url,
        risk_score=None if no_tumor_detected else (result_payload.get("risk_score") if result_payload.get("risk_score") is not None else (analysis.risk_score if analysis else None)),
        risk_group=None if no_tumor_detected else (result_payload.get("risk_group") or (analysis.risk_group if analysis else None)),
        survival_curve_data=None if no_tumor_detected else (result_payload.get("survival_curve_data") or (analysis.survival_curve_data if analysis else None)),
        multimodal_risk_xai_data_url=_stored_image_to_data_url(result_payload.get("multimodal_risk_xai_path") or result_payload.get("gradcam_heatmap_path")),
        multimodal_gradcam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("multimodal_gradcam_heatmap_path")),
        multimodal_gradcam_plus_heatmap_data_url=_stored_image_to_data_url(result_payload.get("multimodal_gradcam_plus_heatmap_path")),
        multimodal_layercam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("multimodal_layercam_heatmap_path")),
        gradcam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("gradcam_heatmap_path")),
        gradcam_plus_heatmap_data_url=_stored_image_to_data_url(result_payload.get("gradcam_plus_heatmap_path")),
        layercam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("layercam_heatmap_path")),
        detection_xai_data_url=_stored_image_to_data_url(result_payload.get("detection_xai_path") or result_payload.get("odam_path")),
        segmentation_xai_data_url=_stored_image_to_data_url(result_payload.get("segmentation_xai_path") or result_payload.get("seg_eigen_cam_path")),
        classification_xai_data_url=_stored_image_to_data_url(classification_xai_path),
        xai_methods=result_payload.get("xai_methods"),
        xai_warnings=result_payload.get("xai_warnings"),
        xai_metadata=xai_metadata,
        xai_explanation=result_payload.get("xai_explanation"),
        classification_xai_explanation=classification_explanation,
        multimodal_xai_explanation=result_payload.get("multimodal_xai_explanation") or result_payload.get("xai_explanation"),
        fusion_attention=[v if v is not None else 0.0 for v in result_payload["fusion_attention"]] if result_payload.get("fusion_attention") else None,
        rna_xai=result_payload.get("rna_xai"),
        is_series=is_series,
        num_slices=num_slices,
        key_slice_index=key_slice_index,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.get("/records/analysis/{patient_id}", response_model=List[schemas.AnalysisResultResponse])
def get_patient_analysis(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")

    # Sử dụng ID số nội bộ để truy vấn
    real_id = patient.id
    results = db.query(models.AnalysisResult).filter(models.AnalysisResult.patient_id == real_id).all()
    if not results:
        raise HTTPException(status_code=404, detail="Chua co ket qua phan tich cho benh nhan nay.")

    return results


@router.get("/records/analysis/image/{image_id}", response_model=schemas.ImageAIResultResponse)
def get_image_analysis_detail(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Khong tim thay anh MRI")

    latest_task = _get_latest_mri_task(db, image_id)
    analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()

    status = "done" if analysis else "ready"
    error_message = None
    result_payload = {}
    task_id = None
    created_at = analysis.created_at if analysis else None
    updated_at = latest_task.updated_at if latest_task else None

    if latest_task:
        task_id = latest_task.id
        status = latest_task.status
        error_message = latest_task.error_message
        result_payload = latest_task.result or {}
        created_at = latest_task.created_at
        updated_at = latest_task.updated_at

    bbox = result_payload.get("bbox")
    seg_mask_path = result_payload.get("seg_mask_path")
    no_tumor_detected = bool(result_payload.get("no_tumor_detected") or (analysis and getattr(analysis, "no_tumor_detected", False)))
    mask_overlay_data_url = _stored_image_to_data_url(result_payload.get("mask_overlay_path"))
    contour_overlay_data_url = _stored_image_to_data_url(result_payload.get("contour_overlay_path"))

    if mask_overlay_data_url is None or contour_overlay_data_url is None:
        original_image_bgr = _load_image_from_minio(image.file_path)
        fallback_mask_overlay_data_url, fallback_contour_overlay_data_url = _build_segmentation_overlays(
            original_image_bgr=original_image_bgr,
            bbox=bbox,
            seg_mask_path=seg_mask_path,
        )
        if mask_overlay_data_url is None:
            mask_overlay_data_url = fallback_mask_overlay_data_url
        if contour_overlay_data_url is None:
            contour_overlay_data_url = fallback_contour_overlay_data_url

    classification_xai_path = result_payload.get("classification_xai_path")
    classification_explanation = GeminiXaiExplanationService._format_for_display(
        result_payload.get("classification_xai_explanation") or ""
    ) or None
    xai_metadata = result_payload.get("xai_metadata") or {}
    ai_tumor_label = _display_tumor_label(
        result_payload.get("tumor_label") or (analysis.tumor_label if analysis else None),
        no_tumor_detected=no_tumor_detected,
    )
    ai_confidence = result_payload.get("classification_confidence")
    if ai_confidence is None and analysis:
        ai_confidence = analysis.classification_confidence
    review_state = classification_review_state(db, image_id, ai_tumor_label, ai_confidence)

    return schemas.ImageAIResultResponse(
        image_id=image_id,
        patient_id=image.patient_id,
        task_id=task_id,
        status=status,
        no_tumor_detected=no_tumor_detected,
        error_message=error_message,
        bbox=bbox,
        bbox_confidence=result_payload.get("bbox_confidence"),
        tumor_label=ai_tumor_label,
        classification_confidence=ai_confidence,
        ai_tumor_label=review_state["ai_tumor_label"],
        ai_confidence=review_state["ai_confidence"],
        final_tumor_label=review_state["final_tumor_label"],
        expert_tumor_label=review_state["expert_tumor_label"],
        expert_comment=review_state["expert_comment"],
        review_required=review_state["review_required"],
        review_status=review_state["review_status"],
        review_action=review_state["review_action"],
        reviewed_at=review_state["reviewed_at"],
        class_probabilities=result_payload.get("class_probabilities"),
        bbox_overlay_data_url=_stored_image_to_data_url(result_payload.get("bbox_image_path")),
        mask_data_url=_stored_image_to_data_url(result_payload.get("seg_mask_path")),
        mask_overlay_data_url=mask_overlay_data_url,
        contour_overlay_data_url=contour_overlay_data_url,
        risk_score=None if no_tumor_detected else (result_payload.get("risk_score") if result_payload.get("risk_score") is not None else (analysis.risk_score if analysis else None)),
        risk_group=None if no_tumor_detected else (result_payload.get("risk_group") or (analysis.risk_group if analysis else None)),
        survival_curve_data=None if no_tumor_detected else (result_payload.get("survival_curve_data") or (analysis.survival_curve_data if analysis else None)),
        multimodal_risk_xai_data_url=_stored_image_to_data_url(result_payload.get("multimodal_risk_xai_path") or result_payload.get("gradcam_heatmap_path")),
        multimodal_gradcam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("multimodal_gradcam_heatmap_path")),
        multimodal_gradcam_plus_heatmap_data_url=_stored_image_to_data_url(result_payload.get("multimodal_gradcam_plus_heatmap_path")),
        multimodal_layercam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("multimodal_layercam_heatmap_path")),
        gradcam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("gradcam_heatmap_path")),
        gradcam_plus_heatmap_data_url=_stored_image_to_data_url(result_payload.get("gradcam_plus_heatmap_path")),
        layercam_heatmap_data_url=_stored_image_to_data_url(result_payload.get("layercam_heatmap_path")),
        detection_xai_data_url=_stored_image_to_data_url(result_payload.get("detection_xai_path") or result_payload.get("odam_path")),
        segmentation_xai_data_url=_stored_image_to_data_url(result_payload.get("segmentation_xai_path") or result_payload.get("seg_eigen_cam_path")),
        classification_xai_data_url=_stored_image_to_data_url(classification_xai_path),
        xai_methods=result_payload.get("xai_methods"),
        xai_warnings=result_payload.get("xai_warnings"),
        xai_metadata=xai_metadata,
        xai_explanation=result_payload.get("xai_explanation"),
        classification_xai_explanation=classification_explanation,
        multimodal_xai_explanation=result_payload.get("multimodal_xai_explanation") or result_payload.get("xai_explanation"),
        fusion_attention=result_payload.get("fusion_attention"),
        rna_xai=result_payload.get("rna_xai"),
        is_series=image.is_series,
        num_slices=image.num_slices,
        key_slice_index=image.key_slice_index,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.post("/records/analysis/image/{image_id}/explain/classification", response_model=schemas.ClassificationXAIExplanationResponse)
def explain_classification_xai(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Khong tim thay anh MRI")

    latest_task = _get_latest_classification_xai_task(db, image)
    analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()
    if not latest_task:
        raise HTTPException(status_code=404, detail="Chua co task chua classification XAI that cho anh nay.")

    result_payload = latest_task.result if latest_task and latest_task.result else {}
    tumor_label = result_payload.get("tumor_label") or (analysis.tumor_label if analysis else None)
    classification_confidence = result_payload.get("classification_confidence")
    if classification_confidence is None and analysis:
        classification_confidence = analysis.classification_confidence
    heatmap_path = result_payload.get("classification_xai_path")
    if not _stored_file_exists(heatmap_path):
        raise HTTPException(
            status_code=404,
            detail="Chua co heatmap classification XAI. Hay chay MRI analysis truoc.",
        )

    xai_metadata = (result_payload.get("xai_metadata") or {}).get("classification") or {}
    if not xai_metadata:
        raise HTTPException(
            status_code=404,
            detail="Chua co metadata classification XAI trong task result. Hay chay lai MRI analysis that.",
        )

    existing_explanation = GeminiXaiExplanationService._format_for_display(
        result_payload.get("classification_xai_explanation") or ""
    )
    if existing_explanation:
        return schemas.ClassificationXAIExplanationResponse(
            image_id=image_id,
            patient_id=image.patient_id,
            explanation_type="classification_xai",
            model_name=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
            content=existing_explanation,
            rag_context=(result_payload.get("xai_explanation_metadata") or {}).get("classification"),
            xai_metadata=xai_metadata,
        )

    contexts = []
    rag_diagnostics = {}
    rag_error: str | None = None

    try:
        rag_service = get_xai_rag_service()
        contexts, rag_diagnostics = rag_service.retrieve_classification_context(
            tumor_label=tumor_label,
            classification_confidence=classification_confidence,
            xai_metadata=xai_metadata,
            top_k=3,
            candidate_k=10,
        )
    except Exception as exc:
        rag_error = str(exc)
        rag_diagnostics = {
            "retrieval_error": rag_error,
            "fallback": "metadata_only_explanation",
        }

    try:
        gemini_service = GeminiXaiExplanationService()
        explanation_text = gemini_service.generate_classification_explanation(
            tumor_label=tumor_label,
            classification_confidence=classification_confidence,
            heatmap_path=heatmap_path,
            xai_metadata=xai_metadata,
            contexts=contexts,
            rag_diagnostics=rag_diagnostics,
        )
    except HTTPException:
        raise
    except Exception as exc:
        explanation_text = _build_classification_xai_fallback(
            tumor_label=tumor_label,
            classification_confidence=classification_confidence,
            xai_metadata=xai_metadata,
            technical_note=rag_error or str(exc),
        )

    rag_context = {
        "diagnostics": rag_diagnostics,
        "contexts": [
            {
                "child_id": context.child_id,
                "parent_id": context.parent_id,
                "score": context.score,
                "source_title": context.source_title,
                "source_url": context.source_url,
                "labels": context.labels,
                "child_preview": context.child_text[:500],
            }
            for context in contexts
        ],
    }

    latest_result = dict(latest_task.result or {})
    latest_result["classification_xai_explanation"] = explanation_text
    latest_result.setdefault("xai_explanation_metadata", {})["classification"] = {
        "rag": rag_context,
        "model_name": os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    }
    latest_task.result = latest_result
    db.commit()

    return schemas.ClassificationXAIExplanationResponse(
        image_id=image_id,
        patient_id=image.patient_id,
        explanation_type="classification_xai",
        model_name=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        content=explanation_text,
        rag_context=rag_context,
        xai_metadata=xai_metadata,
    )


@router.get("/records/analysis/image/{image_id}/slice/{slice_index}")
def get_slice_image(
    image_id: int,
    slice_index: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Khong tim thay anh MRI")

    if not image.is_series:
        # If not series, just return the only slice
        slice_index = 0

    bucket_name, folder_prefix = _parse_minio_path(image.file_path)
    # List objects in folder and sort to find the right index
    objects = minio_client.list_objects(bucket_name, prefix=folder_prefix, recursive=True)
    sorted_objects = sorted(list(objects), key=lambda x: x.object_name)

    if slice_index < 0 or slice_index >= len(sorted_objects):
        raise HTTPException(status_code=404, detail="Index lat cat khong hop le")

    target_obj = sorted_objects[slice_index]
    try:
        url = minio_client.presigned_get_object(bucket_name, target_obj.object_name)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Khong the tao URL lat cat MRI") from exc

    return RedirectResponse(url=url)


@router.get("/records/analysis/image/{image_id}/report")
def download_image_report(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Khong tim thay anh MRI")

    latest_task = _get_latest_mri_task(db, image_id)
    # Cũng tìm prognosis task theo patient_id nếu không có mri_pipeline task
    prognosis_task = (
        db.query(models.InferenceTask)
        .filter(
            models.InferenceTask.task_type == "prognosis",
            models.InferenceTask.target_id == image.patient_id,
        )
        .order_by(models.InferenceTask.created_at.desc())
        .first()
    )
    analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()
    if not analysis:
        analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.patient_id == image.patient_id).first()
    if not latest_task and not prognosis_task and not analysis:
        raise HTTPException(status_code=404, detail="Chua co ket qua de xuat bao cao")

    # Merge results from both task types
    result_payload = {}
    if latest_task and latest_task.result:
        result_payload.update(latest_task.result)
    if prognosis_task and prognosis_task.result:
        if result_payload:
            result_payload = _merge_prognosis_only(result_payload, prognosis_task.result)
        else:
            result_payload.update(prognosis_task.result)
    no_tumor_detected = bool(result_payload.get("no_tumor_detected") or (analysis and getattr(analysis, "no_tumor_detected", False)))
    tumor_label = _display_tumor_label(
        result_payload.get("tumor_label") or (analysis.tumor_label if analysis else None),
        no_tumor_detected=no_tumor_detected,
    )
    classification_confidence = result_payload.get("classification_confidence")
    if classification_confidence is None and analysis:
        classification_confidence = analysis.classification_confidence
    classification_xai_explanation = GeminiXaiExplanationService._format_for_display(
        result_payload.get("classification_xai_explanation") or ""
    ) or None
    if not classification_xai_explanation:
        classification_xai_path = result_payload.get("classification_xai_path")
        classification_xai_metadata = (result_payload.get("xai_metadata") or {}).get("classification") or {}
        if classification_xai_path and _stored_file_exists(classification_xai_path) and classification_xai_metadata:
            try:
                rag_service = get_xai_rag_service()
                contexts, rag_diagnostics = rag_service.retrieve_classification_context(
                    tumor_label=tumor_label,
                    classification_confidence=classification_confidence,
                    xai_metadata=classification_xai_metadata,
                    top_k=3,
                    candidate_k=10,
                )
                gemini_service = GeminiXaiExplanationService()
                classification_xai_explanation = gemini_service.generate_classification_explanation(
                    tumor_label=tumor_label,
                    classification_confidence=classification_confidence,
                    heatmap_path=classification_xai_path,
                    xai_metadata=classification_xai_metadata,
                    contexts=contexts,
                    rag_diagnostics=rag_diagnostics,
                )

                xai_task = latest_task
                if not (
                    xai_task
                    and isinstance(xai_task.result, dict)
                    and xai_task.result.get("classification_xai_path")
                ):
                    xai_task = prognosis_task

                if xai_task:
                    latest_result = dict(xai_task.result or {})
                    latest_result["classification_xai_explanation"] = classification_xai_explanation
                    xai_task.result = latest_result
                    db.commit()
            except Exception as exc:
                print(f"[Warning] Classification XAI explanation for PDF failed: {exc}")
    patient = db.query(models.Patient).filter(models.Patient.id == image.patient_id).first()
    patient_code = patient.patient_external_id if patient and patient.patient_external_id else str(image.patient_id)
    report_id = f"RPT-{patient_code}-{image_id}"
    best_task = latest_task or prognosis_task
    processing_date = (
        best_task.updated_at.strftime("%Y-%m-%d %H:%M") if best_task and best_task.updated_at else "N/A"
    )
    
    try:
        pdf_bytes = _build_professional_report_pdf(
            report_id=report_id,
            patient_code=patient_code,
            image_id=image_id,
            status=(best_task.status if best_task else "done"),
            processing_date=processing_date,
            tumor_label=tumor_label,
            classification_confidence=classification_confidence,
            bbox_confidence=result_payload.get("bbox_confidence"),
            bbox=result_payload.get("bbox"),
            class_probabilities=result_payload.get("class_probabilities"),
            no_tumor_detected=no_tumor_detected,
            multimodal_available=False if no_tumor_detected else bool((analysis and (analysis.risk_score is not None or analysis.risk_group)) or result_payload.get("risk_group")),
            original_image=_load_image_for_report(minio_file_path=image.file_path, local_path=result_payload.get("original_image_path")),
            bbox_image=_load_image_for_report(local_path=result_payload.get("bbox_image_path")),
            cropped_roi_image=_load_image_for_report(local_path=result_payload.get("cropped_roi_path")),
            mask_image=_load_image_for_report(local_path=result_payload.get("seg_mask_path")),
            overlay_image=_load_image_for_report(local_path=result_payload.get("mask_overlay_path"))
            or _load_image_for_report(local_path=result_payload.get("masked_roi_path")),
            risk_score=None if no_tumor_detected else (result_payload.get("risk_score") if result_payload.get("risk_score") is not None else (analysis.risk_score if analysis else None)),
            risk_group=None if no_tumor_detected else (result_payload.get("risk_group") or (analysis.risk_group if analysis else None)),
            survival_curve_data=None if no_tumor_detected else (result_payload.get("survival_curve_data") or (analysis.survival_curve_data if analysis else None)),
            heatmap_image=_bgr_path_to_pil(result_payload.get("multimodal_risk_xai_path") or result_payload.get("gradcam_heatmap_path")),
            gradcam_plus_image=_bgr_path_to_pil(result_payload.get("multimodal_gradcam_plus_heatmap_path") or result_payload.get("gradcam_plus_heatmap_path")),
            layercam_image=_bgr_path_to_pil(result_payload.get("multimodal_layercam_heatmap_path") or result_payload.get("layercam_heatmap_path")),
            detection_xai_image=_bgr_path_to_pil(result_payload.get("detection_xai_path") or result_payload.get("odam_path")),
            segmentation_xai_image=_bgr_path_to_pil(result_payload.get("segmentation_xai_path") or result_payload.get("seg_eigen_cam_path")),
            classification_xai_image=_bgr_path_to_pil(result_payload.get("classification_xai_path")),
            classification_xai_explanation=classification_xai_explanation,
            xai_explanation=result_payload.get("multimodal_xai_explanation") or result_payload.get("xai_explanation"),
            fusion_attention=[v if v is not None else 0.0 for v in result_payload["fusion_attention"]] if result_payload.get("fusion_attention") else None,
            is_series=image.is_series,
            num_slices=image.num_slices,
            key_slice_index=image.key_slice_index,
            rna_xai=result_payload.get("rna_xai"),
        )
        import urllib.parse
        p_name = patient.name or "BenhNhan"
        p_id = patient_code
        current_date = datetime.datetime.now().strftime("%d-%m-%Y")
        filename = f"{p_id}_{p_name}_{current_date}.pdf"
        encoded_filename = urllib.parse.quote(filename)

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        try:
            with open("pdf_error.log", "w") as f:
                f.write(error_msg)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Lỗi tạo báo cáo PDF: {str(e)}")

@router.get("/records/analysis/{image_id}/xai-overlay", response_model=schemas.XAIOverlayResponse)
def get_xai_overlay(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail=f"Chua co ket qua XAI cho image_id={image_id}.")

    result = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()
    if not result:
        raise HTTPException(status_code=404, detail=f"Chua co ket qua XAI cho image_id={image_id}.")

    return schemas.XAIOverlayResponse(
        image_id=image_id,
        gradcam_url=_get_presigned_url(result.gradcam_path),
        mask_url=_get_presigned_url(result.mask_path),
    )


@router.get("/analytics/survival/{patient_id}", response_model=schemas.SurvivalCurveResponse)
def get_survival_curve(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    patient = crud.get_patient_for_user(db, patient_id, current_user)
    if not patient:
        raise HTTPException(status_code=404, detail="Khong tim thay benh nhan")

    real_id = patient.id
    result = (
        db.query(models.AnalysisResult)
        .filter(
            models.AnalysisResult.patient_id == real_id,
            models.AnalysisResult.survival_curve_data.isnot(None),
        )
        .order_by(models.AnalysisResult.created_at.desc())
        .first()
    )

    if not result or not result.survival_curve_data:
        raise HTTPException(status_code=404, detail="Chua co du lieu duong cong song con.")

    curve_points = [
        schemas.SurvivalPoint(
            time=point["time"],
            survival_probability=point["survival_probability"],
        )
        for point in result.survival_curve_data
    ]

    return schemas.SurvivalCurveResponse(
        patient_id=real_id,
        risk_group=result.risk_group,
        curve=curve_points,
    )


@router.post("/records/analysis/image/{image_id}/validate", response_model=schemas.ExpertValidationResponse)
def submit_expert_validation(
    image_id: int,
    payload: schemas.ExpertValidationCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Check if image exists
    image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Không tìm thấy hình ảnh.")
        
    validation = models.ExpertValidation(
        image_id=image_id,
        user_id=int(current_user["sub"]),
        rating=payload.rating,
        heatmap_method=payload.heatmap_method,
        comments=payload.comments
    )
    db.add(validation)
    db.commit()
    db.refresh(validation)
    return validation


@router.post("/records/analysis/image/{image_id}/classification-review", response_model=schemas.ClassificationReviewResponse)
def submit_classification_review(
    image_id: int,
    payload: schemas.ClassificationReviewCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    image = crud.get_image_for_user_or_second_opinion(db, image_id, current_user)
    if not image:
        raise HTTPException(status_code=404, detail="Khong tim thay anh MRI")

    analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()
    latest_task = _get_latest_mri_task(db, image_id)
    result_payload = latest_task.result if latest_task and latest_task.result else {}
    ai_label = _display_tumor_label(
        result_payload.get("tumor_label") or (analysis.tumor_label if analysis else None),
        no_tumor_detected=bool(result_payload.get("no_tumor_detected")),
    )
    ai_confidence = result_payload.get("classification_confidence")
    if ai_confidence is None and analysis:
        ai_confidence = analysis.classification_confidence

    expert_label = (payload.expert_tumor_label or "").strip()
    if not expert_label:
        raise HTTPException(status_code=400, detail="Nhan chuyen gia khong duoc de trong")

    review_action = "confirmed" if ai_label and expert_label.lower() == ai_label.lower() else "corrected"
    user_id = crud.current_user_id(current_user)

    review = models.ClassificationReview(
        image_id=image_id,
        patient_id=image.patient_id,
        user_id=user_id,
        ai_tumor_label=ai_label,
        ai_confidence=ai_confidence,
        expert_tumor_label=expert_label,
        expert_comment=payload.expert_comment,
        review_action=review_action,
    )
    db.add(review)
    if user_id is not None:
        second_opinion_request = (
            db.query(models.NeuroSecondOpinionRequest)
            .filter(
                models.NeuroSecondOpinionRequest.case_image_id == image_id,
                models.NeuroSecondOpinionRequest.reviewer_doctor_id == user_id,
                models.NeuroSecondOpinionRequest.status != "Completed",
            )
            .order_by(models.NeuroSecondOpinionRequest.created_at.desc())
            .first()
        )
        if second_opinion_request:
            second_opinion_request.status = "Completed"
            second_opinion_request.completed_at = datetime.datetime.utcnow()
            second_opinion_request.opinion = payload.expert_comment or expert_label
    db.commit()
    db.refresh(review)

    return {
        "id": review.id,
        "image_id": review.image_id,
        "patient_id": review.patient_id,
        "user_id": review.user_id,
        "ai_tumor_label": review.ai_tumor_label,
        "ai_confidence": review.ai_confidence,
        "expert_tumor_label": review.expert_tumor_label,
        "expert_comment": review.expert_comment,
        "final_tumor_label": review.expert_tumor_label,
        "review_action": review.review_action,
        "review_status": review.review_action,
        "review_required": False,
        "created_at": review.created_at,
    }


@router.get("/records/dashboard/stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from sqlalchemy import func
    user_id = crud.current_user_id(current_user)
    
    # 1. Total patients
    total_patients = (
        db.query(models.Patient)
        .filter(models.Patient.owner_user_id == user_id)
        .count()
    )
    
    # 2. Tumor distribution
    tumor_counts = (
        db.query(models.AnalysisResult.tumor_label, func.count(models.AnalysisResult.id))
        .join(models.Patient, models.AnalysisResult.patient_id == models.Patient.id)
        .filter(models.Patient.owner_user_id == user_id)
        .group_by(models.AnalysisResult.tumor_label)
        .all()
    )
    tumor_distribution = {label or "Unknown": count for label, count in tumor_counts}
    
    # 3. Risk group distribution
    risk_counts = (
        db.query(models.AnalysisResult.risk_group, func.count(models.AnalysisResult.id))
        .join(models.Patient, models.AnalysisResult.patient_id == models.Patient.id)
        .filter(models.Patient.owner_user_id == user_id)
        .group_by(models.AnalysisResult.risk_group)
        .all()
    )
    risk_distribution = {group or "N/A": count for group, count in risk_counts}
    
    # 4. Average Sanity Check rating
    avg_rating_result = (
        db.query(func.avg(models.ExpertValidation.rating))
        .join(models.Image, models.ExpertValidation.image_id == models.Image.id)
        .join(models.Patient, models.Image.patient_id == models.Patient.id)
        .filter(models.Patient.owner_user_id == user_id)
        .scalar()
    )
    avg_rating = round(float(avg_rating_result), 1) if avg_rating_result else 0.0
    
    # 5. Total validations
    total_validations = (
        db.query(models.ExpertValidation)
        .join(models.Image, models.ExpertValidation.image_id == models.Image.id)
        .join(models.Patient, models.Image.patient_id == models.Patient.id)
        .filter(models.Patient.owner_user_id == user_id)
        .count()
    )
    
    return {
        "total_patients": total_patients,
        "tumor_distribution": tumor_distribution,
        "risk_distribution": risk_distribution,
        "average_validation_rating": avg_rating,
        "total_validations": total_validations
    }

@router.get("/records/export/research-data")
def export_research_data(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import csv
    from io import StringIO
    user_id = crud.current_user_id(current_user)
    
    # Lấy tất cả validations cùng với thông tin analysis result
    validations = (
        db.query(models.ExpertValidation, models.AnalysisResult)
        .join(models.AnalysisResult, models.ExpertValidation.image_id == models.AnalysisResult.image_id)
        .join(models.Patient, models.AnalysisResult.patient_id == models.Patient.id)
        .filter(models.Patient.owner_user_id == user_id)
        .all()
    )
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "Validation ID", "Image ID", "Patient ID", "Expert User ID", 
        "Rating (1-5)", "Heatmap Method", "Comments", "Created At",
        "Tumor Label", "Risk Group", "Risk Score"
    ])
    
    for val, analysis in validations:
        writer.writerow([
            val.id, val.image_id, analysis.patient_id, val.user_id,
            val.rating, val.heatmap_method, val.comments, val.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            analysis.tumor_label, analysis.risk_group, analysis.risk_score
        ])
        
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=research_clinical_validation_data.csv"}
    )
