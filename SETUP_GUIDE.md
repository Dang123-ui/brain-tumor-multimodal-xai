# Setup Guide - NeuroDiagnosis AI

Tai lieu nay huong dan tu dau de chay du an theo 2 che do:

```text
1. Local:
   Frontend local + Backend local + Worker + PostgreSQL + Redis + MinIO

2. Deploy tunnel:
   Vercel frontend -> Cloudflare Quick Tunnel -> Backend local + Worker + PostgreSQL + Redis -> Cloudflare R2
```

Luu y quan trong:

- Khi chay local thi dung MinIO.
- Khi deploy tunnel thi dung Cloudflare R2, khong can MinIO.
- Backend va worker deu phai chay vi worker xu ly job AI/XAI.
- Cloudflare Quick Tunnel chi hoat dong khi may ca nhan va cua so `cloudflared` dang bat.
- URL `trycloudflare.com` se doi moi lan tat/mo lai `cloudflared`.

## 1. Phan mem can co

Cai tren Windows:

- Docker Desktop
- Git
- Node.js
- cloudflared

Kiem tra trong PowerShell:

```powershell
docker --version
docker compose version
git --version
node --version
npm --version
cloudflared --version
```

## 2. Clone hoac cap nhat source code

Neu chua co source:

```powershell
git clone <REPO_URL> NeuroProject
cd NeuroProject
```

Neu da co source:

```powershell
cd D:\Nghien_cuu_khoa_hoc\Web\NeuroProject
git checkout main
git pull origin main
```

## 3. Chay local

Local dung file:

```text
docker-compose.yml
```

Thanh phan local:

```text
db + redis + minio + backend + worker + frontend
```

Build lan dau:

```powershell
docker compose build
```

Chay local:

```powershell
docker compose up -d
```

Kiem tra backend:

```powershell
curl.exe http://localhost:8000/health
```

Mo Swagger:

```text
http://localhost:8000/docs
```

Mo MinIO:

```text
http://localhost:9001
```

Thong tin MinIO local mac dinh:

```text
Username: admin
Password: password123
```

Chay frontend local:

```powershell
cd frontend
npm install
notepad .env.local
```

Noi dung `frontend/.env.local` khi test local:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Chay frontend:

```powershell
npm run dev
```

Mo:

```text
http://localhost:3000
```

Tai khoan mac dinh:

```text
Username: admin
Password: 123456
```

## 4. Chuan bi deploy tunnel

Deploy tunnel dung file:

```text
docker-compose.tunnel.yml
```

Thanh phan deploy tunnel:

```text
db + redis + backend + worker + Cloudflare R2 + cloudflared
```

Tao file env tunnel:

```powershell
Copy-Item .env.tunnel.example .env.tunnel
notepad .env.tunnel
```

Dien cac bien quan trong:

```text
POSTGRES_DB=neuroproject
POSTGRES_USER=neuroproject
POSTGRES_PASSWORD=<MAT_KHAU_POSTGRES>

MINIO_URL=<ACCOUNT_ID>.r2.cloudflarestorage.com
MINIO_ACCESS_KEY=<R2_ACCESS_KEY_ID>
MINIO_SECRET_KEY=<R2_SECRET_ACCESS_KEY>
MINIO_SECURE=true
MINIO_REGION=auto
MINIO_BUCKET=analysis-results
R2_BUCKET=analysis-results

SECRET_KEY=<CHUOI_RANDOM_DAI>
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=http://localhost:3000

GEMINI_API_KEY=<GEMINI_API_KEY>
GEMINI_MODEL=gemini-3.1-flash-lite

HF_API_TOKEN=<HF_API_TOKEN>
HF_API_TIMEOUT=300
HF_EMBEDDING_API_URL=https://router.huggingface.co/hf-inference/models/BAAI/bge-m3/pipeline/feature-extraction
HF_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
HF_RERANKER_API_URL=https://router.huggingface.co/hf-inference/models/BAAI/bge-reranker-v2-m3
```

Tao `SECRET_KEY`:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

## 5. Build va chay backend deploy tunnel

Neu local dang chay va dang giu port 8000, tat local truoc:

```powershell
docker compose stop
```

Build image AI chung cho backend va worker:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel build backend
```

Lenh tren tao image:

```text
neuroproject-ai:latest
```

Chay tunnel stack:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d
```

Kiem tra:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel ps
curl.exe http://localhost:8000/health
```

Ket qua dung:

```json
{"status":"ok"}
```

## 6. Mo Cloudflare Quick Tunnel

Mo mot cua so PowerShell moi va giu cua so nay luon mo:

```powershell
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Copy URL dang:

```text
https://abc-def-xyz.trycloudflare.com
```

Test tunnel:

```powershell
curl.exe https://abc-def-xyz.trycloudflare.com/health
```

Neu tra ve:

```json
{"status":"ok"}
```

thi backend public qua tunnel da chay duoc.

## 7. Deploy frontend len Vercel

Vao Vercel va import GitHub repo.

Trong project settings:

```text
Framework Preset: Next.js
Root Directory: frontend
Build Command: npm run build
Output Directory: de trong
Install Command: de trong hoac npm install
```

Trong `Settings -> Environments -> Production -> Environment Variables`, them:

