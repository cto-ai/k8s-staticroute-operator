import os, sys, time
import logging
import requests
import json
from ping3 import ping
from pyroute2 import IPRoute
from socket import AF_INET
from utils import valid_ip_address
from constants import DEFAULT_GW_CIDR
from constants import NOT_USABLE_IP_ADDRESS



api_host=os.environ.get("API_HOST") or "k8s-staticroute-operator-service"
api_port=os.environ.get("API_PORT") or "80"
api_url=f"http://{api_host}:{api_port}"
node_name=os.environ.get("NODE_NAME")
raw_token=os.environ.get("TOKEN")
if isinstance(raw_token, (bytes, bytearray)):
    token=str(raw_token,'utf-8').strip()
else:
    token=raw_token

def get_routes(api_url,token,node):
    error = False
    data=[]
    try:
        headers = {'content-type': 'application/json', 'Authorization': f'{token}' }
        json_data = {"selector_key":"nodePrefix","selector_value":node}
        response = requests.get(f'{api_url}/api/v1/route',headers=headers,json=json_data)
        json_response=response.json()
        if json_response:
            for item in json_response["result"]:
                if item["multipath"] is not None:
                    item["multipath"].sort()
                data.append(
                    {
                        "destination":item["destination"],
                        "gateway":item["gateway"],
                        "multipath":item["multipath"]
                    }
                )
        logging.info(f"Routes for node [{node}]: {data}")
    except Exception as e:
        logging.info(f'Failed calling API {e}')
        error = True
    final_result = sorted(data, key=lambda d: d['destination'])
    return final_result, error

def manage_static_route(operation, destination, gateway=None, multipath=None):
    operation_success = False
    is_multipath = False
    message = ""
    
    if isinstance(multipath, list):
        is_multipath = True

    if is_multipath:
        for route_gw in multipath:
            gw_ip = ""
            if isinstance(route_gw, dict):
                if ("gateway" in route_gw) and ("hops" in route_gw):
                    gw_ip = route_gw["gateway"]
                else:
                    message = f"Invalid IP address/hops specified for route - dest: {destination}!"
                    if logging is not None:
                            logging.error(message)
                    return (False, message)
            else:
                gw_ip = route_gw

            # Check if destination/gateway IP address/CIDR is valid for each path
            if not valid_ip_address(destination) or not valid_ip_address(gw_ip):
                message = f"Invalid IP address specified for route - dest: {destination}, gateway: {gw_ip}!"
                if logging is not None:
                        logging.error(message)
                return (False, message)
    else:

    	# Check if destination/gateway IP address/CIDR is valid first
    	if not valid_ip_address(destination) or not valid_ip_address(gateway):
            message = f"Invalid IP address specified for route - dest: {destination}, gateway: {gateway}!"
            if logging is not None:
                logging.error(message)
            return (False, message)

    # We don't want to mess with default GW settings, or with the '0.0.0.0' IP address
    if destination == DEFAULT_GW_CIDR or destination == NOT_USABLE_IP_ADDRESS:
        message = f"Route {operation} request denied - dest: {destination}!"
        if logging is not None:
                logging.error(message)
        return (False, message)

    with IPRoute() as ipr:
        try:
            if is_multipath:
                multipath_arr = []
                for gw in multipath:
                    if isinstance(gw, dict):
                        multipath_arr.append({"gateway":gw["gateway"],"hops":gw["hops"]})
                    else:
                        multipath_arr.append({"gateway":gw})
                ipr.route(operation, dst=destination, multipath=multipath_arr, table=60)    
            else:
                ipr.route(operation, dst=destination, gateway=gateway, table=60)
            operation_success = True
            message = f"Success - Dest: {destination}, gateway: {gateway}, multipath: {multipath}, operation: {operation}."
            if logging is not None:
                logging.info(message)
        except Exception as ex:
            operation_success = False
            message = f"Route {operation} failed! Error message: {ex}"
            if logging is not None:
                logging.error(message)

    return (operation_success, message)

def get_routing_status():
    with IPRoute() as ipr:
        try:
            result_routes = []
            routes = ipr.get_routes(family=AF_INET,table=60)
            for route in routes:
                #print(route)
                multipath = None
                if route.get_attr('RTA_MULTIPATH'):
                    multipath = []
                    for path in route.get_attr('RTA_MULTIPATH'):
                        multipath.append(path.get_attr('RTA_GATEWAY'))
                if multipath is not None:
                    multipath.sort()
                append = True
                if "dst_len" in route:
                    if route["dst_len"] == 32:
                        dst = route.get_attr('RTA_DST')
                    else:
                        dst = f"{route.get_attr('RTA_DST')}/{route['dst_len']}"
                gateway = route.get_attr('RTA_GATEWAY')
                if dst is None:
                    append = False
                if (multipath is None) and (gateway is None):
                    append = False
                if append:
                    result_routes.append({"destination":dst, "gateway": gateway, "multipath": multipath})
            if len(result_routes) > 1:
                final_result = sorted(result_routes, key=lambda d: d['destination'])
            else:
                final_result = result_routes
            return final_result               
        except Exception as ex:
            print(f"Error message: {ex}")

def list_remove(left,right):
    result_list=[]
    for item in left:
        if item not in right:
            result_list.append(item)
    return result_list
def keep_reachable(routes):
    for route in routes:
        if ("multipath" in route) and (route["multipath"] is not None):
            if len(route["multipath"]):
                for gw in route["multipath"]:
                    try:
                        delay=ping(gw)
                        logging.info(f"GW {gw} reachable with delay:{delay}")
                    except:
                        logging.info(f"GW {gw} NOT RECHABLE")                
    
def main():
    while True:
        desired, errors=get_routes(api_url=api_url,token=token,node=node_name)
        if not errors:
            current=get_routing_status()
            keep_reachable(current)
            logging.info(f"[{node_name}] - Current routes: {current}")
            routes_to_del = list_remove(left=current,right=desired)
            routes_to_add = list_remove(left=desired,right=current)
            logging.info(f"[{node_name}] - Routes to delete: {routes_to_del}")
            logging.info(f"[{node_name}] - Routes to add: {routes_to_add}")
            for route in routes_to_del:
                manage_static_route(operation="del",destination=route["destination"],gateway=route["gateway"],multipath=route["multipath"])
            for route in routes_to_add:
                manage_static_route(operation="add",destination=route["destination"],gateway=route["gateway"],multipath=route["multipath"])
        else:
            logging.info(f"[{node_name}] - Unable to reach the API, Keeping the last known state")
        time.sleep(30)

if __name__ == '__main__':
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - static-route-controller - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)
    main()