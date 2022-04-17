# coding=utf-8
"""
Multi Language Project Classes
"""
__all__ = (
    "venv",
    "AnyPath",
    "cli_invoke",
    "FileConfig",
    "GIT_DEFAULT_SCHEME",
    "GITHUB_DOMAIN",
    "GITHUB_URL",
    "GitScheme",

    "EnvBuilder",
    "ProjectBase",
    "ProjectPy",
)

import tempfile
from dataclasses import InitVar
from os import PathLike
from typing import AnyStr
from typing import IO
from typing import Literal
from typing import Type
from urllib.parse import ParseResult

import click
import sys
import sysconfig
import venv
from collections import namedtuple
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from subprocess import check_call
from subprocess import getoutput
from types import SimpleNamespace
from typing import ClassVar
from typing import Optional
from typing import Union

import git
import setuptools.config
import toml
from furl import furl
from git import Git as GitCmd
from git import GitCmdObjectDB
from git import GitConfigParser
from gitdb import LooseObjectDB
from packaging.specifiers import SpecifierSet
from typer import Typer
from typer.testing import CliRunner

venv.CORE_VENV_DEPS = ("build", "darling", "icecream", "ipython", "pip", "pip-tools", "pytest", "pytest-asyncio",
                       "rich", "setuptools", "setuptools_scm", "tox", "wheel", )

AnyPath = Union[AnyStr, IO[AnyStr], PathLike, Path]
cli_invoke = CliRunner().invoke
FileConfig = namedtuple("FileConfig", ("file", "config"))
GIT_DEFAULT_SCHEME = "https"
GITHUB_DOMAIN = "github.com"
GITHUB_URL = {
    "api": f"https://api.{GITHUB_DOMAIN}/",
    "git+file": "git+file:///",
    "git+https": f"git+https://{GITHUB_DOMAIN}/",
    "git+ssh": f"git+ssh://git@{GITHUB_DOMAIN}/",
    "https": f"https://{GITHUB_DOMAIN}/",
    "ssh": f"git@{GITHUB_DOMAIN}:",
}
"""
GitHub: api, git+file, git+https, git+ssh, https, ssh and git URLs
(join directly the user or path without '/' or ':')
"""
GitScheme = Literal["git+file", "git+https", "git+ssh", "https", "ssh"]

__project__: str = Path(__file__).parent.name
app = Typer(add_completion=False, context_settings=dict(help_option_names=['-h', '--help']), name=__project__)


@dataclass
class OwnerRepo:
    """Git Owner Repo Parser Class"""
    owner: str = field(default="")
    repo: str = field(default="")

    def __post_init__(self):
        if not self.owner or not self.repo:
            raise ValueError(f"Invalid GitHub URL: {self.owner}/{self.repo}")

    @classmethod
    def from_url(cls, url: Union[furl, ParseResult, Path, str] = None) -> "OwnerRepo":
        """
        Parse a GitHub URL into owner and repo

        :param url: Url, or None to use remote url from git config (Default: None)

        :return: furl instance of GitHub URL
        """
        url = furl(url if isinstance(url, (str, furl)) else url.geturl() if isinstance(url, ParseResult) else Git(url).remote.url)
        if "@" in url:
            owner = url.username
        else:
            pass

        return cls(owner=owner, repo=repo)

    @classmethod
    def from_path(cls, path: Path) -> "OwnerRepo":
        """
        Parse a path into owner and repo
        """
        return cls(owner=path.parent.name, repo=path.name)

    def url(self, scheme: GitScheme = GIT_DEFAULT_SCHEME) -> furl:
        """
        Get Repository URL

        if scheme is "git+file" will only use repo argument as the path and must be absolute path

        furl:
            - url.query: after "?", i.e. ?ref=master&foo=bar
            - url.args: query args dict, i.e. {'ref': 'master', 'foo': 'bar'}
            - url.fragment: after "#", i.e. #two/directories?one=argument
            - url.fragment.path.segments: i.e. ['two', 'directories']
            - url.fragment.args: i.e. {'one': 'argument'}


        Examples:
            >>> OwnerRepo().url() # doctest: +ELLIPSIS
            'https://github.com/.../....git'
            >>> OwnerRepo(repo="test").url() # doctest: +ELLIPSIS
            'https://github.com/.../test.git'
            >>> OwnerRepo("cpython", "cpython").url()
            'https://github.com/cpython/cpython.git'
            >>> OwnerRepo(repo="/tmp/cpython", scheme="git+file").url("git+file")
            'git+file:///tmp/cpython.git'
            >>> OwnerRepo("cpython", "cpython", scheme="git+https").url("git+https")
            'git+https://github.com/cpython/cpython.git'
            >>> OwnerRepo("cpython", "cpython", scheme="git+ssh").url("git+ssh")
            'git+ssh://git@github.com/cpython/cpython.git'
            >>> OwnerRepo("cpython", "cpython", scheme="ssh").url("ssh")
            'git@github.com:cpython/cpython.git'

        :param scheme: Git URL scheme (Default: data:`mproject.GIT_DEFAULT_SCHEME`)

        :return: furl instance of GitHub URL
        """
        args = dict(scheme=scheme, host=GITHUB_DOMAIN, path=[self.owner, self.repo])
        if scheme == "git+file":
            if not self.repo.startswith("/"):
                raise ValueError(f"Repo must be an absolute file for '{scheme}': {self.repo}")
            args["path"] = [str(Path(self.repo).absolute().with_suffix(".git"))]
            del args["host"]
        elif "ssh" in scheme:
            args["username"] = "git"
        return furl(**args)


