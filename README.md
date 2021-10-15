# Tools supporting management of Kentik synthetic tests

The synth_tools repo consists of 2 components:
- `kentik_synth_client` which is a package containing (temporary) SDK supporting interaction with Kentik synthetic API
- `synth_ctl.py` command-line tool for manipulation of synthetic tests

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
  | test | contains test attributes other than targets and agents | nested dictionary |
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

### Examples test

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
