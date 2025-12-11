FROM zauberzeug/nicegui:latest
WORKDIR /app
COPY . /app
RUN python3 -m pip install -r requirements.txt