@dataclass
class EnvBuilder(venv.EnvBuilder):
    # noinspection PyUnresolvedReferences
    """
    Wrapper for :class:`venv.EnvBuilder`.

    Changed defaults for: `prompt`` `symlinks` and `with_pip`, adds `env_dir` to `__init__` arguments.

    This class exists to allow virtual environment creation to be
    customized. The constructor parameters determine the builder's
    behaviour when called upon to create a virtual environment.

    By default, the builder makes the system (global) site-packages dir
    *un*available to the created environment.

    If invoked using the Python -m option, the default is to use copying
    on Windows platforms but symlinks elsewhere. If instantiated some
    other way, the default is to *not* use symlinks (changed with the wrapper to use symlinks always).

    Args:
        system_site_packages: bool
            If True, the system (global) site-packages dir is available to created environments.
        clear: bool
            If True, delete the contents of the environment directory if it already exists, before environment creation.
        symlinks: bool
            If True, attempt to symlink rather than copy files into virtual environment.
        upgrade: bool
            If True, upgrade an existing virtual environment.
        with_pip: bool
            If True, ensure pip is installed in the virtual environment.
        prompt: str
            Alternative terminal prefix for the environment.
        upgrade_deps: bool
            Update the base venv modules to the latest on PyPI (python 3.9+).
        context: Simplenamespace
            The information for the environment creation request being processed.
        env_dir: bool
            The target directory to create an environment in.
        """
    system_site_packages: bool = False
    clear: bool = False
    symlinks: bool = True
    upgrade: bool = False
    with_pip: bool = True
    prompt: Optional[str] = "."
    upgrade_deps: bool = False
    env_dir: Optional[Union[Path, str]] = None
    context: Optional[SimpleNamespace] = field(default=None, init=False)

    def __post_init__(self):
        # noinspection PyUnresolvedReferences
        """
        Initialize the environment builder and also creates the environment is does not exist.

        Args:
            system_site_packages: If True, the system (global) site-packages
                                     dir is available to created environments.
            clear: If True, delete the contents of the environment directory if
                      it already exists, before environment creation.
            symlinks: If True, attempt to symlink rather than copy files into
                         virtual environment.
            upgrade: If True, upgrade an existing virtual environment.
            with_pip: If True, ensure pip is installed in the virtual
                         environment.
            prompt: Alternative terminal prefix for the environment.
            env_dir: The target directory to create an environment in.
            upgrade_deps: Update the base venv modules to the latest on PyPI (python 3.9+).
        """
        super().__init__(system_site_packages=self.system_site_packages, clear=self.clear, symlinks=self.symlinks,
                         upgrade=self.upgrade, with_pip=self.with_pip, prompt=self.prompt,
                         **(dict(upgrade_deps=self.upgrade_deps) if sys.version_info >= (3, 9) else {}))
        if self.env_dir:
            self.env_dir = Path(self.env_dir)
            if self.env_dir.exists():
                self.ensure_directories()
            else:
                self.create(self.env_dir)

    def create(self, env_dir: Optional[Union[Path, str]] = None) -> None:
        """
        Create a virtual environment in a directory.

        :param env_dir: The target directory to create an environment in.
        """
        if env_dir and self.env_dir is None:
            self.env_dir = env_dir
        super().create(self.env_dir)

    def ensure_directories(self, env_dir: Optional[Union[Path, str]] = None) -> SimpleNamespace:
        """
        Create the directories for the environment.

        :param env_dir: The target directory to create an environment in.

        Returns:
            A context object which holds paths in the environment, for use by subsequent logic.
        """
        self.context = super().ensure_directories(env_dir or self.env_dir)
        return self.context

    def post_setup(self, context: Optional[SimpleNamespace] = None) -> None:
        """
        Hook for post-setup modification of the venv. Subclasses may install
        additional packages or scripts here, add activation shell scripts, etc.

        :param context: The information for the environment creation request
                        being processed.
        """
        ProjectPy().pip_install()


