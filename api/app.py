"""Handler de AWS Lambda para la API: Mangum traduce los eventos de la Function URL a peticiones
ASGI para FastAPI (api_fondos.py) y las respuestas de FastAPI al formato que espera Lambda."""

from mangum import Mangum

from api_fondos import app

# Sin eventos de arranque y parada: la aplicación no mantiene conexiones abiertas
handler = Mangum(app, lifespan="off")
