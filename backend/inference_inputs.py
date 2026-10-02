"""Identify the data used by a patient prognosis, beyond the selected MRI."""

import hashlib
import json

import models


def prognosis_input_signature(db, patient, image_id: int | None) -> str:
    image = db.query(models.Image).filter_by(id=image_id, patient_id=patient.id).first() if image_id is not None else None
    wsi = (
        db.query(models.Image)
        .filter_by(patient_id=patient.id, modality="WSI_SERIES")
        .order_by(models.Image.scan_date.desc(), models.Image.id.desc())
        .first()
    )
    rna = db.query(models.RnaData).filter_by(patient_id=patient.id).first()
    clinical = db.query(models.ClinicalData).filter_by(patient_id=patient.id).first()
    sources = {
        "image": [image.id, image.file_path] if image else None,
        "wsi": [wsi.id, wsi.file_path] if wsi else None,
        "rna": [rna.id, rna.file_path] if rna else None,
        "clinical": [clinical.id, str(clinical.updated_at)] if clinical else None,
        "age": patient.age,
        "gender": patient.gender,
    }
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