@dataclass
class Git(git.Repo):
    """
    Dataclass Wrapper for :class:`git.Repo`.

    Represents a git repository and allows you to query references,
    gather commit information, generate diffs, create and clone repositories query
    the log.

    'working_tree_dir' is the working tree directory, but will raise AssertionError if we are a bare repository.
    """
    git: GitCmd = field(init=False)
    """
    The Git class manages communication with the Git binary.

    It provides a convenient interface to calling the Git binary, such as in::

     g = Git( git_dir )
     g.init()                   # calls 'git init' program
     rval = g.ls_files()        # calls 'git ls-files' program

    ``Debugging``
        Set the GIT_PYTHON_TRACE environment variable print each invocation
        of the command to stdout.
        Set its value to 'full' to see details about the returned values.

    """
    git_dir: AnyPath | None = field(default=None, init=False)
    """the .git repository directory, which is always set"""
    odb: Type[LooseObjectDB] = field(init=False)
    working_dir: AnyPath | None = field(default=None, init=False)
    """working directory of the git command, which is the working tree
    directory if available or the .git directory in case of bare repositories"""

    path: InitVar[AnyPath | None] = None
    """File or Directory inside the git repository, the default with search_parent_directories"""
    expand_vars: InitVar[bool] = True
    odbt: InitVar[Type[LooseObjectDB]] = GitCmdObjectDB
    """the path to either the root git directory or the bare git repo"""
    search_parent_directories: InitVar[bool] = True
    """if True, all parent directories will be searched for a valid repo as well."""

    def __post_init__(self, path: AnyPath | None, expand_vars: bool,
                      odbt: Type[LooseObjectDB], search_parent_directories: bool):
        """
        Create a new Repo instance

        Examples:
            >>> assert Git(__file__)
            >>> Git("~/repo.git")  # doctest: +SKIP
            >>> Git("${HOME}/repo")  # doctest: +SKIP

        Raises:
            InvalidGitRepositoryError
            NoSuchPathError

        Args:
            path: File or Directory inside the git repository, the default with search_parent_directories set to True
                or the path to either the root git directory or the bare git repo
                if search_parent_directories is changed to False
            expand_vars: if True, environment variables will be expanded in the given path
            search_parent_directories: Search all parent directories for a git repository.
        Returns:
            Git: Git instance
        """
        super(Git, self).__init__(path if path is None else path if (path := Path(path)).is_dir() else path,
                                  expand_vars=expand_vars,
                                  odbt=odbt, search_parent_directories=search_parent_directories)

    @classmethod
    def bare(cls, name: str = None, repo: "Git" = None) -> "Git":
        """
        Create a bare repository in a temporary directory, to manage global/system config or as a remote for testing.

        Args:
            name: the path of the bare repository
            repo: Git instance to update git config with remote url of the new bare repository (default: None)

        Returns:
            Git: Git instance
        """
        with tempfile.TemporaryDirectory(suffix=".git") as tmpdir:
            bare = cls.init(Path(tmpdir) / (f"{name}.git" if name else ""), bare=True)
            if repo:
                repo.config_writer().set_value("remote.origin.url", repo.git_dir).release()
            return bare

    @property
    def git_config(self) -> GitConfigParser:
        """
        Wrapper for :func:`git.Repo.config_reader`, so it is already read and can be used

        The configuration will include values from the system, user and repository
        configuration files.

        Examples:
            >>> conf = Git(__file__).git_config
            >>> conf.has_section('remote "origin"')
            True
            >>> conf.has_option('remote "origin"', 'url')
            True
            >>> conf.get('remote "origin"', 'url')  # doctest: +ELLIPSIS
            https://github.com/...
            >>> conf.get_value('remote "origin"', 'url', "")  # doctest: +ELLIPSIS
            https://github.com/...

        Returns:
            GitConfigParser: GitConfigParser instance
        """
        config = self.config_reader()
        config.read()
        return config

    @property
    def top(self) -> Path:
        """Git Top Directory Path."""
        path = Path(self.working_dir)
        return Path(path.parent if ".git" in path else path)

    @property
    def origin_url(self) -> furl:
        """Git Origin URL."""

        return furl(list(self.remote().urls)[0])


