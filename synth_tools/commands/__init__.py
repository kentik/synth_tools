from synth_tools.commands.agents import agents_app
from synth_tools.commands.tests import tests_app

commands_registry = {"test": tests_app, "agent": agents_app}
