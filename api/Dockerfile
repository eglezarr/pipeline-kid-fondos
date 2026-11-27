# Imagen Lambda de la API HTTP (FastAPI + Mangum), expuesta con una Function URL.
# Construir desde la raíz del repo: docker build -f api/Dockerfile .
FROM public.ecr.aws/lambda/python:3.14

COPY api/requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY common/ ${LAMBDA_TASK_ROOT}/common/
COPY api/api_fondos.py api/app.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
