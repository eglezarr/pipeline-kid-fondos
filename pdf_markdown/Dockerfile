# Imagen Lambda de la etapa 2: conversión de los KID de PDF a Markdown (con OCR).
# Construir desde la raíz del repo: docker build -f pdf_markdown/Dockerfile .
FROM public.ecr.aws/lambda/python:3.14

COPY pdf_markdown/requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

# RapidOCR descarga sus modelos la primera vez que se usa; en Lambda el código es de solo
# lectura, así que se descargan aquí, al construir la imagen.
RUN PYTHONPATH="${LAMBDA_TASK_ROOT}" python -c "from rapidocr import RapidOCR; RapidOCR()"

COPY common/ ${LAMBDA_TASK_ROOT}/common/
COPY pdf_markdown/pdf_a_markdown.py pdf_markdown/app.py ${LAMBDA_TASK_ROOT}/

CMD ["app.handler"]
