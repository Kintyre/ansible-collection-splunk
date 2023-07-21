# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function


__metaclass__ = type

import os
import re

from ansible.module_utils.basic import AnsibleModule


__version__ = "0.20.0"

SIDELOAD_STATE_FILE = ".ksconf_sideload.json"

# Traditional Splunk home (install paths)
SPLUNK_HOME_PATH = [
    "/opt/splunk",
    "/Applications/Splunk",
    "/opt/splunkforwarder"
]


def find_splunk_home():
    """ Find an appropriate value for SPLUNK_HOME.

    First, use $SPLUNK_HOME if that directory exists.  After that, try a series
    of path-based guesses based on common installation files, and finally just
    go with *any* match against the well known splunk home list.

    Multiple splunk installations are not explicitly supported.
    """
    if "SPLUNK_HOME" in os.environ:
        path = os.environ["SPLUNK_HOME"]
        if os.path.isdir(path):
            return path

    # Check popular paths
    for known_path in ("bin/splunk", "etc/splunk.version", None):
        path = _guess_splunk_home(SPLUNK_HOME_PATH, known_path)
        if path:
            return path
    return None


def _guess_splunk_home(discovery_paths, test_file):
    for path in discovery_paths:
        if os.path.isdir(path):
            if test_file:
                test_path = os.path.join(path, test_file)
                if os.path.isfile(test_path):
                    return path
            else:
                return path
    return None


def check_ksconf_version(module: AnsibleModule = None) -> tuple:
    if not module:
        from ansible.errors import AnsibleActionFail
        from ansible.utils.display import Display
        display = Display()
    try:
        from ksconf import __version__ as ksconf_version
    except ImportError:
        message = "Unable to import the 'ksconf' python module.  "\
                  "Try running 'pip install -U ksconf'"
        if module:
            module.fail_json(msg=message)
        else:
            raise AnsibleActionFail(message=message)

    match = re.match(r'(\d+)\.(\d+)\.(\d+)(.*)$', ksconf_version)
    if match:
        p = match.groups()
        return int(p[0]), int(p[1]), int(p[2]), p[3]
    else:
        message = f"Unable to parse ksconf version.  '{ksconf_version}'"
        if module:
            module.warn(message)
        else:
            display.warning(message)
        return 0, 0, 0, ksconf_version