```text
NEXT_PUBLIC_API_URL=https://abc-def-xyz.trycloudflare.com
```

Trong do `https://abc-def-xyz.trycloudflare.com` la URL Cloudflare Tunnel dang chay.

Sau khi them env, phai redeploy frontend:

```text
Deployments -> Redeploy -> Clear Build Cache
```

Build dung se co log:

```text
Running "npm run build"
next build --webpack
Next.js ... (webpack)
Compiled successfully
Deployment completed
```

Mo domain Vercel production, vi du:

```text
https://neurodiagnosisai.vercel.app
```

## 8. Cap nhat CORS backend theo URL Vercel

Sau khi co URL Vercel that, sua file `.env.tunnel`:

```text
FRONTEND_URL=https://neurodiagnosisai.vercel.app
CORS_ORIGINS=http://localhost:3000,https://neurodiagnosisai.vercel.app
```

Restart backend:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d --force-recreate backend
```

Test lai:

```powershell
curl.exe http://localhost:8000/health
curl.exe https://abc-def-xyz.trycloudflare.com/health
```

## 9. Thu tu chay moi lan deploy

Moi lan muon chay deploy tunnel:

```powershell
docker compose stop
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Sau khi cloudflared in URL moi:

1. Copy URL `trycloudflare.com` moi.
2. Vao Vercel `Settings -> Environments -> Production`.
3. Sua `NEXT_PUBLIC_API_URL` thanh URL moi.
4. Redeploy frontend.
5. Neu URL Vercel thay doi, cap nhat `FRONTEND_URL` va `CORS_ORIGINS` trong `.env.tunnel`.
6. Recreate backend de nap lai bien moi:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d --force-recreate backend
```

## 10. Doi qua lai giua local va deploy

Chuyen sang local:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel stop
docker compose up -d
```

Chuyen sang deploy tunnel:

```powershell
docker compose stop
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

## 11. Cac loi hay gap

### Vercel hien 404 NOT_FOUND

Kiem tra:

```text
Framework Preset phai la Next.js
Root Directory phai la frontend
Output Directory phai de trong
Deployment phai Ready
Mo dung domain production trong Settings -> Domains
```

### Vercel build dung Turbopack va fail

Kiem tra `frontend/package.json`:

```json
"build": "next build --webpack"
```

Kiem tra `frontend/next.config.ts` co:

```ts
turbopack: {},
```

Sau do commit, push va redeploy.

### Port 8000 bi chiem

Tat stack dang giu port:

```powershell
docker compose stop
```

hoac:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel stop
```

### cloudflared loi QUIC

Dung HTTP/2:

```powershell
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

### Upload WSI/RNA cho benh nhan duoc chon

Trong trang Upload, nhap ma benh nhan can nhan du lieu. WSI chap nhan ZIP chua tiles anh hoac nhieu file anh. File RNA CSV/TSV mot mau duoc gan cho benh nhan nay, ke ca khi patient_id trong file la ma mau goc khac; gia tri gene duoc giu nguyen. File nhieu mau can co mot dong trung ma benh nhan, hoac can tach rieng mau muon dung truoc khi upload.

Sau khi them/thay WSI, RNA hoac lam sang, chay lai pipeline de tinh ket qua voi dau vao moi. He thong chi dung lai job cu khi cac dau vao khong thay doi. Upload WSI khong thay the MRI dang duoc chon; neu da co MRI, pipeline lay MRI moi nhat cua benh nhan khi chua chon file MRI moi.

Sau khi cap nhat source tren stack tunnel dang chay, nap lai backend va worker luc khong co job dang xu ly:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel restart backend worker
```

### Pipeline dung o 5% hoac bao IncompleteRead khi tai R2

Worker tu thu lai toi da 3 lan khi ket noi bi ngat, bao gom ca loi doc file giua chung. Du lieu tai thieu se bi bo va file duoc tai lai toan bo. Ket noi co timeout 10 giay, doc du lieu co timeout 30 giay; WSI tai toi da 4 anh dong thoi va hien so anh da tai tren thanh tien trinh.

Sau khi cap nhat source, recreate worker de nap code moi:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d --no-deps --force-recreate worker
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel logs --tail 100 worker
```

Chi recreate khi worker khong dang xu ly job. Worker dung `--pool=threads --concurrency=1` de van phan hoi kiem tra trong luc xu ly AI. Neu job da bao failed, chay lai pipeline tren dung anh MRI; loi file khong ton tai hoac khong co quyen R2 can sua du lieu/quyen truy cap.

### Giai thich XAI bi Hugging Face timeout

Tang timeout trong `.env.tunnel`:

```text
HF_API_TIMEOUT=300
```

Sau do recreate backend:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d --force-recreate backend
```

### Frontend goi backend bi CORS

Sua `.env.tunnel`:

```text
CORS_ORIGINS=http://localhost:3000,https://neurodiagnosisai.vercel.app
```

Restart backend:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d --force-recreate backend
```

## 12. Khong nen dung lenh nay neu con can data

Khong dung:

```powershell
docker compose down -v
```

Vi `-v` se xoa volume database/MinIO.

Neu chi muon tat container:

```powershell
docker compose stop
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel stop
```
