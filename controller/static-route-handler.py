import kopf
import os, sys, time
import requests
import json
from pyroute2 import IPRoute
from api.v1.types import StaticRoute
from constants import DEFAULT_GW_CIDR
from constants import NOT_USABLE_IP_ADDRESS
from constants import ROUTE_EVT_MSG
from constants import ROUTE_READY_MSG
from constants import ROUTE_NOT_READY_MSG
from utils import valid_ip_address


# =================================== Static route management ===========================================
#
# Works the same way as the Linux `ip route` command:
#  - "add":     Adds a new entry in the Linux routing table (must not exist beforehand)
#  - "change":  Changes an entry from the the Linux routing table (must exist beforehand)
#  - "delete":  Deletes an entry from the Linux routing table (must exist beforehand)
#  - "replace": Replaces an entry from the Linux routing table if it exists, creates a new one otherwise
#
# =======================================================================================================


api_host=os.environ.get("API_HOST") or "k8s-staticroute-operator-service"
api_port=os.environ.get("API_PORT") or "80"
api_url=f"http://{api_host}:{api_port}"
raw_token=os.environ.get("TOKEN")
if isinstance(raw_token, (bytes, bytearray)):
    token=str(raw_token,'utf-8').strip()
else:
    token=raw_token

def apply_operation(data,operation,logger=None):
    is_success=False
    if operation == "add":
        try:
            headers = {'content-type': 'application/json', 'Authorization': f'{token}' }
            json_data = data
            response = requests.post(f'{api_url}/api/v1/route',headers=headers,json=json_data)
            json_response=response.json()
            if logger is not None:
                logger.info(f'service response: {json.dumps(json_response)}')
            is_success=True
        except Exception as e:
            if logger is not None:
                logger.error(f'Failed calling API {e}')
    if operation == "del":
        try:
            headers = {'content-type': 'application/json', 'Authorization': f'{token}' }
            json_data = data
            response = requests.delete(f'{api_url}/api/v1/route',headers=headers,json=json_data)
            json_response=response.json()
            if logger is not None:
                logger.info(f'service response: {json.dumps(json_response)}')
            is_success=True
        except Exception as e:
            if logger is not None:
                logger.error(f'Failed calling API {e}')
    return is_success

def manage_static_route(name, operation, destination, gateway=None, multipath=None,selector=None,logger=None):
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
                    if logger is not None:
                            logger.error(message)
                    return (False, message)
            else:
                gw_ip = route_gw

            # Check if destination/gateway IP address/CIDR is valid for each path
            if not valid_ip_address(destination) or not valid_ip_address(gw_ip):
                message = f"Invalid IP address specified for route - dest: {destination}, gateway: {gw_ip}!"
                if logger is not None:
                        logger.error(message)
                return (False, message)
    else:

    	# Check if destination/gateway IP address/CIDR is valid first
    	if not valid_ip_address(destination) or not valid_ip_address(gateway):
            message = f"Invalid IP address specified for route - dest: {destination}, gateway: {gateway}!"
            if logger is not None:
                logger.error(message)
            return (False, message)

    # We don't want to mess with default GW settings, or with the '0.0.0.0' IP address
    if destination == DEFAULT_GW_CIDR or destination == NOT_USABLE_IP_ADDRESS:
        message = f"Route {operation} request denied - dest: {destination}!"
        if logger is not None:
                logger.error(message)
        return (False, message)

    destination_val = destination.split("/")
    if len(destination_val) > 1:
        if destination_val[1] == "32":
            destination = destination_val[0]
    data = {}
    if is_multipath:
        data = {"rule_set":name,"destination":destination,"multipath":multipath}
    else:
        data = {"rule_set":name,"destination":destination,"gateway":gateway}

    if selector:
        data["selector"] = selector["operation"]
        data["selector_key"] = selector["key"]
        data["selector_value"] = selector["values"]
    apply_operation(operation=operation,data=data,logger=logger) 
    operation_success = True
    
        

    return (operation_success, message)


