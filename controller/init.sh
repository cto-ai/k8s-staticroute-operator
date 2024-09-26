#!/bin/sh
/sbin/ip rule flush table 60
/sbin/ip route flush table 60
#### PREPARE ENVIRONMENT
sysctl -w net.ipv4.tcp_fwmark_accept=1
sysctl -w net.ipv4.fib_multipath_hash_policy=1

# CREATES A ROUTE TABLE ONLY FOR STATIC-ROUTE CONTROLLER
/sbin/ip route add 127.0.0.1 dev lo scope host src 127.0.0.1 table 60
/sbin/ip rule add priority 200 from all lookup 60