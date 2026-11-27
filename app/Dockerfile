# Imagen de la aplicación web (Streamlit), desplegada en ECS Express Mode.
# Construir desde la raíz del repo: docker build -f app/Dockerfile .
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código, configuración (.streamlit/config.toml) y recursos estáticos (tipografía y logotipo)
COPY app/ .

# La aplicación no necesita privilegios de administrador dentro del contenedor
RUN useradd --create-home --uid 10001 kid
USER kid

EXPOSE 8501
CMD ["streamlit", "run", "kid_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
