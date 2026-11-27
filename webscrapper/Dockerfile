# Imagen Lambda de la etapa 1: captura de los KID.
# Construir desde la raíz del repo: docker build -f webscrapper/Dockerfile .
FROM public.ecr.aws/lambda/python:3.14

COPY webscrapper/requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY common/ ${LAMBDA_TASK_ROOT}/common/
COPY webscrapper/*.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
