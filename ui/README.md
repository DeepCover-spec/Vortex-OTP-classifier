# OTP Shield website

Plain HTML, CSS, and JavaScript. Near-black background, neon green accents. No build step and no npm packages.

The browser calls the API at `window.OTP_API_BASE` from `ui/config.js`. The default is `http://127.0.0.1:8000`. That value is not a secret. Change it when the API is on another host. Docker rewrites `config.js` on container start from the environment variable `OTP_API_BASE` (same meaning: the URL the browser should call).

Website port on the host: **8080**. The container listens on port **80**.

## Without Docker

From this folder:

```powershell
python -m http.server 8080
```

Open http://127.0.0.1:8080 . The API must already be running and must allow this origin. CORS is configured on the API, not on this page.

## Docker image

From the repository root, without changing `docker-compose.yml`:

```powershell
docker build -f docker/Dockerfile.ui -t otp-shield-ui .
docker run --rm -p 8080:80 -e OTP_API_BASE=http://127.0.0.1:8000 otp-shield-ui
```

`127.0.0.1` in `OTP_API_BASE` is the browser's machine, which is what you want when you open the site on the same computer as the API.

## Compose snippet for Hisshan

Do not apply this here. Hisshan adds the service. He also needs the API to allow origins `http://127.0.0.1:8080` and `http://localhost:8080`.

```yaml
  ui:
    build:
      context: .
      dockerfile: docker/Dockerfile.ui
    ports:
      - "8080:80"
    environment:
      OTP_API_BASE: http://127.0.0.1:8000
```
