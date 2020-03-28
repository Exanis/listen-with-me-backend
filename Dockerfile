FROM python:buster

RUN apt-get update && rm -rf /var/lib/apt/lists/*

RUN mkdir /app
COPY ./requirements.txt /app

WORKDIR /app
RUN pip install -r requirements.txt
COPY ./ /app
EXPOSE 8000
CMD [ "uvicorn", "application:app", "--host=0.0.0.0", "--port=8000" ]