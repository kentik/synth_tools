# Tools supporting management of Kentik synthetic tests

The synth_tools repo consists of 2 components:
- `kentik_synth_client` which is a package containing (temporary) Kentik synthetics SDK
- `synth_ctl` command-line tool for manipulation of synthetic tests and agents

`kentik_synth_client` is documented in separate [README](./kentik_synth_client/README.md).

## Requirements and Installation

The `synth_tools` package requires Python3 to execute. The lowest tested version is 3.7.3 and the newest 3.10.0.
The package is currently not published to PyPi, but it can be installed directly from Github.

_Note_: Installation directly from Github requires to have `git` installed and on `$PATH`.

```bash
pip3 install git+https://github.com/kentik/synth_tools.git#egg=kentik-synth-tools
```

It is highly recommended to use virtual environment, because the application has non-trivial dependencies.

```bash
mkdir kentik_synth_tools
cd kentik_synth_tools
python3 -m venv .venv
source .venv/bin/activate
pip3 install git+https://github.com/kentik/synth_tools.git#egg=kentik-synth-tools
```

The tool also requires authentication profile(s) for accessing the Kentik API.
Those are by default stored in `.kentik` directory in $HOME (see also _Authentication_ section)

Example of creation of Kentik authentication profile:
```bash
mkdir $HOME/.kentik
cat > $HOME/.kentik/default <<EOF
{
	"email": "<your_email>",
	"api-key": "<your_Kentik_API_key"
}
EOF
```

## Limitations / future development

The `synth_ctl` tool currently does not support:
- modification of synthetic agents
- creation of `bgp` and `transaction` type tests

## synth_ctl tool

The `synth_ctl` tool supports manipulation of Kentik synthetic tests and agents.

(see also `synth_ctl --help`)

### Operations supported for synthetic tests:
- listing and display of test configuration
- creation of tests based on configuration in `YAML` format
- in-place update of existing synthetic tests
- deletion
- pausing and resuming
- temporary execution of tests
- retrieval of test results, health status and traces

See also: `synth_ctl test --help`

### Operations supported for synthetic agents:
- listing and display of agent configuration
- matching of agents based on expression
- activation and deactivation

See also: `synth_ctl agent --help`


### Test configuration file

Each configuration file defines configuration for a single test.
The test configuration file uses `YAML` syntax and has 3 sections (dictionaries):

#### test section

This section specifies test attributes other than list of targets and agents.

_Common test attributes:_

  | name           | purpose                                                                       | required | possible values                                                         |
  | :--------------| :-----------------------------------------------------------------------------| :--------| :-----------------------------------------------------------------------|
  | type           | test type                                                                     | YES      | ip, hostname, network_grid, dns, dns_grid, url, page-load, network_mesh |
  | name           | name of the test                                                              | NO       | any printable string                                                    |
  | period         | test execution period                                                         | NO       | integer (default: 60 seconds)                                           |
  | family         | IP address family to use for tests selecting target address via DNS resolution| NO       | IP_FAMILY_DUAL (default), IP_FAMILY_V4, IP_FAMILY_V6                    |
  | health_settings| definition of thresholds for establishing test health                         | NO       | _see bellow_ (default: no thresholds)                                   |

_Health settings attributes_
```
    latency_ critical: 0
    latency_warning: 0
    latency_critical_stddev: 3
    latency_warning_stddev: 1
    packet_loss_critical: 50
    packet_loss_warning: 0
    jitter_critical: 0
    jitter_warning: 0
    jitter_critical_stddev: 3
    jitter_warning_stddev: 1
    http_latency_critical: 0
    http_latency_warning: 0
    http_latency_critical_stddev: 3
    http_latency_warning_stddev: 1
    http_valid_codes: []
    dns_valid_codes: []
```

_Test specific attributes:_
<br>`<Coming soon>`

#### targets section

The `targets` section allows specifying either direct list of targets (using the `use` sub-section),
or set of selection rules (using the `match` sub-section). Only one of `use` or `match` can be specified. 

