# Use pre-built frontend assets instead of building in Docker
# This ensures consistency and speeds up deployment
FROM python:3.10-slim
WORKDIR /app

# Copy backend requirements and install dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source code
COPY backend/ ./backend/

# Copy pre-built frontend assets
# Note: frontend/dist must be present in the build context
COPY frontend/dist /app/backend/static

# Set environment variables
ENV PYTHONPATH=/app
ENV PORT=7860

# Expose the port required by ModelScope
EXPOSE 7860

# Run the application
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
