import subprocess
from pybuilder.core import Author, init, use_plugin, task, before, after

use_plugin("filter_resources")
use_plugin("python.core")
use_plugin("python.install_dependencies")
use_plugin("python.distutils")
use_plugin("python.pycharm")

name = "fuct"
url = "https://github.com/MrOnion/fuct"
description = "Visit %s for more information." % url

authors = [Author("Ari Karhu", "ari@baboonplanet.com")]
license = "MIT License"
summary = "Unified commandline tools for FreeEMS"

default_task = ["install_dependencies", "publish"]


@init
def set_properties(project, logger):
    project.get_property("filter_resources_glob").append("**/fuct/__init__.py")
    project.depends_on("pyserial", ">=2.7")
    project.depends_on('futures;python_version=="2.7"')
    project.depends_on("colorlog[windows]", ">=2.0")
    logger.info("Executing git describe")
    project.version = subprocess.check_output(
        ["git", "describe", "--abbrev=0"]).decode('utf-8').rstrip("\n")
    project.set_property("gitdesc", subprocess.check_output(
        ["git", "describe", "--tags", "--always", "--long", "--dirty"]).decode('utf-8').rstrip("\n"))
    project.set_property("dir_dist", "$dir_target/dist/%s-%s" % (project.name, project.version))
    project.set_property('distutils_commands', 'build')
    project.set_property('distutils_command_options', {'build': ('-e', '/usr/bin/env python', 'bdist_wheel')})
