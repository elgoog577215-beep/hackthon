# KnowledgeMap AI Learning Assistant

A modern, AI-powered learning assistant that generates structured course maps and provides detailed answers.

## Features

- **Interactive Course Tree**: Visualizes knowledge structure with infinite nesting.
- **AI-Generated Content**: Automatically generates courses, chapters, and detailed explanations.
- **Contextual Q&A**: Ask questions based on specific nodes for precise answers.
- **Modern UI**: Glassmorphism design with smooth animations and responsive layout.
- **Bilingual Support**: Fully localized in Chinese.

## Project Structure

- `frontend/`: Vue 3 + Vite + Element Plus + Tailwind CSS
- `backend/`: FastAPI + Python
- `data/`: JSON storage for course trees and annotations

## Getting Started

### Backend

1. Navigate to `backend` directory:
   ```bash
   cd backend
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the server:
   ```bash
   uvicorn main:app --reload
   ```
   Server runs at `http://localhost:8000`.

### Frontend

1. Navigate to `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run development server:
   ```bash
   npm run dev
   ```
   Access the app at `http://localhost:5173`.

## Configuration

- **AI Service**: By default, the system uses a Mock AI service for demonstration. To use a real LLM (e.g., Qwen), set the `AI_API_KEY` environment variable in `backend/.env` (create if needed).

## License

MIT
