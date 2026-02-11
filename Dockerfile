# Stage 1: Build Frontend
FROM node:22-alpine as frontend-build
WORKDIR /app/frontend

# Copy package files first to leverage cache
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install

# Copy source code
COPY frontend/ ./

# Build with empty API base URL for relative paths in production
# This ensures the frontend talks to the same origin (the FastAPI backend)
RUN VITE_API_BASE_URL="" npm run build

# Stage 2: Backend & Final Image
FROM python:3.10-slim
WORKDIR /app

# Copy backend requirements and install dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source code
COPY backend/ ./backend/

# Copy built frontend assets from Stage 1
# This mounts the Vue app to the static directory served by FastAPI
COPY --from=frontend-build /app/frontend/dist /app/backend/static

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=7860

# Expose the port required by ModelScope
EXPOSE 7860

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
