import os
import io
import re
import sys
import importlib
import importlib.util
import mimetypes
import shutil
import tempfile
from typing import TYPE_CHECKING

from celery import shared_task
import numpy as np
import pandas as pd
import torch

import models
from database import SessionLocal
from utils import ensure_bucket_exists, minio_client

CURRENT_DIR = os.path.dirname(__file__)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

if TYPE_CHECKING:
    from ai_core.pipeline import TumorAnalysisPipeline

WEIGHTS_DIR = os.path.join(CURRENT_DIR, "ai_core", "weights")
RESULTS_BUCKET = os.getenv("MINIO_BUCKET") or os.getenv("R2_BUCKET") or "analysis-results"
ai_pipeline: "TumorAnalysisPipeline | None" = None


def _upload_result_files_to_minio(result: dict, prefix: str) -> dict:
    """Upload generated pipeline files to MinIO and replace local paths by MinIO paths."""
    ensure_bucket_exists(RESULTS_BUCKET)
    clean_result = dict(result)

    for key, value in list(clean_result.items()):
        if not (isinstance(value, str) and value and os.path.isfile(value)):
            continue

        filename = os.path.basename(value)
        object_name = f"{prefix}/{filename}"
        content_type = mimetypes.guess_type(value)[0] or "application/octet-stream"

        minio_client.fput_object(
            bucket_name=RESULTS_BUCKET,
            object_name=object_name,
            file_path=value,
            content_type=content_type,
        )
        clean_result[key] = f"/{RESULTS_BUCKET}/{object_name}"

    return clean_result


def _load_pipeline_class():
    ai_core_dir = os.path.join(CURRENT_DIR, "ai_core")
    ai_core_init = os.path.join(ai_core_dir, "__init__.py")

    if CURRENT_DIR not in sys.path:
        sys.path.insert(0, CURRENT_DIR)

    if "ai_core" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "ai_core",
            ai_core_init,
            submodule_search_locations=[ai_core_dir],
        )
        if spec is None or spec.loader is None:
            raise ImportError("Khong the tao import spec cho package 'ai_core'.")

        module = importlib.util.module_from_spec(spec)
        sys.modules["ai_core"] = module
        spec.loader.exec_module(module)

    pipeline_module = importlib.import_module("ai_core.pipeline")
    return pipeline_module.TumorAnalysisPipeline


def get_ai_pipeline() -> "TumorAnalysisPipeline":
    global ai_pipeline
    if ai_pipeline is None:
        TumorAnalysisPipeline = _load_pipeline_class()
        # Detect device: use cuda if available
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[CELERY WORKER] Khoi tao pipeline tren thiet bi: {device}")
        ai_pipeline = TumorAnalysisPipeline(weights_dir=WEIGHTS_DIR, device=device)
    return ai_pipeline


