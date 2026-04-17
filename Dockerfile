# ---- Stage 1: Build the React frontend ----
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Python application ----
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Overwrite with freshly built frontend artifacts
COPY --from=frontend-build /build/dist /app/frontend/dist
CMD ["python", "main.py"]
