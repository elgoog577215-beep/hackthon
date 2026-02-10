# Stage 1: Build Frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend

# Copy package files and install dependencies
COPY frontend/package*.json ./
RUN npm install

# Copy source code and build
COPY frontend/ .
RUN npm run build

# Stage 2: Setup Backend and Runtime
FROM python:3.10-slim
WORKDIR /app

# Copy backend requirements and install dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source code
COPY backend/ ./backend/

# Copy built frontend assets from builder stage
# We'll place them in a 'static' directory inside backend for easy serving
COPY --from=frontend-builder /app/frontend/dist /app/backend/static

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=7860

# Expose the port required by ModelScope
EXPOSE 7860

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
