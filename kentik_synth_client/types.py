from enum import Enum


class SerializableEnum(Enum):
    @classmethod
    def from_dict(cls, value: str):
        return cls(value)

    def to_dict(self):
        return self.value


class TestType(SerializableEnum):
    none = "<invalid>"
    agent = "agent"
    bgp_monitor = "bgp_monitor"
    dns = "dns"
    dns_grid = "dns_grid"
    flow = "flow"
    hostname = "hostname"
    ip = "ip"
    mesh = "application_mesh"
    network_grid = "network_grid"
    page_load = "page_load"
    url = "url"


class TestStatus(SerializableEnum):
    none = "<invalid>"
    active = "TEST_STATUS_ACTIVE"
    paused = "TEST_STATUS_PAUSED"
    deleted = "TEST_STATUS_DELETED"


class IPFamily(SerializableEnum):
    unspecified = "IP_FAMILY_UNSPECIFIED"
    dual = "IP_FAMILY_DUAL"
    v4 = "IP_FAMILY_V4"
    v6 = "IP_FAMILY_V6"


class Protocol(SerializableEnum):
    none = ""
    icmp = "icmp"
    udp = "udp"
    tcp = "tcp"


class FlowTestType(SerializableEnum):
    none = ""
    asn = "asn"
    cdn = "cdn"
    country = "country"
    region = "region"
    city = "city"


class DirectionType(SerializableEnum):
    dst = "dst"
    src = "src"
