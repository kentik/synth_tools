# Tools supporting management of Kentik synthetic tests

The synth_tools repo consists of 2 components:
- `kentik_synth_client` which is a package containing (temporary) SDK supporting interaction with Kentik synthetic API
- `synth_ctl.py` command-line tool for manipulation of synthetic tests and agents

`kentik_synth_client` is documented in separate [README](./kentik_synth_client/README.md).

## synth_ctl

The `synth_ctl.py` tool supports manipulation of Kentik synthetic tests and agents.

(see also `synth_ctl.py --help`)

### Operations supported for synthetic tests:
- listing and display of test configuration
- creation of tests based on configuration in `YAML` format
- deletion
- pausing and resuming
- temporary execution of tests
- retrieval of test results and health status

See also: `synth_ctl --profile <your_profile> test --help`

_Note: The authentication profile (`--profile` option) unfortunately must be specified when requesting command group specific usage information.
This is a limitation of the framework used for implementation of the tool._

### Operations supported for synthetic agents:
- listing and display of agent configuration
- matching of agents based on criteria

See also: `synth_ctl --profile <your_profile> agent --help`

### Test configuration file

Each test configuration file defines configuration for 1 test. The test configuration file use `YAML` syntax.
The configuration file has 3 sections:

  | name | purpose | format |
  | :---------| :------| :----- |
  | test | contains test attributes other than targets and agents | dictionary |
  | agents | Criteria for matching agents to use for the test | list of dictionaries |
  | targets | Criteria for matching targets or direct list of targets | dictionary or list |

#### test section

_Common test attributes:_

  | name | purpose | required | possible values |
  | :---------| :------| :----- | :------|
  | type | test type | YES | ip, hostname, network_grid, dns, dns_grid, url, page-load, mesh |
  | name | name of the test | NO | any printable string |
  | period | test execution period | NO | integer (default: 60 seconds) |
  | family | IP address family to use for tests selecting target address via DNS resolution | NO | IP_FAMILY_DUAL (default), IP_FAMILY_V4, IP_FAMILY_V6 |
  | healthSettings | definition of thresholds for establishing test health | NO| dictionary (default: no thresholds) |

_Test specific attributes:_
<TDB>

#### targets section

The `targets` section allows to specify either direct list of targets, or criteria for selecting targets. Content differs by test type.
Following table shows content of targets section for individual tests
 
  | test type        | targets section format |
  | :----------------| :----------------------|
  | ip, network_grid | list of IP addresses or address selection criteria (see bellow) |
  | hostname, dns, dns_grid | list of valid DNS host/domain names |
  | url, page_load   | list of URLs |
  | agent            | list of agent ids or agent selection criteria (see bellow) |

**Address selection criteria**

The tool allows construct list of addresses by querying `device` and `interface` configuration in Kentik and selecting
addresses based on specified criteria.

Format of the `targets` section for address matching:

```
devices: # required
  <list of matching criteria>
interface_addresses: # optional
  <address properties>
sending_ips: # optional
  <address properties>
snmp_ip: # optional
   <address properties> 
```

The selection algorithm first retrieves list of devices from Kentik API and applies criteria in the `devices` list. All criteria
in the list must match in order for a device to be selected.

_Available matching criteria:_

  | type                     | evaluation                                                    | format                                                                           | example                                                                              |
  | :------------------------| :-------------------------------------------------------------| :--------------------------------------------------------------------------------| :------------------------------------------------------------------------------------|
  | direct attribute match   | tests value of specified attribute                            |  `attribute`: `value`                                                            | device_type: router                                                                  |
  | regular expression match | matches value of specified attribute using regular expression |`attribute`: regex(`regular expression`)                                          | device_name: regex(.\*-iad1-.\*)                                                     |
  | match any (OR operator)  | matches if at least one criterium in the list matches         | match_any: `list of criteria`                                                    | match_any: <br>  - label: gateway<br>  - label: edge router                          |
  | match all (AND operator) | matches if all criteria in the list match                     | match_all: `list of criteria`                                                    | match_all: <br>  - label: gateway<br>  - site.site_name: Ashburn DC3                 |
  | one_of_each              | produces set of candidate matches and matches 1 object to each| one_of_each:<br>`attribute1`: `list of values`<br>`attribute2`: `list of values` | one_of_each:<br>site.site_name: \[siteA, siteB\]<br>device_type: \[router, gateway\] |

