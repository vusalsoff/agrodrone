# AgroDrone Cloud Deployment (Vercel + Railway)

Kompüter sönülü olsa belə proqramın **istənilən telefondan 24/7 işləməsi** üçün ən rahat və peşəkar üsul:
* **Backend + OpenCV + YOLOv8 + PostgreSQL → Railway**
* **Frontend (Next.js) → Vercel**

---

## 1. Backend-i Railway-ə yükləmək (`infra/docker/Dockerfile.cloud`)
1. Layihəni GitHub reposuna push edin.
2. [Railway](https://railway.app)-də **New Project → Deploy from GitHub Repo** seçin (`railway.toml` avtomatik olaraq `Dockerfile.cloud`-u seçəcək).
3. Eyni layihəyə **+ New → Database → PostgreSQL** əlavə edin (`DATABASE_URL` avtomatik veriləcək).
4. Railway **Variables** bölməsində bunları təyin edin:
   * `ENVIRONMENT=production`
   * `JWT_SECRET_KEY=<uzun-təsadüfi-açar>` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   * `COOKIE_SECURE=true`
   * `COOKIE_SAMESITE=lax`
   * `CORS_ORIGINS=["https://sizin-app.vercel.app"]`
   * `STORAGE_BACKEND=local` *(və ya S3/R2)*
   * `ALLOW_DIRECT_LOCAL_CAMERA_PROBE=false`
5. Railway sizə HTTPS ünvan verəcək (məsələn: `https://agrodrone-api.up.railway.app`).

## 2. Frontend-i Vercel-ə yükləmək (`apps/web`)
1. [Vercel](https://vercel.com)-də **Add New Project** → eyni GitHub reposunu seçin.
2. **Root Directory** olaraq **`apps/web`** göstərin.
3. **Environment Variables** bölməsində əlavə edin:
   * `BACKEND_INTERNAL_URL=https://agrodrone-api.up.railway.app`
   * `NEXT_PUBLIC_ENVIRONMENT=production`
4. **Deploy** düyməsinə basın.

Hazırdır! Vercel sizə daimi `https://sizin-app.vercel.app` linkini verəcək — **kompütersiz istənilən telefondan** daxil olub telefon kamerası ilə bitki xəstəliyi analizi edə bilərsiniz.