def process_static_routes(name, routes, operation,event_ctx=None, logger=None):
    status = []

    for route in routes:
        operation_succeeded, message = manage_static_route(
            name=name,
            operation=operation,
            destination=route["destination"],
            gateway=route["gateway"],
            multipath=route["multipath"],
            selector=route["selector"],
            logger=logger,
        )

        if not operation_succeeded:
            status.append(
                {
                    "name": name,
                    "destination": route["destination"],
                    "gateway": route["gateway"],
                    "multipath": route["multipath"],
                    "selector": route["selector"],
                    "status": ROUTE_NOT_READY_MSG,
                }
            )
            if event_ctx is not None:
                kopf.exception(
                    event_ctx,
                    reason=ROUTE_EVT_MSG[operation]["failure"],
                    message=message,
                )
            continue

        status.append(
            {
                "name": name,
                "destination": route["destination"],
                "gateway": route["gateway"],
                "multipath": route["multipath"],
                "selector": route["selector"],
                "status": ROUTE_READY_MSG,
            }
        )
        if event_ctx is not None:
            kopf.info(
                event_ctx, reason=ROUTE_EVT_MSG[operation]["success"], message=message
            )

    return status


# ============================== Create Handler =====================================
#
# Default behavior is to "add" the static route(s) specified in our CRD
# If the static route already exists, it will not be overwritten.
#
# ===================================================================================


@kopf.on.resume(StaticRoute.__group__, StaticRoute.__version__, StaticRoute.__name__)
@kopf.on.create(StaticRoute.__group__, StaticRoute.__version__, StaticRoute.__name__)
def create_fn(name, body, spec, logger, **_):
    destinations = spec.get("destinations", [])
    selector = spec.get("nodeSelector", None)
    multipath = spec.get("multipath", None)
    gateway = spec.get("gateway", None)
    routes_to_add_spec = [
        {"destination": destination, "gateway": gateway, "multipath": multipath, "selector":selector} for destination in destinations
    ]

    return process_static_routes(
        name=name,routes=routes_to_add_spec, operation="add", event_ctx=body, logger=logger
    )


# ============================== Update Handler =====================================
#
# Default behavior is to update/replace the static route(s) specified in our CRD
#
# ===================================================================================


@kopf.on.update(StaticRoute.__group__, StaticRoute.__version__, StaticRoute.__name__)
def update_fn(name, body, old, new, logger, **_):
    old_gateway = old["spec"].get("gateway", None)
    new_gateway = new["spec"].get("gateway", None)
    old_selector = old["spec"].get("nodeSelector", None)
    new_selector = new["spec"].get("nodeSelector", None)
    old_multipath = old["spec"].get("multipath", None)
    new_multipath = new["spec"].get("multipath", None)
    old_destinations = old["spec"].get("destinations", [])
    new_destinations = new["spec"].get("destinations", [])
    destinations_to_delete = list(set(old_destinations) - set(new_destinations))
    destinations_to_add = list(set(new_destinations) - set(old_destinations))

    routes_to_delete_spec = [
        {"destination": destination, "gateway": old_gateway, "multipath": old_multipath, "selector": old_selector}
        for destination in destinations_to_delete
    ]

    process_static_routes(
        name=name,routes=routes_to_delete_spec, operation="del", event_ctx=body, logger=logger
    )

    routes_to_add_spec = [
        {"destination": destination, "gateway": new_gateway, "multipath": new_multipath, "selector": new_selector}
        for destination in destinations_to_add
    ]

    return process_static_routes(
        name=name,routes=routes_to_add_spec, operation="add", event_ctx=body, logger=logger
    )


# ============================== Delete Handler =====================================
#
# Default behavior is to delete the static route(s) specified in our CRD only!
#
# ===================================================================================


@kopf.on.delete(StaticRoute.__group__, StaticRoute.__version__, StaticRoute.__name__)
def delete(name, body, spec, logger, **_):
    destinations = spec.get("destinations", [])
    gateway = spec.get("gateway", None)
    selector = spec.get("nodeSelector", None)
    multipath= spec.get("multipath", None)
    routes_to_delete_spec = [
        {"destination": destination, "gateway": gateway, "multipath": multipath, "selector":selector} for destination in destinations
    ]

    return process_static_routes(
        name=name,routes=routes_to_delete_spec, operation="del", event_ctx=body, logger=logger
    )
