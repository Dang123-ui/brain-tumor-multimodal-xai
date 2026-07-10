# Brain Tumor Multimodal XAI

An end-to-end clinical decision support system for brain tumor analysis that combines:

- MRI diagnosis with detection, segmentation, and classification
- multimodal prognosis from MRI, WSI, RNA-seq, and clinical data
- explainable AI for both visual and genomic evidence
- a production-style web platform for asynchronous AI inference and reporting

This repository is built from the student research project:

_Development of a Multimodal Deep Learning Model with XAI for Brain Tumor Diagnosis and Prognosis_

## Highlights

- MRI pipeline with **YOLOv11 + DynUNet + DenseNet169**
- Multimodal prognosis with **gated attention fusion + CoxPH risk modeling**
- XAI stack with **ODAM**, **Seg-Eigen-CAM**, **Finer-CAM**, and **Grad-CAM family**
- Web CDSS architecture using **Next.js**, **FastAPI**, **Celery**, **Redis**, **PostgreSQL**, and object storage
- Quantitative evaluation summarized from the full thesis report

![Key experimental highlights](assets/readme/results/metrics_highlights.svg)

## Project Scope

The system is organized around three core modules described in the project report:

1. **MRI diagnosis module**
   - tumor detection
   - tumor segmentation
   - tumor classification
   - per-stage explainability

2. **Multimodal prognosis module**
   - MRI, WSI, RNA-seq, and clinical feature fusion
   - Cox proportional hazards risk estimation
   - visual and genomic explainability

3. **Clinical web platform**
   - patient management
   - asynchronous inference orchestration
   - result review, XAI visualization, and reporting

## System Architecture

### 3-layer MRI analysis and XAI architecture

This figure is adapted from the full report and shows the application layer, AI inference layer, and XAI/storage layer used by the MRI workflow.

![3-layer MRI and XAI architecture](assets/readme/architecture_3layer_mri_xai.png)

### MRI workflow with XAI, RAG, and report generation

The MRI branch starts from raw input, runs detection, segmentation, and classification, then stores XAI artifacts and supports language-based explanation.

![MRI pipeline with XAI and RAG](assets/readme/mri_pipeline_xai_rag_flow.png)

### Multimodal prognosis architecture

The prognosis branch fuses MRI, WSI, RNA, and clinical embeddings using attention-based feature fusion before CoxPH risk prediction.

![Multimodal fusion architecture](assets/readme/multimodal_fusion_architecture.png)

## Explainable AI Design

The project uses different XAI mechanisms for different prediction tasks instead of forcing one heatmap method onto every branch.

### Detection XAI: ODAM

![ODAM workflow](assets/readme/xai_odam_diagram.png)

### Segmentation XAI: Seg-Eigen-CAM

![Seg-Eigen-CAM workflow](assets/readme/xai_seg_eigen_cam_diagram.png)

### Classification XAI: Finer-CAM

![Finer-CAM workflow](assets/readme/xai_finer_cam_diagram.png)

## Experimental Results

The following summary is derived from the full report and the packaged experiment outputs included in this repository.

### Technical objectives vs achieved results

![Technical targets vs achieved metrics](assets/readme/results/objectives_vs_results.svg)

Key MRI diagnosis metrics reported in the thesis:

- **Detection**
  - Precision: **95.25%**
  - Recall: **86.20%**
  - F1-score: **90.50%**
  - mAP@50: **85.39%**

- **Segmentation**
  - Dice: **92.77%**
  - IoU: **87.03%**
  - Sensitivity: **92.77%**
  - Specificity: **96.83%**

- **Classification**
  - Accuracy: **97.55%**
  - Macro-F1: **97.54%**
  - ROC-AUC: **99.45%**
  - Inference time: **0.029 s**

### XAI quantitative summary

![XAI quantitative summary](assets/readme/results/xai_quantitative_summary.svg)

Representative XAI findings highlighted in the report:

- **ODAM** explains the detection branch well
  - Pointing game on bbox: **98.98%**
  - Confidence drop@20 when masking important region: **82.55%**

- **Seg-Eigen-CAM** explains the segmentation branch well
  - Pointing to GT mask: **99.08%**

- **Finer-CAM** captures class-discriminative evidence
  - Drop@20: **23.77%**
  - Relative drop@20: **41.50%**

### Example outputs

MRI detection result:

![MRI detection example](assets/readme/examples/mri_detection_example.png)

MRI segmentation result:

![MRI segmentation example](assets/readme/examples/mri_segmentation_example.png)

Classification XAI example:

![Classification XAI example](assets/readme/examples/mri_classification_xai_example.png)

Multimodal prognosis XAI example:

![Multimodal prognosis XAI example](assets/readme/examples/multimodal_risk_xai_example.png)

## Repository Structure

```text
.
├── backend/        FastAPI APIs, AI pipeline integration, async task orchestration
├── frontend/       Next.js clinical dashboard
├── assets/readme/  README figures and exported report diagrams
├── notebooks/      Research and experiment notebooks
├── scratch/        Intermediate experiment/report artifacts
├── test_output/    Sample generated MRI outputs
├── docker-compose.yml
├── docker-compose.tunnel.yml
└── README.md
```

## Technology Stack

### Application layer

- Next.js
- React
- TypeScript
- Tailwind CSS

### Backend and orchestration

- FastAPI
- Celery
- Redis
- PostgreSQL
- MinIO / object storage

### AI and XAI

- YOLOv11
- DynUNet
- DenseNet169
- CoxPH-based multimodal prognosis
- ODAM
- Seg-Eigen-CAM
- Finer-CAM
- Grad-CAM / Grad-CAM++ / LayerCAM

## Quick Start

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Expected frontend environment:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_USE_MOCK_DATA=false
```

### Backend and infrastructure

```bash
docker compose up --build
```

This starts the main backend services used by the web platform and asynchronous AI workflow.

### API documentation

Once the backend is running:

```text
http://localhost:8000/docs
```

## Research Notes

The thesis report describes the project in six major parts:

- motivation and problem setting
- literature review
- theoretical background
- proposed architecture and system design
- experiments and evaluation
- conclusions and future directions

The README intentionally focuses on the implementation-facing summary, while the full report provides the detailed academic discussion, data protocol, and metric interpretation.

## Authors

- Pham Huynh Quoc Dat
- Nguyen Hai Dang
- Vuong Quoc An

Academic advisor:

- Dr. Trinh Hung Cuong

## Acknowledgment

The architecture figures and result summaries in this README are adapted from the attached thesis report and the experiment artifacts packaged with this repository.
