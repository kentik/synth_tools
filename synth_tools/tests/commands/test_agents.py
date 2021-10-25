import json
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from kentik_synth_client.synth_client import SynthHTTPTransport
from synth_tools.cli import app


def fake_req(fixture_file):
    d = Path(__file__).parent / fixture_file
    with open(d) as stream:
        return json.load(stream)


@pytest.mark.parametrize(
    "cmd, status_code, expected_in_output, not_expected_in_output",
    [
        (["agent", "list"], 0, ["AGENT_STATUS_OK", "country:"], []),
        (["agent", "list", "--brief"], 0, [], ["AGENT_STATUS_OK", "country:"]),
    ],
)
@mock.patch.object(SynthHTTPTransport, "req")
def test_get_agent(mocked_req, cmd, status_code, expected_in_output, not_expected_in_output):
    mocked_req.side_effect = [
        fake_req("../fixtures/agents/get_agents.json"),
        fake_req("../fixtures/agents/get_agent.json"),
    ]
    result = CliRunner().invoke(app, cmd)
    assert result.exit_code == status_code

    for expected in expected_in_output:
        assert expected in result.output
    for expected in not_expected_in_output:
        assert expected not in result.output
