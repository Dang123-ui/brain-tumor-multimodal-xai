# Chay local va deploy tunnel

Du an co 2 che do rieng:

```text
LOCAL:
docker-compose.yml
db + redis + minio + backend + worker + frontend

DEPLOY TUNNEL:
docker-compose.tunnel.yml
db + redis + backend + worker + R2 + cloudflared
```

Backend va worker dung chung 1 image:

```text
neuroproject-ai:latest
```

## 1. Build lai tu dau

Neu da xoa het image/container, build lai image AI chung:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel build backend
```

Lenh nay tao image:

```text
neuroproject-ai:latest
```

Worker dung lai image nay, khong can build rieng.

## 2. Chay deploy tunnel

Dam bao local dang tat de khong dung port 8000:

```powershell
docker compose stop
```

Chay deploy:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d
```

Test backend:

```powershell
curl http://localhost:8000/health
```

Mo Cloudflare Tunnel:

```powershell
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Copy URL dang:

```text
https://abc-def-xyz.trycloudflare.com
```

Test tunnel:

```powershell
curl https://abc-def-xyz.trycloudflare.com/health
```

Gan URL nay vao Vercel:

```text
Project Settings -> Environment Variables
NEXT_PUBLIC_API_URL=https://abc-def-xyz.trycloudflare.com
```

Sau khi sua `NEXT_PUBLIC_API_URL`, redeploy frontend tren Vercel. Vercel khong doc
`frontend/.env.local`; file do chi dung khi chay local.

## 3. Chay local

Tat deploy tunnel truoc:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel stop
```

Chay local:

```powershell
docker compose up -d
```

Mo:

```text
Frontend: http://localhost:3000
Backend:  http://localhost:8000/docs
MinIO:    http://localhost:9001
```

## 4. Doi qua lai

Muon deploy:

```powershell
docker compose stop
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Muon local:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel stop
docker compose up -d
```

## 5. Khi nao moi build

Chi build khi:

```text
doi Dockerfile
doi requirements.txt
xoa image
muon lam lai tu dau
```

Build:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel build backend
```

Chay lai:

```powershell
docker compose -f docker-compose.tunnel.yml --env-file .env.tunnel up -d
```

Khong dung:

```powershell
docker compose down -v
```

Neu khong muon xoa volume database/MinIO.

cloudflared tunnel --protocol http2 --url http://localhost:8000

Luu y database:

```text
Local mac dinh:  docker-compose.yml + postgres volume local
Deploy tunnel:   docker-compose.tunnel.yml + .env.tunnel + postgres_data rieng
```

Khong chay `docker compose down -v` neu muon giu database. Lenh do xoa volume.
