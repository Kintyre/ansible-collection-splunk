#!/usr/bin/python
# -*- coding: utf-8 -*-
# Heavy inspiration from https://github.com/ansible/ansible/blob/devel/lib/ansible/modules/command.py

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

from __future__ import absolute_import, division, print_function

import datetime
import os
import shlex

from ansible.module_utils._text import to_text
from ansible.module_utils.basic import AnsibleModule


__metaclass__ = type


MODULE_NAME = "splunk_cli"


DOCUMENTATION = '''
---
module: splunk_cli
short_description: Splunk command line interface
description:
    - This is a lightweight wrapper around the Splunk CLI that handles auth
      parameter hiding and some other niceties.
    - If the Splunk command requires authentication, provide the I(username) and
      I(password) options.
version_added: "0.9.0"
author: Lowell C. Alleman (@lowell80)
attributes:
    check_mode:
        details: while the command itself is arbitrary and cannot be subject to
                 the check mode semantics it adds C(creates)/C(removes) options
                 as a workaround
        support: partial
    diff_mode:
        support: none
    platform:
      support: full
      platforms: posix
    raw:
      support: full
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


def main():
    # Note attempting to use '_raw_params' here, like `command`` does, doesn't
    # work.  Apparently you must be on the the "special list" (RAW_PARAM_MODULES)
    # this must be something that Ansible wants to restrict.
    # Therefore cmd="..." syntax must be use.
    module = AnsibleModule(
        argument_spec=dict(
            cmd=dict(),
            splunk_home=dict(required=True),
            splunk_uri=dict(default=None, aliases=["uri", "splunkd_uri"]),
            username=dict(default=None),
            password=dict(default=None, no_log=True),
            # token=dict(default=None, no_log=True),
            # Borrowed from the shell/command module
            creates=dict(default=None),
            removes=dict(default=None),
            create_on_success=dict(default=None),
        )
    )
    args = module.params["cmd"]
    splunk_home = module.params["splunk_home"]
    splunk_uri = module.params['splunk_uri']
    splunk_user = module.params['username']
    splunk_pass = module.params['password']
    creates = module.params['creates']
    removes = module.params['removes']
    create_on_success = module.params['create_on_success']

    if (splunk_user or splunk_pass) and not (splunk_user and splunk_pass):
        module.fail_json(msg="Both 'username' and 'password' must be specified at the same time.")

    if args.strip() == '':
        module.fail_json(rc=256, msg="no command given")

    splunk_home = os.path.abspath(os.path.expanduser(splunk_home))

    # Q: Why chdir to splunk home, should the caller have control of this?
    try:
        os.chdir(splunk_home)
    except (IOError, OSError) as e:
        module.fail_json(rc=257, msg='Unable to change directory before execution: %s' % to_text(e))

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
                cmd=args, changed=False, rc=0,
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
        # Tell splunk CLI to issue command to remote Splunk instance
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
        open(os.path.expanduser(create_on_success), "w").write("MARKER FILE CREATED")
    module.exit_json(
        cmd=args,
        stdout=to_text(out).rstrip("\r\n"),
        stderr=to_text(err).rstrip("\r\n"),
        rc=rc,
        start=to_text(start_time),
        end=to_text(end_time),
        delta=to_text(delta),
        changed=True,
    )


if __name__ == '__main__':
    main()
