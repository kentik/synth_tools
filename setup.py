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

PACKAGES = ["kentik_synth_client", "synth_tools"]


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

    description = "Copy generated Python stubs from source repo"
    user_options = [
        ("repo=", None, "Source repository"),
        ("src-path=", None, "Path to generated Python code within the source repo"),
        ("dst-path=", None, "Destination path in the local source tree"),
    ]

    def initialize_options(self):
        self.repo = "https://github.com/kentik/api-schema-public.git"
        self.src_path = "gen/python"
        self.dst_path = HERE.joinpath("generated").as_posix()

    def finalize_options(self):
        pass

    # noinspection Mypy
    def run(self):
        import git

        # create destination directory, if it does not exist
        dst = Path(self.dst_path)
        dst.mkdir(parents=True, exist_ok=True)
        # cleanup destination directory
        rm_all(dst)
        # checkout source repo and copy stubs
        with TemporaryDirectory() as tmp:
            git.Repo.clone_from(self.repo, tmp)
            Path(tmp).joinpath(self.src_path).rename(dst)


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
        run_cmd(cmd, self.announce)


# noinspection PyAttributeOutsideInit
class Black(Command):
    """Custom command to run black"""

    description = "run black on all relevant code"
    user_options = [("dirs=", None, "Directories to check with black")]

    def initialize_options(self) -> None:
        self.dirs = ["."]

    def finalize_options(self):
        """Post-process options."""
        for d in self.dirs:
            assert os.path.exists(d), "Path {} does not exist.".format(d)

    def run(self):
        """Run command"""
        cmd = ["black"]
        for d in self.dirs:
            cmd.append(d)
        run_cmd(cmd, self.announce)


# noinspection PyAttributeOutsideInit
class Isort(Command):
    """Custom command to run isort"""

    description = "run isort on all relevant code"
    user_options = [("dirs=", None, "Directories to check with isort")]

    def initialize_options(self) -> None:
        self.dirs = ["."]

    def finalize_options(self):
        """Post-process options."""
        for d in self.dirs:
            assert os.path.exists(d), "Path {} does not exist.".format(d)

    def run(self):
        """Run command"""
        cmd = ["isort"]
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
    install_requires=["kentik-api>=0.3.0", "urllib3>=1.26.0", "pyyaml", "typer", "validators"],
    setup_requires=["pytest-runner", "setuptools_scm", "wheel", "grpcio-tools", "gitpython"],
    tests_require=["httpretty", "pytest", "mypy"],
    cmdclass={"mypy": MypyCmd, "grpc_stubs": FetchGRPCCode, "black": Black, "isort": Isort},
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
    ],
    scripts=["synth_ctl.py"],
    packages=PACKAGES,
    package_dir={pkg: os.path.join(*pkg.split(".")) for pkg in PACKAGES},
)