At the moment only tests targeting IP addresses or agents support `match`. 
_Supported `targets` specification for individual test types_:
 
  | test type               | targets section format                                          |
  | :-----------------------| :---------------------------------------------------------------|
  | ip, network_grid        | `use: <list of addresses>` or `match: <address matching rules>` |
  | hostname, dns, dns_grid | `use: <list of DNS names>`                                      |
  | url, page_load          | `use: <list of URLs> `                                          |
  | agent                   | `use: <list of agent_ids>` or `match: <agent matching rules>`   |
  | network_mesh            | None (`targets` section is ignored)                             |                                             

**Address matching rules**

List of target addresses can be constructed by querying `device` and `interface` configuration in Kentik and selecting
addresses based on set of rules.

Format of the `match` section for address selection:

```
devices: # required
  <list of rules>
interface_addresses: # optional
  <address properties>
sending_ips: # optional
  <address properties>
snmp_ip: # optional
   <address properties> 
```

The selection algorithm retrieves list of devices from Kentik API and applies rules in the `devices` list. All rules
in the list must match in order for a device to be selected. See section _Device and agent matching rules_ for supported
rule syntax.

If the `interface_addresses` section is present, list of all interfaces is collected for each matched device. Candidate
addresses are extracted from values of the `ip_address` and `secondary_ips` interface attributes. 
If the `sending_ips` section is present, candidate addresses are extracted from the value of `sending_ips` attribute
of each matched device.
If the `snmp_ip` sections is present, value of the `snmp_ip` attribute of each matched devices is used.

At least one of `interface_addresses`, `sending_ips` or `snmp_ip` sections must be present. If more than one is present
extracted address lists are combined and de-duplicated. 

_Address properties_

  | name   | purpose                                                                      | required | possible values
  | :------| :--------------------------------------------------------------------------- | :--------| :-----------------------------------------------------|
  | family | IP address family to match                                                   | NO       | IP_FAMILY_DUAL (default), IP_FAMILY_V4, IP_FAMILY_V6  |
  | public | Exclude link-local and multicast and addresses in iana-ipv4-special-registry | NO       | True, False                                           |

#### agents section

This section specifies list of rules for selecting agents for the test. All rules in the list must match in order for an
agent to be selected. Rule syntax is described in the `Device and Agent matching rules` section bellow.

### Device and Agent matching rules

_Available matching rules :_

  | type                     | evaluation                                                    | format                                                                          | example                                                                              |
  | :------------------------| :-------------------------------------------------------------| :-------------------------------------------------------------------------------| :------------------------------------------------------------------------------------|
  | attribute match          | tests value of specified (device or agent) attribute          |`attribute`: `value` or `attribute`: `match_function(...)` (see bellow)          | device_type: router                                                                  |
  | match any (logical OR)   | matches if at least one rule in the list matches              |any: `list of rules`                                                             | any: <br>  - label: gateway<br>  - label: edge router                                |
  | match all (logical AND)  | matches if all rules in the list match                        |all: `list of rules`                                                             | all: <br>  - label: gateway<br>  - site.site_name: Ashburn DC3                       |
  | one_of_each              | produces set of candidate matches and matches 1 object to each|one_of_each:<br>`attribute1`: `list of values`<br>`attribute2`: `list of values` | one_of_each:<br>site.site_name: \[siteA, siteB\]<br>device_type: \[router, gateway\] |

Attribute value match (including match via a function) can be negated using `!` as the first character of the value.
Example: `type:!dns`. 

The `all` and `any` operators can be nested allowing to construct complex expressions. Example of matching `router`
type devices in `siteA` and `gateway` devices in `siteB`

```yaml
targets:
  match:
    devices:
      - any:
        - all:
          - site.site_name: site_a
          - device_type: router
        - all:
          - site.site_name: site_b
          - device_type: gateway
      ...
```

