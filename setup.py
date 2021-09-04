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


def run_cmd(cmd, reporter) -> None:
    """Run arbitrary command as subprocess"""
    reporter("Run command: {}".format(str(cmd)), level=distutils.log.DEBUG)
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as ex:
        reporter(str(ex), level=distutils.log.ERROR)


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
class FetchGRPCCode(Command):
    """Command copying generate Python gRPC code from source repo."""

    description = "Import .proto files from source repo and build Python stubs"
    user_options = [
        ("repo=", None, "Source repository"),
        ("python-path=", None, "Path to generated Python code within the source repo"),
    ]

    def initialize_options(self):
        self.repo = "https://github.com/kentik/api-schema-public.git"
        self.python_path = "gen/python"

    def finalize_options(self):
        pass

    # noinspection Mypy
    def run(self):
        import git

        # create work directory, if it does not exist
        dst = HERE.joinpath("generated")
        dst.mkdir(parents=True, exist_ok=True)
        # cleanup the work directory
        rm_all(dst)
        # checkout source repo and copy proto files to work directory
        with TemporaryDirectory() as tmp:
            git.Repo.clone_from(self.repo, tmp)
            Path(tmp).joinpath(self.python_path).rename(dst)


# noinspection PyAttributeOutsideInit
class MypyCmd(Command):
    """Custom command to run Mypy"""

    description = "run Mypy on all relevant code"
    user_options = [("dirs=", None, "Directories to check with mypy")]

    def initialize_options(self) -> None:
        self.dirs = ["synth_tools"]

    def finalize_options(self):
        """Post-process options."""
        for d in self.dirs:
            assert os.path.exists(d), "Path {} does not exist.".format(d)

    def run(self):
        """Run command"""
        cmd = ["mypy"]
        for d in self.dirs:
            cmd.append(d)
        run_cmd(cmd, self.announce)


setup(
    name="kentik-synth-tools",
    use_scm_version={
        "root": ".",
        "relative_to": __file__,
    },
    description="Tools supporting management of Kentik synthetic tests",
    maintainer="Martin Machacek",
    maintainer_email="martin.machacek@kentik.com",
    long_description=README,
    long_description_content_type="text/markdown",
    url="https://github.com/kentik/synth_tools",
    license="Apache-2.0",
    include_package_data=True,
    install_requires=["kentik-api>=0.3.0"],
    setup_requires=["pytest-runner", "setuptools_scm", "wheel", "grpcio-tools", "gitpython"],
    tests_require=["httpretty", "pytest", "mypy"],
    cmdclass={"mypy": MypyCmd, "grpc": FetchGRPCCode},
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
    ],
    scripts=["synth_tools/synth_ctl.py"],
)
