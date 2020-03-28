FROM python:buster

RUN apt-get update && rm -rf /var/lib/apt/lists/*

RUN mkdir /app
COPY ./ /app

WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 8000
CMD [ "uvicorn", "application:app", "--host=0.0.0.0", "--port=8000" ]