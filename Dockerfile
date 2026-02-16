FROM zauberzeug/nicegui:3.6.1
WORKDIR /app
COPY . /app
RUN uv pip install -r requirements.txt