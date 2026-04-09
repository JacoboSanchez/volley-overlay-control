FROM zauberzeug/nicegui:3.10.0
WORKDIR /app
COPY . /app
RUN uv pip install -r requirements.txt