@shared_task(name="tasks.run_mri_pipeline", bind=True)
def run_mri_pipeline(self, task_id: int, image_id: int):
    """MRI -> YOLOv11 -> ROI -> U-Net -> DenseNet169 classify."""
    print(f"[CELERY WORKER] Nhan task MRI. Task ID: {task_id} | Image ID: {image_id}")
    db = SessionLocal()

    try:
        task_record = db.query(models.InferenceTask).filter(models.InferenceTask.id == task_id).first()
        if not task_record:
            return {"error": "Khong tim thay InferenceTask"}

        task_record.status = "processing"
        db.commit()

        image_record = db.query(models.Image).filter(models.Image.id == image_id).first()
        if not image_record:
            raise Exception(f"Khong tim thay anh MRI voi image_id={image_id}")

        output_dir = tempfile.mkdtemp(prefix=f"neuro_mri_{image_id}_{task_id}_")

        # Fetch RNA data if available
        rna_record = db.query(models.RnaData).filter(models.RnaData.patient_id == image_record.patient_id).first()
        rna_vector = None
        rna_gene_names = None
        if rna_record:
            try:
                rna_bucket, rna_object = _parse_minio_path(rna_record.file_path)
                rna_response = minio_client.get_object(rna_bucket, rna_object)
                try:
                    rna_bytes = rna_response.read()
                finally:
                    rna_response.close()
                    rna_response.release_conn()

                separator = "\t" if rna_record.file_format == "tsv" else ","
                lines = rna_bytes.decode("utf-8").strip().splitlines()
                if not lines:
                    raise Exception("RNA file is empty.")
                headers = [h.strip() for h in lines[0].split(separator)]
                gene_start_idx = -1
                for i, h in enumerate(headers):
                    if h.startswith("ENSG"):
                        gene_start_idx = i
                        break
                if gene_start_idx == -1:
                    gene_start_idx = 1
                data_line = lines[1] if len(lines) > 1 else lines[0]
                parts = data_line.split(separator)
                rna_vector = np.array([float(x) if x.strip() else 0.0 for x in parts[gene_start_idx:]], dtype=np.float32)
                rna_gene_names = headers[gene_start_idx:]
            except Exception as e:
                print(f"[CELERY WORKER] Loi khi doc RNA: {e}")

        # Fetch Clinical data if available
        clinical_record = db.query(models.ClinicalData).filter(models.ClinicalData.patient_id == image_record.patient_id).first()
        clinical_dict = {}
        if clinical_record:
            clinical_dict = {
                "ki67_index": clinical_record.ki67_index,
                "biochemistry_markers": clinical_record.biochemistry_markers,
                "initial_status": clinical_record.initial_status,
            }

        # ── Fetch All Slices if it's a Series ──
        if image_record.is_series:
            bucket_name, folder_prefix = _parse_minio_path(image_record.file_path)
            # List objects in the series folder
            objects = minio_client.list_objects(bucket_name, prefix=folder_prefix, recursive=True)
            image_bytes_list = []
            
            # Sort by name to keep slice order if possible
            sorted_objects = sorted(list(objects), key=lambda x: x.object_name)
            
            for obj in sorted_objects:
                obj_res = minio_client.get_object(bucket_name, obj.object_name)
                try:
                    image_bytes_list.append(obj_res.read())
                finally:
                    obj_res.close()
                    obj_res.release_conn()
            
            print(f"[CELERY WORKER] Dang chay SERIES pipeline voi {len(image_bytes_list)} lat cat.")
            
            def progress_updater(percent, status_text):
                self.update_state(
                    state='PROGRESS',
                    meta={'percent': percent, 'status': status_text}
                )

            result = get_ai_pipeline().run_series_inference(
                image_bytes_list=image_bytes_list,
                rna_data=rna_vector,
                clinical_data=clinical_dict,
                output_dir=output_dir,
                progress_callback=progress_updater,
                rna_gene_names=rna_gene_names
            )
        else:
            # Single image mode
            bucket_name, object_name = _parse_minio_path(image_record.file_path)
            response = minio_client.get_object(bucket_name, object_name)
            try:
                image_bytes = response.read()
            finally:
                response.close()
                response.release_conn()

            def progress_updater(percent, status_text):
                self.update_state(
                    state='PROGRESS',
                    meta={'percent': percent, 'status': status_text}
                )

            result = get_ai_pipeline().run_multimodal_inference(
                image_source=image_bytes,
                rna_data=rna_vector,
                clinical_data=clinical_dict,
                output_dir=output_dir,
                progress_callback=progress_updater,
                rna_gene_names=rna_gene_names
            )

        if result["status"] != "success":
            raise Exception(result["error_msg"])

        result = _upload_result_files_to_minio(
            result=result,
            prefix=f"mri/{image_id}/task-{task_id}",
        )

        task_record.status = "done"
        task_record.result = result

        analysis = db.query(models.AnalysisResult).filter(models.AnalysisResult.image_id == image_id).first()
        if not analysis:
            analysis = models.AnalysisResult(
                patient_id=image_record.patient_id,
                image_id=image_id,
            )
            db.add(analysis)

        no_tumor_detected = bool(result.get("no_tumor_detected"))
        analysis.no_tumor_detected = no_tumor_detected
        analysis.tumor_label = None if no_tumor_detected else result.get("tumor_label")
        analysis.classification_confidence = None if no_tumor_detected else result.get("classification_confidence")
        analysis.mask_path = None if no_tumor_detected else (result.get("seg_mask_path") or None)
        
        # Cập nhật metadata cho series nếu có
        if image_record.is_series:
            image_record.key_slice_index = result.get("key_slice_index", 0)
            image_record.num_slices = result.get("num_slices", image_record.num_slices)

        analysis.risk_score = None if no_tumor_detected else result.get("risk_score")
        analysis.risk_group = None if no_tumor_detected else result.get("risk_group")
        analysis.survival_curve_data = None if no_tumor_detected else result.get("survival_curve_data")
        analysis.finer_cam_path = None if no_tumor_detected else (result.get("classification_xai_path") or result.get("finer_cam_path"))
        analysis.seg_eigen_cam_path = None if no_tumor_detected else (result.get("segmentation_xai_path") or result.get("seg_eigen_cam_path"))
        analysis.odam_path = result.get("detection_xai_path") or result.get("odam_path")
        analysis.xai_3_panel_path = None if no_tumor_detected else result.get("xai_3_panel_path")

        db.commit()

        print(
            f"[CELERY WORKER] MRI {'SERIES' if image_record.is_series else 'SINGLE'} pipeline xong | "
            f"class={result.get('tumor_label')} | key_slice={result.get('key_slice_index')}"
        )
        return {"task_id": task_id, "status": "done"}

    except Exception as exc:
        print(f"[CELERY WORKER] System error: {exc}")
        # Thu hồi giao dịch lỗi ngay lập tức để làm sạch session
        db.rollback()
        try:
            # Tạo một truy vấn mới để ghi nhận trạng thái lỗi
            task_record = db.query(models.InferenceTask).filter(models.InferenceTask.id == task_id).first()
            if task_record:
                task_record.status = "failed"
                task_record.error_message = str(exc)
                db.commit()
        except Exception as commit_exc:
            print(f"[CELERY WORKER] Cannot save error status to database: {commit_exc}")
        return {"task_id": task_id, "status": "failed", "error": str(exc)}
    finally:
        if "output_dir" in locals() and output_dir and os.path.isdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
        db.close()


