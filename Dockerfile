FROM python:3.7-slim

COPY . /webrender

WORKDIR webrender

RUN \
  pip install -r requirements.txt

EXPOSE 8010

CMD gunicorn -c gunicorn.ini webrender.wrengine:app
