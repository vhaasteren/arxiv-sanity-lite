# Instead, look at this: https://cobuildlab.com/development-blog/deploying-python-wsgi-application-using-Docker/
# Or better, this: https://github.com/tiangolo/uwsgi-nginx-flask-docker

#FROM ubuntu:latest
FROM tiangolo/uwsgi-nginx-flask:python3.7

RUN apt-get update -y && \
    apt-get install -y python3-pip python3-dev build-essential && \
    apt-get install -y ghostscript && \
    apt-get install -y vim && \
    apt-get install -y cron

COPY . /app
WORKDIR /app
RUN pip3 install -r requirements.txt

# If STATIC_INDEX is 1, serve / with /static/index.html directly (or the static URL configured)
#ENV STATIC_INDEX 1
ENV STATIC_INDEX 0

# For the cron job description, see:
# https://medium.com/@jonbaldie/how-to-run-cron-jobs-inside-docker-containers-26964315b582
COPY crontab /etc/cron.d/scrape-arxiv
RUN chmod 0644 /etc/cron.d/scrape-arxiv
RUN crontab /etc/cron.d/scrape-arxiv
RUN sed -i '$ d' /entrypoint.sh && \
    echo 'service cron start \n\
exec "$@"' >> /entrypoint.sh

ENV PYTHONBUFFERED 1
RUN service cron start
CMD cron -f

# Deal with the Imagemagick security issue
RUN sed -i_bak 's/rights="none" pattern="PDF"/rights="read | write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml

# Google cloud CLI
#RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg  add - && apt-get update -y && apt-get install google-cloud-cli -y

# When running the ubuntu image (not the uwsgi nginx image):
#ENTRYPOINT ["python3"]

ENV FLASK_APP serve.py
CMD ["flask", "run", "--host=0.0.0.0", "--port=80"]
EXPOSE 80
