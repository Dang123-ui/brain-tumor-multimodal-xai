import csv
import io
import os
import unittest
import zipfile
from unittest.mock import Mock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from inference_inputs import prognosis_input_signature
from routers.inference import _reusable_task
from routers import multimodal, upload
from rna_import import prepare_rna_file
from utils import get_current_user


def read_matrix(content):
    return list(csv.reader(io.StringIO(content.decode("utf-8"))))


class RnaImportTests(unittest.TestCase):
    def prepare(self, content, **kwargs):
        return prepare_rna_file(
            content, delimiter=kwargs.pop("delimiter", ","),
            target_patient_id="UCSF-003", patient_aliases={"UCSF-003", "3"}, **kwargs,
        )

    def test_single_sample_can_be_assigned_without_changing_gene_values(self):
        source = b"patient_id,ENSG001,ENSG002\nTCGA-12-1093,1.000000000000001,2.5\n"
        result = self.prepare(source)
        self.assertEqual(read_matrix(result.content)[1], ["UCSF-003", "1.000000000000001", "2.5"])
        self.assertEqual(result.num_genes, 2)
        self.assertIn(b"TCGA-12-1093", source)

    def test_matching_sample_is_selected_from_a_multi_patient_matrix(self):
        result = self.prepare(b"patient_id,ENSG001\nTCGA-12-1093,9\n3,4.2\n")
        self.assertEqual(read_matrix(result.content), [["patient_id", "ENSG001"], ["UCSF-003", "4.2"]])

    def test_ambiguous_multi_sample_file_is_not_flattened_into_one_patient(self):
        with self.assertRaisesRegex(ValueError, "nhiều mẫu"):
            self.prepare(b"patient_id,ENSG001\nA,1\nB,2\n")

    def test_missing_patient_column_is_added_to_a_single_sample(self):
        result = self.prepare(b"ENSG001,ENSG002\n1,2\n")
        self.assertEqual(read_matrix(result.content)[0], ["patient_id", "ENSG001", "ENSG002"])
        self.assertEqual(result.num_genes, 2)

    def test_tsv_and_blank_expression_values_remain_pipeline_readable(self):
        result = self.prepare(b"patient_id\tENSG001\tENSG002\nTCGA-12-1093\t\t2.3\n", delimiter="\t")
        self.assertIn(b"UCSF-003\t0\t2.3", result.content)

    def test_invalid_and_nonfinite_gene_values_are_rejected(self):
        for value in (b"not-a-number", b"NaN", b"Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.prepare(b"patient_id,ENSG001\nA," + value + b"\n")

    def test_inconsistent_row_width_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "không khớp"):
            self.prepare(b"patient_id,ENSG001\nA,1,2\n")


class MultimodalUploadTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        owner = models.User(username="owner", hashed_password="unused", role="doctor")
        outsider = models.User(username="outsider", hashed_password="unused", role="doctor")
        self.db.add_all([owner, outsider])
        self.db.flush()
        self.source = models.Patient(owner_user_id=owner.id, patient_external_id="TCGA-12-1093")
        self.target = models.Patient(owner_user_id=owner.id, patient_external_id="UCSF-003")
        other = models.Patient(owner_user_id=outsider.id, patient_external_id="OTHER-PATIENT")
        self.db.add_all([self.source, self.target, other])
        self.db.commit()

        app = FastAPI()
        app.include_router(multimodal.router)
        app.include_router(upload.router)
        def override_db():
            yield self.db
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: {"user_id": owner.id, "role": "doctor"}
        self.client = TestClient(app)
        self.stored = {}
        self.storage = Mock()
        self.storage.bucket_exists.return_value = True
        def store(**kwargs):
            self.stored[kwargs["object_name"]] = kwargs["data"].read()
        self.storage.put_object.side_effect = store
        for target in ("routers.multimodal.minio_client", "routers.upload.multimodal_minio_client"):
            patcher = patch(target, self.storage)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_tcga_rna_upload_is_attached_to_patient_c(self):
        data = b"patient_id,ENSG001,ENSG002\nTCGA-12-1093,1.2,3.4\n"
        response = self.client.post(
            "/upload/rna/?patient_id=UCSF-003",
            files={"file": ("TCGA-12-1093.csv", data, "text/csv")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["patient_id"], self.target.id)
        self.assertEqual(response.json()["num_genes"], 2)
        self.assertEqual(read_matrix(next(iter(self.stored.values())))[1], ["UCSF-003", "1.2", "3.4"])
        self.assertEqual(self.db.query(models.RnaData).filter_by(patient_id=self.source.id).count(), 0)

    def test_numeric_patient_id_works_and_reupload_updates_the_same_record(self):
        first_id = None
        for value in ("1.2", "4.2"):
            response = self.client.post(
                f"/upload/rna/?patient_id={self.target.id}",
                files={"file": ("sample.csv", f"patient_id,ENSG001\nA,{value}\n".encode(), "text/csv")},
            )
            self.assertEqual(response.status_code, 200, response.text)
            if first_id is None:
                first_id = response.json()["id"]
            self.assertEqual(response.json()["id"], first_id)
        self.assertEqual(self.db.query(models.RnaData).filter_by(patient_id=self.target.id).count(), 1)

    def test_upload_cannot_assign_rna_to_another_users_patient(self):
        response = self.client.post(
            "/upload/rna/?patient_id=OTHER-PATIENT",
            files={"file": ("sample.csv", b"patient_id,ENSG001\nA,1\n", "text/csv")},
        )
        self.assertEqual(response.status_code, 404)
        self.storage.put_object.assert_not_called()

    def test_ambiguous_matrix_returns_a_useful_validation_error(self):
        response = self.client.post(
            "/upload/rna/?patient_id=UCSF-003",
            files={"file": ("sample.csv", b"patient_id,ENSG001\nA,1\nB,2\n", "text/csv")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("nhiều mẫu", response.json()["detail"])
        self.storage.put_object.assert_not_called()

    def test_wsi_archive_upload_attaches_tiles_to_selected_patient(self):
        image = io.BytesIO()
        Image.new("RGB", (16, 16), (140, 60, 100)).save(image, format="PNG")
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("tiles/patch_1.png", image.getvalue())
            archive.writestr("tiles/patch_2.png", image.getvalue())
            archive.writestr("README.md", "not an image")
        with patch("ai_core.utils.wsi_filter.WSITileFilter") as tile_filter:
            tile_filter.return_value.score_tiles.return_value = [(1, 0.8), (0, 0.7)]
            response = self.client.post(
                "/upload/wsi/series?patient_id=UCSF-003",
                files={"zip_file": ("TCGA-12-1093_WSI.zip", archive_bytes.getvalue(), "application/zip")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["num_valid_tiles"], 2)
        record = self.db.query(models.Image).filter_by(id=response.json()["image_id"]).one()
        self.assertEqual(record.patient_id, self.target.id)
        self.assertEqual(record.modality, "WSI_SERIES")
        self.assertEqual(len(self.stored), 2)
        self.assertTrue(all(name.endswith(".png") for name in self.stored))

    def test_broken_wsi_zip_has_a_clear_error(self):
        response = self.client.post(
            "/upload/wsi/series?patient_id=UCSF-003",
            files={"zip_file": ("broken.zip", b"not a zip", "application/zip")},
        )
        self.assertEqual(response.status_code, 422)
        self.storage.put_object.assert_not_called()

    def test_new_rna_and_wsi_prevent_reusing_a_completed_prognosis(self):
        image = models.Image(patient_id=self.target.id, modality="MRI", file_path="/data/mri.png")
        self.db.add(image)
        self.db.flush()
        initial_signature = prognosis_input_signature(self.db, self.target, image.id)
        old_task = models.InferenceTask(
            task_type="prognosis", target_id=self.target.id, status="done",
            celery_task_id="before-upload",
            result={"image_id": image.id, "input_signature": initial_signature},
        )
        self.db.add(old_task)
        self.db.commit()
        self.assertIsNotNone(_reusable_task(self.db, "prognosis", self.target.id, image.id, initial_signature))

        rna = models.RnaData(patient_id=self.target.id, file_path="/data/new-rna.csv", file_format="csv")
        self.db.add(rna)
        self.db.commit()
        rna_signature = prognosis_input_signature(self.db, self.target, image.id)
        self.assertNotEqual(initial_signature, rna_signature)
        self.assertIsNone(_reusable_task(self.db, "prognosis", self.target.id, image.id, rna_signature))

        self.db.add(models.Image(patient_id=self.target.id, modality="WSI_SERIES", file_path="/data/new-wsi/"))
        self.db.commit()
        wsi_signature = prognosis_input_signature(self.db, self.target, image.id)
        self.assertNotEqual(rna_signature, wsi_signature)
        rna.file_path = "/data/replacement-rna.csv"
        self.db.commit()
        self.assertNotEqual(wsi_signature, prognosis_input_signature(self.db, self.target, image.id))

    def test_same_inputs_reuse_the_running_task(self):
        image = models.Image(patient_id=self.target.id, modality="MRI", file_path="/data/mri.png")
        self.db.add(image)
        self.db.flush()
        signature = prognosis_input_signature(self.db, self.target, image.id)
        running = models.InferenceTask(
            task_type="prognosis", target_id=self.target.id, status="processing",
            celery_task_id="running-task",
            result={"image_id": image.id, "input_signature": signature},
        )
        self.db.add(running)
        self.db.commit()
        task = _reusable_task(self.db, "prognosis", self.target.id, image.id, signature)
        self.assertEqual(task.id, running.id)


if __name__ == "__main__":
    unittest.main()
