# Build frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
ARG VITE_BASE_PATH=/
ARG VITE_API_BASE_URL=
ARG VITE_QIZHI_AUTH_REQUIRED=false
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_QIZHI_AUTH_REQUIRED=${VITE_QIZHI_AUTH_REQUIRED}
COPY frontend/package*.json ./
# Install dependencies using npm ci for reproducible builds
RUN npm ci
COPY frontend/ .
# Build the application
RUN npm run build

# Build backend
FROM python:3.10-slim
WORKDIR /app

# Use the same CJK font family for capacity checks and render every PPT page for OCR QA.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        libreoffice-impress \
        poppler-utils && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user for security (ModelScope standard)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    SLIDE_LIBREOFFICE_AUDIT_ENABLED=true

# Copy requirements first to leverage Docker cache
COPY --chown=user backend/requirements.txt /app/backend/requirements.txt

# Install backend dependencies
WORKDIR /app/backend
ENV PYTHONPATH=/app
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend files with correct ownership
COPY --chown=user backend/ /app/backend/
COPY --chown=user shared/ /app/shared/

# Setup startup script and data seeding
COPY --chown=user backend/start.sh /app/backend/start.sh
RUN chmod +x /app/backend/start.sh && \
    mkdir -p /app/backend/data_seed && \
    cp -r /app/backend/data/* /app/backend/data_seed/ || true

# Copy frontend build artifacts to backend static directory
# This allows FastAPI to serve the frontend
COPY --from=frontend-builder --chown=user /app/frontend/dist /app/backend/static

# Ensure data directory is writable by the app user
RUN mkdir -p /app/backend/data && chmod 755 /app/backend/data

# Expose the port that ModelScope expects (7860)
EXPOSE 7860

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
