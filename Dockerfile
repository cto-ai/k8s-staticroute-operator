FROM python:3.10-alpine

WORKDIR /controller
COPY requirements.txt ./
RUN apk add libcap && \
    pip install -r "requirements.txt" && \
    # python interpreter needs NET_ADMIN privileges to alter routes on the host
    setcap 'cap_net_admin+ep' $(readlink -f $(which python))
COPY controller/ ./
RUN chmod +x start.sh
ENTRYPOINT [ "/bin/sh","start.sh"]
