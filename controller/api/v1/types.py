from dataclasses import dataclass, field
from apischema import schema
from typing import NewType
from ..schema import OpenAPIV3Schema


# Static route API representation
# Final CRD is generated upon below dataclass via `make manifests` command
# WIP

@dataclass
class NodeSelector:
    key: str
    operation: str
    values: list[str]

@dataclass
class StaticRoute(OpenAPIV3Schema):
    __group__ = "networking.digitalocean.com"
    __version__ = "v1"
    __scope__ = "Cluster"
    __short_names__ = ["sr"]

    __additional_printer_columns__ = [
        {
            "name": "Age",
            "type": "date",
            "priority": 0,
            "jsonPath": ".metadata.creationTimestamp",
        },
        {
            "name": "Destinations",
            "type": "string",
            "priority": 1,
            "description": "Destination host(s)/subnet(s)",
            "jsonPath": ".spec.destinations",
        },
        {
            "name": "Gateway",
            "type": "string",
            "priority": 1,
            "description": "Gateway to route through",
            "jsonPath": ".spec.gateway",
        },
        {
            "name": "Multipath",
            "type": "string",
            "priority": 1,
            "description": "Gateways list for multipath routing",
            "jsonPath": ".spec.multipath",
        },
        {
            "name": "NodeSelector",
            "type": "string",
            "priority": 1,
            "description": "Sets the policy for apply this route set",
            "jsonPath": ".spec.nodeSelector",
        },
    ]

    Destination = NewType("Destination", str)
    schema(
        pattern="^([0-9]{1,3}\.){3}[0-9]{1,3}$|^([0-9]{1,3}\.){3}[0-9]{1,3}(\/([0-9]|[1-2][0-9]|3[0-2]))?$",
    )(Destination)

    destinations: list[Destination] = field(
        metadata=schema(
            description="Destination host(s)/subnet(s) to route through the gateway (required)",
        )
    )
    gateway: str = field(
        metadata=schema(
            description="Gateway to route through",
            pattern="^([0-9]{1,3}\.){3}[0-9]{1,3}$"
        )
    )

    IpAddress = NewType("IpAddress", str)
    schema(
        pattern="^([0-9]{1,3}\.){3}[0-9]{1,3}$",
    )(IpAddress)

    multipath: list[IpAddress] = field(
        
    )

    nodeSelector: NodeSelector = field(metadata=schema(
            description="Sets the policy for apply this route set"
    ))