The `match_all` and `match_any` operators can be nested allowing to construct complex expressions. Example of matching of `router`
type devices in `siteA` and `gateway` devices in `siteB`

```yaml
devices:
  - match_any:
    - match_all:
      - site.site_name: siteA
      - device_type: router
    - match_all
      - site.site_name: siteB
      - device_type: gateway
```
Note: the top list in the `devices` section is actually consumed by an implied `match_all` operator.

(see `agents` section for example usage of the `one_of_each` operator)

If the `interface_addresses` section is present, list of all interfaces is collected for each matched device. Candidate
addresses are extracted from values of the `ip_address` and `secondary_ips` interface attributes. 
If the `sending_ips` section is present, candidate addresses are extracted from the value of `sending_ips` attribute
of each matched device.
If the `snmp_ip` sections is present, value of the `snmp_ip` attribute of each matched devices is used.

At least one of `interface_addresses`, `sending_ips` or `snmp_ip` sections must be present. If more than one is present
extracted address lists are combined and de-duplicated. Available matching criteria are as shown in the _Available matching criteria_
in the `targets` section above.

#### agents section

This section allows to specify selection criteria for agents to used to run the test. The content is list of criteria
for matching agents configuration. Selection criteria are as shown in the _Available matching criteria:_ table in the `targets` section.

Example of specifying list of agents by `id`:

```yaml
agents:
  - match_any:
    - id: ID1
    - id: ID2
```
 
Example of selecting 1 agent in each specified ASN and country:
```yaml
agents:
  - one_of_each:
    asn: [1234, 5678]
    country: [US, CZ]
```
The above example will select at most 1 agent with `asn: 1234` and `country: US` (and other combinations of `asn` and `country` values) even if multiple agents match the criteria.

### Example test configurations

- `network_grid` test with target selection based on matching interface addresses
and selection of test agents based on ASN and country code:

```yaml
test:
  type: network_grid
  period: 300

targets:
  devices:
    - site.site_name: Ashburn DC3
    - match_any:
        - label: edge router
        - label: gateway
        - label: bastions
  interface_addresses:
    family: ipv4
    public_only: True
    
agents:
  - family: IP_FAMILY_DUAL
  - one_of_each:
     asn: [15169, 7224, 16509, 36351]
     country: [US, AU, BR]
```
- `dns_grid` test with direct specification of targets and selection of agents based on regular expression match on name
```yaml
test:
  name: dns AAAA
  type: dns_grid
  period: 600
  servers: [1.1.1.1, 8.8.8.8]
  record_type: DNS_RECORD_AAAA
  healthSettings:
    dnsValidCodes: [0]

targets:
  - www.photographymama.com
  - pupik.m3a.net

agents:
  - name: regex(.*-west-.*)
```

More examples are in the `tests` directory in the repo.

### Authentication
The `synth_ctl` tool relies on `authentication profiles`. Authentication profile is a JSON file with the following format:
```json
{
  "email": "<email address>",
  "api-key": "<the API key>"
}
```
Profile files are first searched in `${KTAPI_HOME}/<profile_name>` and if not found then in `${HOME}/.kentik/<profile_name>`.

Up to 2 profiles can be specified:
`--profile` identity associated with this profile is used for authentication with the Kentik synthetics API
`--target-profile` identity associated with this profile is used for authentication to Kentik management API, which is used for selection of monitoring targets

If no `--target-profile` is specified, profile specified via `--profile` is used.

### Proxy access

The `--proxy` option allows to specify proxy to use for accessing Kentik APIs. The syntax of the `--proxy` values is
as specified in the [Proxies](https://2.python-requests.org/en/master/user/advanced/#id10) definition for the Python `requests` modules

## Limitations / future development

The `synth_ctl.py` tool current does not support:
- creation of `flow` type tests
- creation of `bgp` type tests
- retrieval of test traceroute results (traces)
