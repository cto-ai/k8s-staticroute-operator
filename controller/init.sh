#!/bin/sh
GATEWAY_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/gateway)
PUBLIC_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address)

/sbin/ip rule flush table 50
/sbin/ip route flush table 50

/sbin/ip rule flush table 60
/sbin/ip route flush table 60

#### PREPARE BEFORE MARKING
#sysctl -w net.ipv4.tcp_fwmark_accept=1
sysctl -w net.ipv4.fib_multipath_hash_policy=1
#COPING eth0 routes

/sbin/ip route show scope link dev eth0 | awk '{print $1" "$5}' | xargs -n 2 sh -c '/sbin/ip route add $0 dev eth0 src $1 table 50'
/sbin/ip route show scope link dev eth1 | awk '{print $1" "$5}' | xargs -n 2 sh -c '/sbin/ip route add $0 dev eth1 src $1 table 50'
/sbin/ip route show scope link dev docker0 | awk '{print $1" "$5}' | xargs -n 2 sh -c '/sbin/ip route add $0 dev docker0 src $1 table 50'

DST=$(ip route list dev cilium_host | grep via | awk '{print $1}')
GW=$(ip route list dev cilium_host | grep via | awk '{print $3}')
SRC=$(/sbin/ip route show scope link dev cilium_host | awk '{print $1}')


/sbin/ip route add $SRC dev cilium_host table 50
/sbin/ip route add $DST via $GW dev cilium_host src $SRC table 50

PUBLIC_IP=$(curl -s http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address)
PUBLIC_SUBNET=$(/sbin/ip route show scope link dev eth0 | grep $PUBLIC_IP | awk '{print $1}')

/sbin/ip route add default via $GATEWAY_IP dev eth0 table 50

/sbin/ip rule add from $GATEWAY_IP table 50 
/sbin/ip rule add to $GATEWAY_IP table 50 

# CREATES A ROUTE TABLE ONLY FOR STATIC-ROUTE CONTROLLER
/sbin/ip route add 127.0.0.1 dev lo scope host src 127.0.0.1 table 60
/sbin/ip rule add priority 200 from all lookup 60