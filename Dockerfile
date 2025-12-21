FROM zauberzeug/nicegui:latest
WORKDIR /app
COPY . /app
RUN uv pip install -r requirements.txt