@shared_task(name="tasks.run_prognosis_pipeline", bind=True)
def run_prognosis_pipeline(self, task_id: int, patient_id: int, image_id: int | None = None):
    """MRI pipeline moi -> masked ROI + RNA + clinical -> multimodal prognosis."""
    print(f"[CELERY WORKER] Nhan task prognosis. Task ID: {task_id} | Patient ID: {patient_id}")
    db = SessionLocal()

    try:
        task_record = db.query(models.InferenceTask).filter(models.InferenceTask.id == task_id).first()
        if not task_record:
            return {"error": "Task not found"}

        task_record.status = "processing"
        db.commit()

        # Thong bao ngay cho Frontend de hien Progress Bar
        print(f"[CELERY WORKER] Bat dau xu ly Prognosis cho Patient {patient_id}. GPU: {torch.cuda.is_available()}")
        self.update_state(
            state='PROGRESS',
            meta={'percent': 5, 'status': "Đang nạp dữ liệu từ kho lưu trữ..."}
        )

        # 1. Tìm ảnh MRI (nếu có)
        mri_query = db.query(models.Image).filter(
            models.Image.patient_id == patient_id,
            models.Image.modality.in_(["MRI", "MRI_SERIES"]),
        )
        if image_id is not None:
            mri_query = mri_query.filter(models.Image.id == image_id)
        else:
            mri_query = mri_query.order_by(models.Image.scan_date.desc())
        mri_record = mri_query.first()
        if image_id is not None and mri_record is None:
            raise ValueError(f"Khong tim thay MRI image_id={image_id} cua patient_id={patient_id}")
        
        mri_bytes = None
        mri_all_bytes = None  # Toàn bộ series bytes (nếu là series)
        is_mri_series = False
        if mri_record:
            image_bucket, folder_or_file = _parse_minio_path(mri_record.file_path)
            if mri_record.is_series:
                is_mri_series = True
                objects = list(minio_client.list_objects(image_bucket, prefix=folder_or_file, recursive=True))
                sorted_objs = sorted(objects, key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', x.object_name)])
                
                # Load TOÀN BỘ slices để pipeline tự quét tìm key slice
                mri_all_bytes = []
                for obj in sorted_objs:
                    resp = minio_client.get_object(image_bucket, obj.object_name)
                    try:
                        mri_all_bytes.append(resp.read())
                    finally:
                        resp.close()
                        resp.release_conn()
            else:
                image_object = folder_or_file
                image_response = minio_client.get_object(image_bucket, image_object)
                try:
                    mri_bytes = image_response.read()
                finally:
                    image_response.close()
                    image_response.release_conn()

        # 2. Tìm WSI Tiles (nếu có)
        wsi_record = (
            db.query(models.Image)
            .filter(
                models.Image.patient_id == patient_id,
                models.Image.modality == "WSI_SERIES",
            )
            .order_by(models.Image.scan_date.desc())
            .first()
        )
        
        wsi_tiles = []
        if wsi_record:
            from concurrent.futures import ThreadPoolExecutor
            wsi_bucket, wsi_folder = _parse_minio_path(wsi_record.file_path)
            objects = list(minio_client.list_objects(wsi_bucket, prefix=wsi_folder, recursive=True))
            
            def load_tile(obj_name):
                resp = minio_client.get_object(wsi_bucket, obj_name)
                try:
                    return resp.read()
                finally:
                    resp.close()
                    resp.release_conn()

            # Tải song song tối đa 10 tiles cùng lúc để tăng tốc độ I/O
            with ThreadPoolExecutor(max_workers=10) as executor:
                wsi_tiles = list(executor.map(lambda o: load_tile(o.object_name), objects))

        # 3. Tìm RNA Data (nếu có)
        rna_record = db.query(models.RnaData).filter(models.RnaData.patient_id == patient_id).first()
        rna_vector = None
        rna_gene_names = None
        if rna_record:
            rna_bucket, rna_object = _parse_minio_path(rna_record.file_path)
            rna_response = minio_client.get_object(rna_bucket, rna_object)
            try:
                rna_bytes = rna_response.read()
            finally:
                rna_response.close()
                rna_response.release_conn()

            separator = "\t" if rna_record.file_format == "tsv" else ","
            df = pd.read_csv(io.BytesIO(rna_bytes), sep=separator)
            numeric_df = df.select_dtypes(include=["number"])
            
            # Loai bo metadata va statistical columns de tranh lech vector gene
            cols_to_drop = ["patient_id", "N_unmapped", "N_multimapping", "N_noFeature", "N_ambiguous"]
            for col in cols_to_drop:
                if col in numeric_df.columns:
                    numeric_df = numeric_df.drop(columns=[col])
                    
            rna_vector = numeric_df.to_numpy(dtype=np.float32).flatten()
            # Lay danh sach ten gene tu cac cot so de truyen vao pipeline phuc vu tinh toan XAI
            rna_gene_names = list(numeric_df.columns)

        # 4. Tìm Clinical Data (nếu có)
        clinical_record = db.query(models.ClinicalData).filter(models.ClinicalData.patient_id == patient_id).first()
        clinical_dict = {}
        if clinical_record:
            clinical_dict = {
                "ki67_index": clinical_record.ki67_index,
                "biochemistry_markers": clinical_record.biochemistry_markers,
                "initial_status": clinical_record.initial_status,
                "age": clinical_record.patient.age,
                "gender": clinical_record.patient.gender,
                "grade": clinical_record.grade,
                "prior_treatment": clinical_record.prior_treatment,
            }

        output_dir = tempfile.mkdtemp(prefix=f"neuro_prognosis_{patient_id}_{task_id}_")

        def progress_updater(percent, status_text):
            self.update_state(
                state='PROGRESS',
                meta={'percent': percent, 'status': status_text}
            )

        # Chạy pipeline tích hợp đầy đủ
        pipeline = get_ai_pipeline()

        if is_mri_series and mri_all_bytes:
            # Series: quét tất cả slices để tự động tìm key slice
            result = pipeline.run_series_inference(
                image_bytes_list=mri_all_bytes,
                wsi_tiles=wsi_tiles,
                rna_data=rna_vector,
                clinical_data=clinical_dict,
                output_dir=output_dir,
                progress_callback=progress_updater,
                rna_gene_names=rna_gene_names
            )
            # Cập nhật key_slice_index trong DB theo kết quả quét thực tế
            new_key_idx = result.get("key_slice_index")
            if new_key_idx is not None and mri_record:
                mri_record.key_slice_index = new_key_idx
        else:
            # Ảnh đơn hoặc không có MRI
            result = pipeline.run_full_prognosis(
                mri_source=mri_bytes,
                wsi_tiles=wsi_tiles,
                rna_data=rna_vector,
                clinical_data=clinical_dict,
                output_dir=output_dir,
                progress_callback=progress_updater,
                rna_gene_names=rna_gene_names
            )

        if result["status"] != "success":
            raise Exception(result.get("error_msg", "Pipeline failed"))

        result = _upload_result_files_to_minio(
            result=result,
            prefix=f"prognosis/{patient_id}/task-{task_id}",
        )

        # Khử giá trị NaN/Inf trước khi lưu vào DB (Postgres không nhận NaN trong JSON)
        def sanitize_json(data):
            if isinstance(data, dict):
                return {k: sanitize_json(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [sanitize_json(v) for v in data]
            elif isinstance(data, float):
                import math
                if math.isnan(data) or math.isinf(data):
                    return None
            return data

        clean_result = sanitize_json(result)
        if mri_record:
            clean_result["image_id"] = mri_record.id

        task_record.status = "done"
        task_record.result = clean_result

        # Prognosis process: attach prognosis to the latest MRI analysis row.
        analysis = None
        if mri_record:
            analysis = db.query(models.AnalysisResult).filter(
                models.AnalysisResult.image_id == mri_record.id
            ).first()
        if not analysis:
            analysis = db.query(models.AnalysisResult).filter(
                models.AnalysisResult.patient_id == patient_id
            ).order_by(models.AnalysisResult.created_at.desc()).first()

        if not analysis:
            analysis = models.AnalysisResult(
                patient_id=patient_id,
                image_id=mri_record.id if mri_record else None,
            )
            db.add(analysis)

        no_tumor_detected = bool(clean_result.get("no_tumor_detected"))
        analysis.no_tumor_detected = no_tumor_detected
        analysis.tumor_label = None if no_tumor_detected else clean_result.get("tumor_label")
        analysis.classification_confidence = None if no_tumor_detected else clean_result.get("classification_confidence")
        analysis.risk_score = None if no_tumor_detected else clean_result.get("risk_score")
        analysis.risk_group = None if no_tumor_detected else clean_result.get("risk_group")
        analysis.survival_curve_data = None if no_tumor_detected else clean_result.get("survival_curve_data")
        analysis.finer_cam_path = None if no_tumor_detected else (clean_result.get("classification_xai_path") or clean_result.get("finer_cam_path"))
        analysis.seg_eigen_cam_path = None if no_tumor_detected else (clean_result.get("segmentation_xai_path") or clean_result.get("seg_eigen_cam_path"))
        analysis.odam_path = clean_result.get("detection_xai_path") or clean_result.get("odam_path")
        analysis.xai_3_panel_path = None if no_tumor_detected else clean_result.get("xai_3_panel_path")

        db.commit()
        return {"status": "done", "patient_id": patient_id}
    except Exception as exc:
        print(f"[CELERY WORKER] Prognosis pipeline system error: {exc}")
        # Thu hồi giao dịch lỗi ngay lập tức để làm sạch session
        db.rollback()
        try:
            # Tạo một truy vấn mới để ghi nhận trạng thái lỗi
            task_record = db.query(models.InferenceTask).filter(models.InferenceTask.id == task_id).first()
            if task_record:
                task_record.status = "failed"
                task_record.error_message = str(exc)
                db.commit()
        except Exception as commit_exc:
            print(f"[CELERY WORKER] Cannot save prognosis error status to database: {commit_exc}")
        return {"status": "failed", "patient_id": patient_id, "error": str(exc)}
    finally:
        if "output_dir" in locals() and output_dir and os.path.isdir(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
        db.close()


def _parse_minio_path(file_path: str) -> tuple[str, str]:
    normalized = file_path.lstrip("/")
    parts = normalized.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Duong dan MinIO khong hop le: {file_path}")
    return parts[0], parts[1]
