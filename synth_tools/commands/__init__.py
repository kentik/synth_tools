import logging


logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


from synth_tools.commands.tests import tests_app
from synth_tools.commands.agents import agents_app

commands_registry = {
    'test': tests_app,
    'agent': agents_app
}
