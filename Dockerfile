# Build frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
# Install dependencies (using npm ci for faster, reliable builds)
RUN npm install
COPY frontend/ .
# Build the application
RUN npm run build

# Build backend
FROM python:3.10-slim
WORKDIR /app

# Create a non-root user for security (ModelScope standard)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

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

# Install backend dependencies
WORKDIR /app/backend
ENV PYTHONPATH=/app
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Ensure data directory is writable
RUN mkdir -p /app/backend/data && chmod 777 /app/backend/data

# Expose the port that ModelScope expects (7860)
EXPOSE 7860

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