Example of selecting 1 agent in each specified ASN and country:
```yaml
agents:
  match:
    - one_of_each: { asn: [1234, 5678], country: [US, CZ] }
  ...
```
The above example will select at most 1 agent with `asn: 1234` and `country: US` (and other combinations of `asn` and `country` values)
even if multiple agents with matching `asn` and `country` attribute are available.
_Note_: list of agents generated by the `one_of_each` rule may differ across invocations, because it depends on the order
in which agents are returned by the API which is undefined.

#### Attribute match functions

In additions to direct comparison of value of object attributes, the tool provides following match functions:

| name       | evaluation                                                    | format                                | example                                                  |
|:-----------|:--------------------------------------------------------------|:--------------------------------------|:---------------------------------------------------------|
| regex      | evaluates regular expression on attribute value               | regex(`regular expression`)           | `device_name: regex(.\*-iad1-.\*)`                       |
| contains   | tests if a multi-valued attribute contains specified value    | contains(`value`)                     | `sending_ips: contains(1.2.3.4)`                         |
| one_of     | test if value of an attribute is in the list                  | one_of(`comma_separated_list`)        | `label: one_of(edge router, gateway, bastions)`          |
| newer_than | tests whether a timestamp value is newer than specified time  | newer_than(`timespec` or `timedelta`) | `last_authed: newer_than(-1h)`                           |
| older_than | tests whether a timestamp value is older than specified time  | older_than(`timespec` or `timedelta`) | `last_authed: older_than(2021-11-01 00:00:00.000-07:00)` |

Arguments to `newer_than` and `older_than` are one of:
- `timespec`: time string in ISO format or one of `today`, `yesterday`, `tomorrow` which are
expanded to UTC time based on system time of the machine on which `synth_ctl` executes.
- `timedelta`: format `<float><optional space><unit>`. Format of the `<unit>` (plural forms are accepted too):

| unit          | abbreviations        | examples                    |
|---------------|:---------------------|:----------------------------|
| `week`        | `w`                  | `1w` `-13.1 weeks`          |
| `day`         | `d`                  | `1d` `10 days`, `-2d`       |
| `hour`        | `h`                  | `1h` `-0.5 hours`           |
| `minute`      | `m` `min`            | `1minute` `-3.14mins`       |
| `second`      | `s` `sec`            | `-1 s` `0.01secs`           |
| `millisecond` | `ms` `msec` `millis` | `1ms` `-3msecs` `2 millis`  |
| `microsecond` | `us` `usec` `micros` | `1us` `-0.1usec` `2 micros` |
 
Negative values mean time in the past with respect to current time. All time specifications are expected to be in UTC.

#### Optional specification of minimum and maximum number of matching targets

Maximum and minimum number of matched targets of agents  can be specified using:
`max_matches: <MAX>` or `min_matches: <MIN>` directives in corresponding `targets` or `agents` section.
If less than `min_targets` matches test creation fails. If more than `max_matches` targets or agents match only
first `max_matches` objects are used. At least 1 agent is required for any test (except for `network_mesh`).
Randomization of selected targets or agents is possible using the `randomize: True` option. This option has effect only
if `max_matches` is specified and number of matching targets or agents is greater than `max_targets`.

Example:
```yaml
targets:
  min_matches: 2
  max_matches: 10
  match:
    devices:
      - name: regex(.*-fra1-.*)
      - device_type: router
    ...
```

### Example test configurations

- `network_grid` test with target selection based on matching interface addresses
and selection of test agents based on ASN and country code:

```yaml
test:
  type: network_grid
  period: 300

targets:
  match:
    devices:
      - site.site_name: Ashburn DC3
      - any:
          - label: edge router
          - label: gateway
          - label: bastions
    interface_addresses:
      family: ipv4
      public_only: True
    
agents:
  match:
    - family: IP_FAMILY_DUAL
    - one_of_each: { asn: [15169, 7224, 16509, 36351], country: [US, AU, BR] }
```
- `dns_grid` test with direct specification of targets and selection of agents based on regular expression match on name
```yaml
test:
  name: dns AAAA
  type: dns_grid
  period: 600
  servers: [1.1.1.1, 8.8.8.8]
  record_type: DNS_RECORD_AAAA
  health_settings:
    dns_valid_codes: [0]

targets:
  use:
    - www.example.com
    - www.kentik.com

agents:
  match:
    - name: regex(.*-west-.*)
```

