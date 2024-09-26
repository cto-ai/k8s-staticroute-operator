import kopf
import time
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


def manage_static_route(operation, destination, gateway=None, multipath=None,logger=None):
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

    with IPRoute() as ipr:
        try:
            if is_multipath:
                multipath_arr = []
                for gw in multipath:
                    if isinstance(gw, dict):
                        multipath_arr.append({"gateway":gw["gateway"],"hops":gw["hops"]})
                    else:
                        multipath_arr.append({"gateway":gw})
                ipr.route(operation, dst=destination, multipath=multipath_arr)    
            else:
                ipr.route(operation, dst=destination, gateway=gateway)
            operation_success = True
            message = f"Success - Dest: {destination}, gateway: {gateway}, multipath: {multipath}, operation: {operation}."
            if logger is not None:
                logger.info(message)
        except Exception as ex:
            operation_success = False
            message = f"Route {operation} failed! Error message: {ex}"
            if logger is not None:
                logger.error(message)

    return (operation_success, message)


def process_static_routes(routes, operation, event_ctx=None, logger=None):
    status = []

    for route in routes:
        operation_succeeded, message = manage_static_route(
            operation=operation,
            destination=route["destination"],
            gateway=route["gateway"],
            multipath=route["multipath"],
            logger=logger,
        )

        if not operation_succeeded:
            status.append(
                {
                    "destination": route["destination"],
                    "gateway": route["gateway"],
                    "multipath": route["multipath"],
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
                "destination": route["destination"],
                "gateway": route["gateway"],
                "multipath": route["multipath"],
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
def create_fn(body, spec, logger, **_):
    destinations = spec.get("destinations", [])
    multipath = spec.get("multipath", None)
    gateway = spec.get("gateway", None)
    routes_to_add_spec = [
        {"destination": destination, "gateway": gateway, "multipath": multipath} for destination in destinations
    ]

    return process_static_routes(
        routes=routes_to_add_spec, operation="add", event_ctx=body, logger=logger
    )


# ============================== Update Handler =====================================
#
# Default behavior is to update/replace the static route(s) specified in our CRD
#
# ===================================================================================


@kopf.on.update(StaticRoute.__group__, StaticRoute.__version__, StaticRoute.__name__)
def update_fn(body, old, new, logger, **_):
    old_gateway = old["spec"].get("gateway", None)
    new_gateway = new["spec"].get("gateway", None)
    old_multipath = old["spec"].get("multipath", None)
    new_multipath = new["spec"].get("multipath", None)
    old_destinations = old["spec"].get("destinations", [])
    new_destinations = new["spec"].get("destinations", [])
    destinations_to_delete = list(set(old_destinations) - set(new_destinations))
    destinations_to_add = list(set(new_destinations) - set(old_destinations))

    routes_to_delete_spec = [
        {"destination": destination, "gateway": old_gateway, "multipath": old_multipath}
        for destination in destinations_to_delete
    ]

    process_static_routes(
        routes=routes_to_delete_spec, operation="del", event_ctx=body, logger=logger
    )

    routes_to_add_spec = [
        {"destination": destination, "gateway": new_gateway, "multipath": new_multipath}
        for destination in destinations_to_add
    ]

    return process_static_routes(
        routes=routes_to_add_spec, operation="add", event_ctx=body, logger=logger
    )


# ============================== Delete Handler =====================================
#
# Default behavior is to delete the static route(s) specified in our CRD only!
#
# ===================================================================================


@kopf.on.delete(StaticRoute.__group__, StaticRoute.__version__, StaticRoute.__name__)
def delete(body, spec, logger, **_):
    destinations = spec.get("destinations", [])
    gateway = spec.get("gateway", None)
    multipath= spec.get("multipath", None)
    routes_to_delete_spec = [
        {"destination": destination, "gateway": gateway, "multipath": multipath} for destination in destinations
    ]

    return process_static_routes(
        routes=routes_to_delete_spec, operation="del", event_ctx=body, logger=logger
    )