@dataclass
class ProjectBase:
    """Project Base Class"""
    name: str = ""
    python_running_major_minor: str = field(default=None, init=False)
    """Python major.minor version running in the project"""
    python_exe_site: Optional[Path] = field(default=None, init=False)
    """python site executable"""
    top: Optional[Path] = field(default=None, init=False)
    """project git top level path"""

    data: InitVar[Union[Path | ParseResult | str]] = None

    def __post_init__(self):
        self.python_running_major_minor = sysconfig.get_python_version()
        self.python_exe_site = Path(sys.executable).resolve()
        top = getoutput('git rev-parse --show-toplevel')
        if top:
            self.top = Path(top).resolve()

    @classmethod
    def from_name(cls, name: str = __project__) -> 'ProjectBase':
        """
        Create a ProjectBase instance from project name

        Args:
            name: project name

        Returns:
            ProjectBase: ProjectBase instance
        """
        return cls(name)


class ProjectCmd:
    """Project Command Base Class"""

    def __init__(self):
        pass

    @staticmethod
    @app.command(name="version")
    def version() -> None:
        """
        Prints the installed version of the package.

        Returns:
            None
        """
        print(version())


@dataclass
class ProjectPy(ProjectBase):
    """
    PyProject Class
    """
    extras_require: tuple[str, ...] = field(default_factory=tuple, init=False)
    """extras_requires from setup.cfg options"""
    install_requires: tuple[str, ...] = field(default_factory=tuple, init=False)
    """install_requires from setup.cfg options"""
    pypi_name: str = field(default="", init=False)
    """name from setup.cfg metadata"""
    py_packages: tuple[str, ...] = field(default_factory=tuple, init=False)
    """python packages from setup.cfg options"""
    pyproject_toml: Optional[FileConfig] = field(default=None, init=False)
    """pyproject.toml"""
    python_exe_venv: Optional[Path] = field(default=None, init=False)
    """python venv executable"""
    _python_requires: SpecifierSet = field(default=SpecifierSet, init=False)
    """python_requires from setup.cfg options"""
    requirements: tuple[str, ...] = field(default_factory=tuple, init=False)
    """all requirements: install_requires, extras_require and :data:`venv.CORE_VENV_DEPS`"""
    setup_cfg: Optional[FileConfig] = field(default=None, init=False)
    """setup.cfg"""
    venv: EnvBuilder = field(default=None, init=False)
    """venv builder"""

    pip_install_options: ClassVar[tuple[str, ...]] = ("-m", "pip", "install", "--quiet", "--no-warn-script-location", )
    pip_upgrade_options: ClassVar[tuple[str, ...]] = pip_install_options + ("--upgrade", )

    def __post_init__(self):
        """
        Post Init
        """
        super().__post_init__()
        if self.top:
            file = self.top / 'pyproject.toml'
            if file.exists():
                self.pyproject_toml = FileConfig(file=file, config=toml.load(file))

            file = self.top / 'setup.cfg'
            if file.exists():
                self.setup_cfg = FileConfig(file=file, config=setuptools.config.read_configuration(file))

            if self.setup_cfg:
                metadata = self.setup_cfg.config.get("metadata", {})
                self.pypi_name = metadata.get('name', None)

                options = self.setup_cfg.config.get('options', dict())
                self.extras_require = tuple(sorted({dep for extra in options.get('extras_require', dict()).values()
                                                    for dep in extra}))
                self.install_requires = tuple(options.get('install_requires', []))
                self.py_packages = tuple(options.get('packages', []))
                self.python_requires = options.get('python_requires')
                self.requirements = tuple(sorted(self.install_requires + self.extras_require + venv.CORE_VENV_DEPS))

                self.venv = EnvBuilder(env_dir=self.top / venv.__name__)
                self.python_exe_venv = Path(self.venv.context.env_exec_cmd)

    def pip_install(self, *args: str, site: bool = False, upgrade: bool = False) -> None:
        """
        Install packages in venv

        Args:
            *args: packages to install (default: all requirements)
            site: install packages in site or venv (default: False)
            upgrade: upgrade packages (default: False)

        Returns:
            None
        """
        executable = self.python_exe_site if site else self.python_exe_venv
        check_call([executable, *self.pip_upgrade_options, "pip", "wheel"])
        check_call([executable, *(self.pip_upgrade_options if upgrade else self.pip_install_options),
                    *(args or self.requirements)])

    @property
    def python_requires(self) -> str:
        if len(self._python_requires) > 0:
            return list(self._python_requires)[0].version
        return ""

    @python_requires.setter
    def python_requires(self, value: Optional[SpecifierSet]) -> None:
        self._python_requires = value or SpecifierSet()


venv.EnvBuilder = EnvBuilder

# TODO: añadir el path del proyecto como argumento
if __name__ == "__main__":
    from typer import Exit
    try:
        Exit(app())
    except KeyboardInterrupt:
        click.secho('Aborted!')
        Exit()