More examples are in the `data` directory in the repo.

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
Proxy URL can be also specified in the authentication profile. Example:
```json
{
  "email": "<email address>",
  "api-key": "<the API key>",
  "proxy": "socks5://localhost:60000"
}
```
### Accessing API in specific environment (other than Kentik US)

The `--api-url` option allows specifying URL to use for access to Kentik management and synthetics APIs.
Only "base" URL is required (example: https://api.kentik.eu) for both. API URL  can be also specified in the
authentication profile.

Example:

```json
{
  "email": "<email address>",
  "api-key": "<the API key>",
  "url": "https://api.kentik.eu"
}
```

### Agent and test match command syntax

`synth_ctl test match` and `synth_ctl agent match` commands allow listing of tests or agents matching specific criteria.
Match criteria are specified as a space separated list of rules. All rules must match in order for a test or agent to be listed.
Format of rules: `attribute:value` or `attribute:match_function(args)`.
Supported match functions are described in _Attribute match functions_ section above. Available attribute names are as returned by 
`synth_ctl test list` or `synth_ctl agent list` commands. Attributes in nested blocks can be specified using dot-syntax.

Examples:

```
❯ synth_ctl test match type:hostname "settings.hostname.target:contains(kentik.com)"
id: 5229
  name: Monitor www.kentik.com
  type: hostname
  status: TEST_STATUS_ACTIVE
  settings:
    [...]
    hostname:
      target: www.kentik.com

id: 5228
  name: Monitor api.kentik.com
  type: hostname
  status: TEST_STATUS_ACTIVE
  settings:
    [...]
    hostname:
      target: api.kentik.com

❯ synth_ctl test match "settings.agentIds:contains(813)"
id: 5372
  name: big one
  type: network_mesh
  status: TEST_STATUS_ACTIVE
  settings:
    agent_ids: ['848', '598', '608', '849', '733', '2642', '2644', '828', '813', '803', '2122', '644', '1022', '662', '573', '612', '611', '615', '568', '616']
    [...]

❯ synth_ctl agent match country:JP version:0.0.17 "name:regex(asia-.*)"
id: 638
  name: asia-northeast1
  status: AGENT_STATUS_OK
  alias: Tokyo, Japan
  type: global
  os:
  ip: 34.84.156.137
  lat: 35.689506
  long: 139.6917
  family: IP_FAMILY_V4
  asn: 15169
  site_id: 0
  version: 0.0.17
  challenge:
  city: Tokyo
  region: Tokyo
  country: JP
  test_ids: []
  local_ip:
  cloud_vpc:
  agent_impl: IMPLEMENT_TYPE_RUST
  last_authed: 2021-10-28T22:05:47.115Z

❯ synth_ctl agent match asn:61098 country:DE --brief
id: 2541 name: EXOSCALE,CH (61098) alias: Frankfurt, Germany type: global
id: 570 name: EXOSCALE,CH (61098) alias: Frankfurt, Germany type: global
id: 580 name: EXOSCALE,CH (61098) alias: Munich, Germany type: global
```

### Specifying attributes/fields to include in test or agent configuration listing

The `--fields` (or `-f`) option allows specifying agent or test configuration attributes/fields to display in a listing.
Fields are specified as a comma-separated list, with dot-syntax for nested attributes. If the only requested attribute
is `id`, output contains only ids of matching agents without the `id:` prefix (one per line) 

Examples:
```
❯ synth_ctl test get 666 -f name,settings.health_settings.http_valid_codes
name: webserver_test
settings:
  health_settings:
    http_valid_codes: [200, 301]
    
❯ synth_ctl agent get 811 -f alias,version,os
id: 811
  alias: Dubai, United Arab Emirates
  os:
  version: 0.0.15

❯ synth_ctl agent match type:private -f id
7108
3462
3553
```

The `--brief` (or `-b`) option enables output of minimal set of attributes, one line per object.
See `synth_ctl test list --help` or `synth_ctl agent list --help` for details.

### Running a test in one-shot mode

The `synth_ctl test one-shot <config_file>` command allows to:
- create a test,
- wait for it to produce health results
- print results
- delete (or disable) the test

Example:

```
❯ synth_ctl test one-shot configs/ip_test_agent.yaml
INFO:core:Loading test configuration from 'configs/ip_test_agent.yaml'
INFO:core:Created test '__auto__ip_test_agent_2021-10-28T22:11:00+00:00' (id: 6654)
INFO:core:Waiting for 58.845728 seconds for test to accumulate results
INFO:core:Waiting for 60 seconds for test to accumulate results
INFO:core:Waiting for 60 seconds for test to accumulate results
INFO:core:Deleted test __auto__ip_test_agent_2021-10-28T22:11:00+00:00' (id: 6654)
target: 1.1.1.1
  time: 2021-10-28T22:14:00Z, agent_id: 3462, agent_addr: 150.230.39.242, task_type: ping, loss: 0% (healthy), latency: 1.017ms (healthy), jitter: 0.099ms (healthy), data: [], status: 0, size: 0
  time: 2021-10-28T22:14:00Z, agent_id: 3449, agent_addr: 66.172.98.201, task_type: ping, loss: 0% (healthy), latency: 12.455ms (healthy), jitter: 0.529ms (healthy), data: [], status: 0, size: 0
```

## synth_ctl usage
Top-level

```
❯ synth_ctl --help
Usage: synth_ctl [OPTIONS] COMMAND [ARGS]...

  Tool for manipulating Kentik synthetic tests

Options:
  -p, --profile TEXT         Credential profile for the monitoring account
                             [default: default]
  -t, --target-profile TEXT  Credential profile for the target account
                             (default: same as profile)
  -d, --debug                Debug output
  --proxy TEXT               Proxy to use to connect to Kentik API
  --api-url TEXT             Base URL for Kentik API (default:
                             api.kentik.com)
  --version                  Show version and exit
  --help                     Show this message and exit.

Commands:
  agent
  test
```

`test` command group
```
❯ synth_ctl test --help
Usage: synth_ctl test [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  compare   Compare configurations of 2 existing tests
  create    Create test
  delete    Delete test
  get       Print test configuration
  import    Compare configurations of 2 existing tests
  list      List all tests
  match     Print configuration of test matching specified rules
  one-shot  Create test, wait until it produces results and delete or...
  pause     Pause test execution
  results   Print test results and health status
  resume    Resume test execution
  trace     Print test trace data
  update    Update existing test
```

`agent` command group
```
❯ synth_ctl agent --help
Usage: synth_ctl agent [OPTIONS] COMMAND [ARGS]...

Options:
  --help  Show this message and exit.

Commands:
  activate    Activate pending agent
  deactivate  Deactivate an active agent
  delete      Delete an agent
  get         Print agent configuration
  list        List all agents
  match       Print configuration of agents matching specified rules
```

Help is also available for individual commands. Example:

```
❯ synth_ctl test one-shot --help
Usage: synth_ctl test one-shot [OPTIONS] TEST_CONFIG

  Create test, wait until it produces results and delete or disable it

Arguments:
  TEST_CONFIG  Path to test config file  [required]

Options:
  --retries INTEGER               Number retries waiting for test results
                                  [default: 3]
  --summary / --no-summary        Print summary rest results  [default: no-
                                  summary]
  --delete / --no-delete          Delete test after retrieving results
                                  [default: delete]
  --print-config / --no-print-config
                                  Print test configuration  [default: no-
                                  print-config]
  --json-out TEXT                 Path to store test results in JSON format
  -s, --substitute TEXT           Comma separated list of substitutions in the
                                  form of 'var:value'
  --help                          Show this message and exit.
```


