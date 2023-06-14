# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function


__metaclass__ = type

import os
import re

from ansible.errors import AnsibleActionFail
from ansible.module_utils.basic import AnsibleModule
from ansible.utils.display import Display


__version__ = "0.18.1"

SIDELOAD_STATE_FILE = ".ksconf_sideload.json"

# Traditional Splunk home (install paths)
SPLUNK_HOME_PATH = [
    "/opt/splunk",
    "/Applications/Splunk",
    "/opt/splunkforwarder"
]


def find_splunk_home():
    if "SPLUNK_HOME" in os.environ:
        return os.environ["SPLUNK_HOME"]
    for path in SPLUNK_HOME_PATH:
        if os.path.isdir(path):
            return path
    return None


def check_ksconf_version(module: AnsibleModule = None) -> tuple:
    if not module:
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
