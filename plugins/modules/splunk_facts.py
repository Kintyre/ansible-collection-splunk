#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import hashlib
import os
import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.cdillc.splunk.plugins.module_utils.ksconf_shared import find_splunk_home


__metaclass__ = type


DOCUMENTATION = '''
---
module: splunk_facts
short_description: Gathers facts about a Splunk installation
version_added: "0.10.0"
author: Lowell C. Alleman (@lowell80)
options:
    splunk_home:
        description:
            - Path to Splunk installation path. If not provided, this
              module will check the $SPLUNK_HOME environment variable
              and then several commonly used install paths.
        required: false
        default: null
        version_added: 1.8

description:
    - This module collects various pieces of data about a Splunk installation
notes:
    - Parameters to enable/disable various config or run-time stats may be added later.

'''

EXAMPLES = '''

Typical use:
- splunk_facts:

Or specify a custom Splunk install home
- splunk_facts: splunk_home=/opt/acmeco/splunk
'''

'''
Notes about output layout:

    ansible_splunk_version
      version
      build
      product
      platform
    ansible_splunk_dist_search
      server_public_key
    ansible_splunk_config
      <config>
        <stanza>
          <key>

'''


SPLUNK_VERSION = "etc/splunk.version"
SPLUNK_INSTANCE_CFG = "etc/instance.cfg"
SPLUNK_AUTH_SECRET = "etc/auth/splunk.secret"
SPLUNK_DIST_SEARCH_PUB_KEY = "etc/auth/distServerKeys/trusted.pem"


class SplunkMetadata(object):
    def __init__(self, module, splunk_home=None):
        self.module = module
        if not splunk_home:
            splunk_home = find_splunk_home()
            if not splunk_home:
                self.fail("Couldn't locate SPLUNK_HOME.")
                return
        self.splunk_home = splunk_home
        self._fail = False
        self._data = {}
        self._prefix = 'ansible_splunk_%s'
        self.fetch_version()
        self.fetch_dist_search_keys()
        self.fetch_guid()
        self.fetch_splunksecret()
        self._error = None

    def error(self, msg):
        self._error = msg

    def fail(self, msg):
        self._error = msg
        self._fail = True

    def fetch_version(self):
        splunk_version = os.path.join(self.splunk_home, SPLUNK_VERSION)
        sv = {}
        try:
            for line in open(splunk_version):
                line = line.strip()
                if line and "=" in line:
                    (key, value) = line.strip().split("=", 1)
                    sv[key.lower()] = value
            self._data["version"] = sv
        except Exception:
            self.fail("Unable to get version info from file:  %s" % splunk_version)

    def fetch_dist_search_keys(self):
        # NOTE:  To get the correct path, we need to do something like:
        #           btool distsearch list tokenExchKeys
        #       and then parse for "certDir" and "publicKey" values.
        #       But we're just starting with the static default path.
        pub_key_path = os.path.join(self.splunk_home, SPLUNK_DIST_SEARCH_PUB_KEY)
        try:
            pub_key = open(pub_key_path).read()
            self._data["dist_search"] = dict(server_public_key=pub_key)
        except Exception:
            self.error("Unable to read distributed search public key: %s" % pub_key_path)

    def fetch_guid(self):
        # Only looking in the Splunk 6.x location (skipping server.conf)
        cfg_file = os.path.join(self.splunk_home, SPLUNK_INSTANCE_CFG)
        try:
            for line in open(cfg_file):
                mo = re.match(r"^guid\s*=\s*([A-Fa-f0-9-]+)\s*$", line)
                if mo:
                    self._data["guid"] = mo.group(1)
                    return
        except Exception:
            self.error("Unable to read guid from file: %s" % cfg_file)

    def fetch_splunksecret(self):
        fn = os.path.join(self.splunk_home, SPLUNK_AUTH_SECRET)
        try:
            # Note could use module.sha1(filename) instead ....
            self._data["secret_hash"] = hashlib.sha1(open(fn).read()).hexdigest()
        except Exception:
            self.error("Unable to read secret file: %s" % fn)

    def return_facts(self):
        if self._fail:
            return dict(failed=True, msg=self._error)
        sf = {}
        sf[self._prefix % "home"] = self.splunk_home
        for (key, value) in self._data.items():
            sf[self._prefix % key] = value
        if self._error:
            sf["msg"] = self._error
        return dict(changed=False, ansible_facts=sf)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            splunk_home=dict(required=False, default=None),
        ),
        supports_check_mode=True
    )

    # Parameters
    splunk_home = module.params['splunk_home']

    splunk_facts = SplunkMetadata(module, splunk_home=splunk_home)
    output = splunk_facts.return_facts()
    module.exit_json(**output)


if __name__ == '__main__':
    main()
