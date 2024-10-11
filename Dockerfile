FROM python:3.10-alpine

WORKDIR /controller
RUN apk add coreutils libcap iptables iproute2 curl sqlite
RUN mkdir -p /controller/requirements
WORKDIR /controller/requirements
COPY requirements.txt ./
COPY controller/service/requirements.txt ./requirements-service.txt
COPY controller/worker/requirements.txt ./requirements-worker.txt
RUN pip install -r "requirements.txt"
RUN pip install -r "requirements-service.txt"
RUN pip install -r "requirements-worker.txt"
WORKDIR /controller
COPY controller/ ./
RUN chmod +x launch.sh
RUN chmod +x init.sh
RUN mkdir /db && sqlite3 /db/router.db
ENTRYPOINT ["/bin/sh","launch.sh"]
