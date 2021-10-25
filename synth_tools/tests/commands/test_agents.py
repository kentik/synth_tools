import json
from pathlib import Path
from unittest import mock

import pytest
from requests import Response
from typer.testing import CliRunner

from kentik_synth_client import KentikAPIRequestError
from kentik_synth_client.synth_client import SynthHTTPTransport
from synth_tools.cli import app


def fake_resp(status_code, content) -> Response:
    resp = Response()
    resp.status_code = status_code
    resp._content = content
    return resp


def fake_req(fixture_file):
    d = Path(__file__).parent / fixture_file
    with open(d) as stream:
        return json.load(stream)


@pytest.mark.parametrize(
    "cmd, status_code, expected_in_output, not_expected_in_output, requests",
    [
        # Expects to see all fields of an agent in a successful list request
        (["agent", "list"], 0, ["AGENT_STATUS_OK", "country:"], [], ["../fixtures/agents/get_agents.json"]),
        # Expects to NOT print status and country fields in a list request with --brief flag
        (["agent", "list", "--brief"], 0, [], ["AGENT_STATUS_OK", "country:"], ["../fixtures/agents/get_agents.json"]),
        # Expects to print the id output for a successful request to an existent agent
        (["agent", "get", "593"], 0, ["id: 593", ""], [], ["../fixtures/agents/get_agent.json"]),
        # Expects to not print anything when attempting to retrieve an nonexistent agent
        (["agent", "get", "999"], 0, [], ["id:"], ["../fixtures/empty_dict.json"]),
    ],
)
@mock.patch.object(SynthHTTPTransport, "req")
def test_agents(mocked_req, cmd, status_code, expected_in_output, not_expected_in_output, requests):
    mocked_req.side_effect = [fake_req(r) for r in requests]
    result = CliRunner().invoke(app, cmd)
    assert result.exit_code == status_code

    for expected in expected_in_output:
        assert expected in result.output
    for expected in not_expected_in_output:
        assert expected not in result.output


@pytest.mark.parametrize(
    "cmd, status_code, expected_in_output, not_expected_in_output, requests",
    [
        # Expects to print that the agent does not exists when attempting to retrieve an nonexistent agent
        (["agent", "get", "999"], 0, ["Agent 999 does not exists"], ["id:"], [fake_resp(404, b"")]),
        # Expects to print the raw request response in case of 5xx
        (["agent", "get", "123"], 0, ["Got unexpected response from API"], ["id:"], [fake_resp(500, b"some err")]),
    ],
)
@mock.patch.object(SynthHTTPTransport, "req")
def test_agents_exceptions(mocked_req, cmd, status_code, expected_in_output, not_expected_in_output, requests):
    mocked_req.side_effect = [KentikAPIRequestError(r) for r in requests]
    result = CliRunner().invoke(app, cmd)
    assert result.exit_code == status_code

    for expected in expected_in_output:
        assert expected in result.output
    for expected in not_expected_in_output:
        assert expected not in result.output
