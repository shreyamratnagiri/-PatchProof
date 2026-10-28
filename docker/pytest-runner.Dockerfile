# Trusted image build with registry access. No downloads occur at test runtime.
# Production workers only use this locally built, explicitly approved image.
FROM python:3.12-alpine
RUN python -m pip install --no-cache-dir --disable-pip-version-check pytest==9.0.2
USER 65534:65534
WORKDIR /workspace
