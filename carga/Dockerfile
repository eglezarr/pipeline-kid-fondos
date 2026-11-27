# Imagen Lambda de la etapa 4: carga de los datos extraídos en PostgreSQL (Aurora, RDS Data API).
# Construir desde la raíz del repo: docker build -f carga/Dockerfile .
FROM public.ecr.aws/lambda/python:3.14

COPY carga/requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY common/ ${LAMBDA_TASK_ROOT}/common/
COPY carga/cargar_kids.py carga/app.py carga/esquema.sql ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
