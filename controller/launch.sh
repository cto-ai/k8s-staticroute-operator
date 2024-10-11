#!/bin/sh
ACTION=$1

if [ -z "${ACTION}" ];
then
    setcap 'cap_net_admin+ep' $(readlink -f $(which python))
    kopf run --all-namespaces static-route-handler.py
    exit 0
fi

if [ "${ACTION}" == "debug" ];
then
    tail -f /dev/null
    exit 0
fi

if [ "${ACTION}" == "service" ];
then
    cd service
    python service.py
    exit 0
fi

if [ "${ACTION}" == "init" ];
then
    /bin/sh /controller/init.sh
    exit 0
fi

if [ "${ACTION}" == "worker" ];
then
    cd worker
    python worker.py
    exit 0
fi

