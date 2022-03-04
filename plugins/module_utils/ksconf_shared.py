# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function


__metaclass__ = type

import os
import re

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.text.converters import to_native


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


def check_ksconf_version(module):
    # type: (AnsibleModule) -> tuple

    try:
        from ksconf import __version__ as ksconf_version
    except ImportError:
        return module.fail_json("Unable to import the 'ksconf' python module.  "
                                "Try running 'pip install -U kintyre-splunk-config'")

    match = re.match(r'(\d+)\.(\d+)\.(\d+)(.*)$', ksconf_version)
    if match:
        p = match.groups()
        return int(p[0]), int(p[1]), int(p[2]), p[3]
    else:
        module.warn("Unable to parse ksconf version.  '{}'".format(ksconf_version))
        return 0, 0, 0, ksconf_version
