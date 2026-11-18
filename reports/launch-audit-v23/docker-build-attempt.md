# ID 93 local image-build attempt

Date: 2026-11-17 (local Windows host)

- Started Docker Desktop because it was installed but stopped; `docker info --format '{{.ServerVersion}} {{.OperatingSystem}}'` returned `29.6.2 Docker Desktop`.
- `docker compose config --quiet` passed after the engine started.
- Started `docker build --tag paperplane-v23-audit:local .` using the project Dockerfile and `.dockerignore`; the project Compose stack and its persistent volumes were not started or mounted.
- Debian package indexes fetched 10.1 MB at 70.0 KB/s. The runtime apt layer then reported 372 MB of package archives and 1,333 MB additional installed space for LibreOffice, OCR, Ghostscript, ICC profiles, Chromium, and dependencies.
- Stopped the build during package downloads. The image was not completed; no container replacement/redeploy persistence test ran. This is evidence of local engine availability and the image's resource/network cost, not proof of deployment readiness.
