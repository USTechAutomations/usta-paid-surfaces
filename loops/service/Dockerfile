# The loops service, ready for Cloud Run.
#
# Build from the REPO ROOT, not from this folder:
#     docker build -f loops/service/Dockerfile -t usta-loops .
#
# The build sends the whole repo as context. Put a .dockerignore at the repo
# root holding at least these lines, or the build will drag the test virtual
# environment along with it:
#     loops/service/.venv
#     **/__pycache__
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY loops/service/requirements.txt /app/loops/service/requirements.txt
RUN pip install --no-cache-dir -r /app/loops/service/requirements.txt

COPY loops /app/loops
# The shared stylesheet, so the pages can fingerprint the link they emit.
COPY styles.css /app/styles.css
# The one site header and footer (brand/shell.py), so these pages carry the
# same shell as every built page.
COPY brand /app/brand
# The virtual environment and the tests are for the build machine only.
RUN rm -rf /app/loops/service/.venv /app/loops/service/tests /app/loops/lib/test_prokey.py \
 && find /app -name '__pycache__' -type d -prune -exec rm -rf {} + \
 && useradd --create-home --uid 10001 loops \
 && chown -R loops:loops /app

USER loops
EXPOSE 8080

# Cloud Run hands the port in as PORT. It is 8080 unless someone changes it.
#
# --no-access-log is not optional. Left on, the web server writes a line per
# request holding the visitor's network address, and this system is not allowed
# to store one anywhere. Cloud Run keeps its own request log outside the
# container, which is where request counts come from.
CMD ["sh", "-c", "exec uvicorn loops.service.app:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
