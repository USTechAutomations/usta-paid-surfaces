# Small, official Apify base image with Python 3.11 already set up.
FROM apify/actor-python:3.11

COPY requirements.txt ./
RUN echo "Python:" && python --version \
 && pip install --no-cache-dir -r requirements.txt

COPY . ./

CMD ["python3", "main.py"]
