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

# Copy backend files
COPY backend/ /app/backend/
COPY shared/ /app/shared/

# Copy frontend build artifacts to backend static directory
# This allows FastAPI to serve the frontend
COPY --from=frontend-builder /app/frontend/dist /app/backend/static

# Install backend dependencies
WORKDIR /app/backend
ENV PYTHONPATH=/app
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port that ModelScope expects (7860)
EXPOSE 7860

# Command to run the application
# Using shell form to allow variable expansion if needed, but here we stick to exec form for signal handling
# We default to port 7860 which is standard for HuggingFace/ModelScope Spaces
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
