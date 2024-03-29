import distutils.log
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

# noinspection Mypy
from setuptools import Command, setup

# The directory containing this file
HERE = Path(__file__).parent

# The text of the README file
README = (HERE / "README.md").read_text()

PACKAGES = ["kentik_synth_client", "kentik_synth_client.synth_tests", "synth_tools", "synth_tools.commands"]


def run_cmd(cmd, reporter) -> bool:
    """Run arbitrary command as subprocess"""
    reporter("run_cmd: {}".format(str(cmd)), level=distutils.log.DEBUG)
    try:
        subprocess.check_call(cmd)
        return True
    except subprocess.CalledProcessError as ex:
        reporter(str(ex), level=distutils.log.ERROR)
        return False


def rm_all(directory, remove_dir=False):
    """Remove all content in a directory"""
    for p in directory.iterdir():
        if p.is_dir():
            rm_all(p, remove_dir=True)
        else:
            p.unlink()
    if remove_dir:
        directory.rmdir()


# noinspection PyAttributeOutsideInit
class MypyCmd(Command):
    """Custom command to run Mypy"""

    description = "run Mypy on all relevant code"
    user_options = [("dirs=", None, "Directories to check with mypy"), ("types", None, "Install missing type stubs")]

    def initialize_options(self) -> None:
        self.dirs = [HERE.as_posix()]
        self.types = False

    def finalize_options(self):
        """Post-process options."""
        for d in self.dirs:
            assert os.path.exists(d), "Path {} does not exist.".format(d)

    def run(self):
        """Run command"""
        cmd = ["mypy"]
        if self.types:
            cmd.append("--install-types")
        for d in self.dirs:
            cmd.append(d)
        if not run_cmd(cmd, self.announce):
            exit(1)


# noinspection PyAttributeOutsideInit
class Format(Command):
    """Custom command to run black + isort"""

    description = "run black and isort on all relevant code; read configuration from pyproject.toml"
    user_options = [("dirs=", None, "Directories to check"), ("check", None, "Run in check mode")]

    def initialize_options(self) -> None:
        self.dirs = ["."]
        self.check = False

    def finalize_options(self):
        """Post-process options."""
        for d in self.dirs:
            assert os.path.exists(d), "Path {} does not exist.".format(d)

    def run(self):
        """Run command"""
        results = list()
        results.append(self._black())
        results.append(self._isort())
        if not all(results):
            exit(1)

    def _black(self) -> bool:
        cmd = ["black"]
        if self.check:
            cmd.append("--check")
            cmd.append("--diff")
        for d in self.dirs:
            cmd.append(d)
        self.announce("Executing: {}".format(" ".join(cmd)), level=distutils.log.INFO)
        return run_cmd(cmd, self.announce)

    def _isort(self) -> bool:
        cmd = ["isort"]
        if self.check:
            cmd.append("--check")
            cmd.append("--diff")
        for d in self.dirs:
            cmd.append(d)
        self.announce("Executing: {}".format(" ".join(cmd)), level=distutils.log.INFO)
        return run_cmd(cmd, self.announce)


# noinspection PyAttributeOutsideInit
class PyTest(Command):
    """Custom command to run pytest"""

    description = "run pytest on all test cases"
    user_options = [("dirs=", None, "Directories containing tests")]

    def initialize_options(self) -> None:
        self.dirs = ["synth_tools/tests"]

    def finalize_options(self):
        """Post-process options."""
        for d in self.dirs:
            assert os.path.exists(d), "Path {} does not exist.".format(d)

    def run(self):
        """Run command"""
        cmd = ["pytest"]
        for d in self.dirs:
            cmd.append(d)
        if not run_cmd(cmd, self.announce):
            exit(1)


setup(
    name="kentik-synth-tools",
    description="Tools supporting management of Kentik synthetic tests",
    maintainer="Martin Machacek",
    maintainer_email="martin.machacek@kentik.com",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/kentik/synth_tools",
    license="Apache-2.0",
    include_package_data=True,
    python_requires=">=3.7, <4",
    install_requires=["inflection", "kentik-api>=1.0.0", "pyyaml", "texttable", "typer", "validators"],
    tests_require=["pytest-runner", "pytest", "mypy"],
    cmdclass={
        "mypy": MypyCmd,
        "format": Format,
        "pytest": PyTest,
    },
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
    ],
    entry_points={
        "console_scripts": [
            "synth_ctl = synth_tools.cli:run",
        ],
    },
    packages=PACKAGES,
    package_dir={pkg: os.path.join(*pkg.split(".")) for pkg in PACKAGES},
)
