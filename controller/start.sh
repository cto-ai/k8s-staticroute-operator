#!/bin/sh
sysctl -w net.ipv4.fib_multipath_hash_policy=1
kopf run --all-namespaces --verbose static-route-handler.py