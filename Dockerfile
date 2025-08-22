FROM python:3.13

WORKDIR /app

COPY ./app /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt