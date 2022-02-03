#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Ansible module to run the Splunk command line interface


Session key / token support:
    File:  $SPLUNK_HOME/.splunk/authToken_{{inventory_hostname}}_{{splunkd_port}}
    Content:
        <auth>
            <username>{{username}}</username>
            <sessionkey>{{ token | replace("Splunk ","") }}</sessionkey>
            <cookie>splunkd_{{splunkd_port}}</cookie>
        </auth>
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type



MODULE_NAME = "splunk_cli"


DOCUMENTATION = '''
---
module: splunk_cli
short_description: Splunk command line interface
description:
    - This is a lightweight wrapper around the Splunk CLI that handles auth parameter hiding and some other niceties.
    - If the Splunk command requires authentication, provide the I(username) and I(password) options.
version_added: "1.9"
author: Lowell C. Alleman <lowell.alleman@cdillc.com>
requirements:
    - splunk-sdk
options:
    splunkd_uri:
        description:
            - The Splunkd endpoint of the Splunk server to configure.
            - Defaults to the local server and default splunkd port.
        required: false
        default: https://localhost:8089
        aliases: [ uri ]

    username:
        description:
            - Splunk username for username/password authentication.
            - When provided, I(password) must also be specified.
        required: false
        default: null

    password:
        description:
            - The password for username/password authentication.
            - Must be provided if I(username) is provided.
        required: false
        default: null

#    token:
#        description:
#            - Token to use when authentication has already taken place.
#            - The C(token) can be specified instead of I(username) and I(password).
#            - This module returns an output named I(token) that can be used for
#              subsequent splunkd calls to the same splunkd endpoint.
#        required: false
#        default: null

    splunk_home:
        description:
            - The Splunk installation home.  $SPLUNK_HOME
        required: true
        default: /opt/splunk

    cmd:
        description:
            - Command line arguments to the Splunk CLI
        required: true
        default: null

#notes:
'''

EXAMPLES = '''
Reload the deployment server:

- splunk_cli:
    cmd: reload deploy-server
    splunk_home: "{{splunk_home}}"
    username: "{{splunk_admin_user}}"
    password: "{{splunk_admin_pass}}"
'''

import os
import shlex
import datetime
import re

from ansible.module_utils.basic import AnsibleModule


# from ansible.module_utils.splitter import *




# Dict of options and their defaults
OPTIONS = {
    'splunk_home' : None,
    'splunk_uri' : None,
    'username' : None,
    'password' : None,
    'creates': None,
    'removes' : None
}

# This is a pretty complex regex, which functions as follows:
#
# 1. (^|\s)
# ^ look for a space or the beginning of the line
# 2. ({options_list})=
# ^ expanded to (chdir|creates|executable...)=
#   look for a valid param, followed by an '='
# 3. (?P<quote>[\'"])?
# ^ look for an optional quote character, which can either be
#   a single or double quote character, and store it for later
# 4. (.*?)
# ^ match everything in a non-greedy manner until...
# 5. (?(quote)(?<!\\)(?P=quote))((?<!\\)(?=\s)|$)
# ^ a non-escaped space or a non-escaped quote of the same kind
#   that was matched in the first 'quote' is found, or the end of
#   the line is reached
OPTIONS_REGEX = '|'.join(OPTIONS.keys())
PARAM_REGEX = re.compile(
    r'(^|\s)(' + OPTIONS_REGEX +
    r')=(?P<quote>[\'"])?(.*?)(?(quote)(?<!\\)(?P=quote))((?<!\\)(?=\s)|$)'
)



def main():
    module = AnsibleModule(
        argument_spec = dict(
            cmd = dict(),
            splunk_home = dict(required=True),
            splunk_uri  = dict(default=None, aliases=["uri", "splunkd_uri"]),
            username    = dict(default=None),
            password    = dict(default=None, no_log=True),
#            token       = dict(default=None, no_log=True),
            # Borrowed from the shell/command module
            creates     = dict(default=None),
            removes     = dict(default=None),
            create_on_success = dict(default=None),
        )
    )
    args        = module.params["cmd"]
    splunk_home = module.params["splunk_home"]
    splunk_uri  = module.params['splunk_uri']
    splunk_user = module.params['username']
    splunk_pass = module.params['password']
    creates     = module.params['creates']
    removes     = module.params['removes']
    create_on_success = module.params['create_on_success']

    if (splunk_user or splunk_pass) and not (splunk_user and splunk_pass):
        module.fail_json(msg="Both 'username' and 'password' must be specified at the same time.")

    if args.strip() == '':
        module.fail_json(rc=256, msg="no command given")

    splunk_home = os.path.abspath(os.path.expanduser(splunk_home))
    os.chdir(splunk_home)

    if creates:
        # do not run the command if the line contains creates=filename
        # and the filename already exists.
        v = os.path.expanduser(creates)
        if os.path.exists(v):
            module.exit_json(
                cmd=args, changed=False, rc=0,
                stdout="skipped, since %s exists" % v,
                stderr=False
            )

    if removes:
        # do not run the command if the line contains removes=filename
        # and the filename does not exist.  This allows idempotence
        # of command executions.
        v = os.path.expanduser(removes)
        if not os.path.exists(v):
            module.exit_json(
                cmd=args,  changed=False, rc=0,
                stdout="skipped, since %s does not exist" % v,
                stderr=False
            )

    args = shlex.split(args)
    executable = os.path.join(splunk_home, "bin", "splunk")
    start_time = datetime.datetime.now()

    # Make sure that 'splunk' is the first argument
    if args[0] != "splunk":
        args.insert(0, "splunk")

    if splunk_user:
        args.append("-auth")
        args.append("%s:%s" % (splunk_user, splunk_pass))

    if splunk_uri:
        args.append("-uri")
        args.append(splunk_uri)

    rc, out, err = module.run_command(args, executable=executable, use_unsafe_shell=False)

    end_time = datetime.datetime.now()
    delta = end_time - start_time

    if out is None:
        out = ''
    if err is None:
        err = ''

    if rc == 0 and create_on_success:
        open(os.path.expanduser(create_on_success),"w").write("MARKER FILE CREATED")
    module.exit_json(
        cmd      = args,
        stdout   = out.rstrip("\r\n"),
        stderr   = err.rstrip("\r\n"),
        rc       = rc,
        start    = str(start_time),
        end      = str(end_time),
        delta    = str(delta),
        changed  = True,
    )


main()
