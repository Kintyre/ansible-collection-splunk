#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Ansible module to manage Splunk users via the Splunkd REST API.
"""

from __future__ import absolute_import, division, print_function

import os
import ssl
import sys

from ansible.module_utils.basic import BOOLEANS, AnsibleModule

__metaclass__ = type


MODULE_NAME = "splunk_user"


# Search path for Splunk SDK, which is bundled as part of some Splunk apps
# This is only used if the splunklib import fails
SPLUNK_SDK_SEARCH_PATH = [
    "lib/python37/site-packages",
    "etc/apps/splunk_management_console/bin",
]


DOCUMENTATION = '''
---
module: splunk_user
short_description: Manage Splunk user accounts
description:
    - Create, delete, and update local Splunk user accounts with Ansible.
    - This module uses the Python Splunk SDK and requires access to the splunkd administrative port.
    - Authentication can be handled via either I(username) and I(password) or via I(token).
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
            - Splunk username for username/password authentication to Splunkd.
            - When provided, I(password) must also be specified.
            - Use the I(splunk_user) option for Splunk user being created, updated, or removed.
        required: false
        default: null

    password:
        description:
            - The password for username/password authentication to Splunkd.
            - Must be provided if I(username) is provided.
            - Use the I(splunk_pass) for the password to the Splunk user being created or updated.
        required: false
        default: null

    token:
        description:
            - Token to use when authentication has already taken place.
            - The C(token) can be specified instead of I(username) and I(password).
            - This module returns an output named I(token) that can be used for
              subsequent splunkd calls to the same splunkd endpoint.
        required: false
        default: null

    splunk_home:
        description:
            - Path to Splunk installation.
            - This is used if the splunk-sdk is not installed for all users.
        required: false
        default: null

    state:
        description:
            - Ensure the user is either present or absent; or list the contents of the user's configuration.
            - Users that already existing will be updated as specified, except for I(splunk_pass).
            - The C(content) output contains the final setting.
            - If the state is absent, the C(content) output will be missing
              if the stanza was previously removed.
        required: false
        default: present
        choices: [present, absent, list]

    update_password:
        description:
            - Replace the existing password with the one specified.
            - The default is to only set the password when the user is created.
            - When enabled, the result of this module will always report as
              changed since there is no way to determine if the new password is
              different than the currently assigned password.
        required: false
        default: false
        choices: [ true, false ]

    append_roles:
        description:
            - When true, the specified I(roles) will be appended to the user's existing roles.
            - Otherwise, the roles will be replaced as-is.
        required: false
        default: false
        choices: [ true, false ]

    splunk_user:
        description:
            - Name of the user to create, modify or delete.
        required: true
        default: null
        aliases: [ name ]

    splunk_pass:
        description:
            - Password for the Splunk user account being created or modified.
            - See the notes regarding changing passwords under the I(update_password) option.
            - This option is required when C(state=present).
        required: false
        default: null

    roles:
        description:
            - Comma separated list of role associated with the Splunk user.
        required: true
        default: user

    tz:
        description:
            - Timezone associated with the Splunk user.
        required: false
        default: null
        aliases: [ timezone ]

    realname:
        description:
            - The full name (comment) of the user account.
        required: false
        default: null
        aliases: [ fullname, comment ]

    defaultapp:
        description:
            - The default Splunk application the user sees when they login to Splunk Web.
        required: false
        default: null
        aliases: [ defaultApp ]

    email:
        description:
            - Email address associated with the Splunk user.
        required: false
        default: null

# Perhaps someday Ansible module docs will include something like this....

outputs:
    result:
        description:
            - The overall result of the module run.
            - Options include C(created), C(updated), C(deleted), or C(unchanged)
    token:
        description:
            - The Splunk auth token created used for the REST API calls.
            - This value can be passed into I(token) of a subsequent REST-based operation.
#notes:
'''

EXAMPLES = '''
Create a new user named 'bob':

- splunk_user: state=present
               username=admin password=manage
               splunk_user=bob splunk_pass=aReallyGoodPassword
               roles=user,admin tz=America/New_York


Change the password of existing user 'joe':
- splunk_user: state=present update_password=true
               username=admin password=manage
               splunk_user=joe splunk_pass=NewPassWord
'''


def import_splunk_sdk(splunk_home=None, search_paths=None):
    sys_path_reset = None
    if splunk_home:
        # Take a backup copy
        sys_path_reset = list(sys.path)
        for p in search_paths:
            sys.path.append(os.path.join(splunk_home, p))
    try:
        import splunklib.client as client

        # Assume that we only need to do this with Splunk SDK living under the SPLUNK_HOME; OS-level install should be up-to-date via other mechanisms.
        evil_ssl_nocertcheck_hack()
    except ImportError:
        client = None
    if sys_path_reset:
        del sys.path[:]
        sys.path.extend(sys_path_reset)
    return client


__default__create_default_https_context = None


def evil_ssl_nocertcheck_hack():
    """
    For newer versions of Python (2.7.9) and older version of the splunk-sdk,
    this hack lets us revert to the old behavior and keep thing moving.
    """
    global __default__create_default_https_context
    import splunklib
    if splunklib.__version__ <= "1.3.1" and sys.version_info >= (2, 7, 9):
        __default__create_default_https_context = ssl._create_default_https_context
        ssl._create_default_https_context = ssl._create_unverified_context


def connect(module, uri, username, password, token=None, owner=None, app=None, sharing=None):
    from ansible.module_utils.six.moves.urllib.parse import urlparse
    up = urlparse(uri)
    port = up.port or 8089
    if not token:
        service = client.connect(host=up.hostname, port=port, scheme=up.scheme,
                                 username=username, password=password,
                                 owner=owner, app=app, sharing=sharing)
    else:
        service = client.Service(host=up.hostname, port=port, scheme=up.scheme,
                                 token=token, owner=owner, app=app, sharing=sharing)
    if not service:
        module.fail_json(msg="Failure connecting to Splunkd:  "
                         "splunklib.client.connect() returned None.")
    return service


def create_user(module, service, params):
    splunk_user = params["splunk_user"]
    splunk_pass = params["splunk_pass"]
    roles = [r.strip() for r in params["roles"].split(",")]
    realname = params["realname"]
    tz = params["tz"]
    email = params["email"]
    defaultapp = params["defaultapp"]
    update_password = params["update_password"]
    append_roles = params["append_roles"]

    output = {}
    changes = {}
    atrsupd = []
    created = False

    try:
        user = service.users[splunk_user]
        if update_password:
            changes["password"] = splunk_pass
            atrsupd.append("password")
    except KeyError:
        user = service.users.create(username=splunk_user, password=splunk_pass,
                                    roles=roles)
        atrsupd.extend(["user", "password", "roles"])
        created = True

    # Look at individual parameter values and update as necessary
    if roles and set(roles) != set(user.roles):
        new_roles = set(roles)
        if append_roles:
            new_roles.update(user.roles)
        changes['roles'] = list(new_roles)
        atrsupd.append("roles")

    if realname and realname != user.realname:
        changes['realname'] = realname
        atrsupd.append("realname")

    if tz and tz != user.tz:
        changes['tz'] = tz
        atrsupd.append("tz")

    if email and email != user.email:
        changes['email'] = email
        atrsupd.append("email")

    if defaultapp and defaultapp != user.defaultApp:
        changes['defaultApp'] = defaultapp
        atrsupd.append("defaultApp")

    output["result"] = "unchanged"
    if created:
        output["changed"] = True
        output["result"] = "created"

    if changes:
        user.update(**changes).refresh()
        output["changed"] = True
        if not created:
            output["result"] = "updated"

    output["updated_attrs"] = atrsupd
    output["content"] = dict(user.content)
    output["endpoint"] = str(user.links['edit'])
    return output


def delete_user(module, service, params):
    splunk_user = params["splunk_user"]
    output = {}
    try:
        user = service.users[splunk_user]
        # May be informative to the caller (possibly a "move" use-case)
        output["content"] = dict(user.content)
        output["result"] = "deleted"
        try:
            user.delete()
        except Exception as e:
            output["failed"] = True
            output["msg"] = "Unable to delete user '%s'  Exception:  %s" % (splunk_user, e)
            return output
        output["changed"] = True
    except KeyError:
        output["result"] = "missing"
        output["changed"] = False
        # Empty content - For output consistency
        output["content"] = {}
    return output


def list_user(module, service, params):
    """
    Return an existing user record
    """
    splunk_user = params["splunk_user"]
    output = {}
    try:
        user = service.users[splunk_user]
        output["result"] = "present"
    except KeyError:
        output["result"] = "missing"
        output["msg"] = "Unable to find user '%s'" % (splunk_user)
        output["failed"] = True
        return output
    output["content"] = dict(user.content)
    output["endpoint"] = str(user.links['list'])
    return output


def main():
    global client

    module = AnsibleModule(
        argument_spec=dict(
            # Splunkd endpoint and authentication
            splunkd_uri=dict(default="https://localhost:8089", aliases=["uri"]),
            username=dict(default=None),
            password=dict(default=None, no_log=True),
            token=dict(default=None, no_log=True),
            splunk_home=dict(default=None),
            # Settings for module behavior
            state=dict(default='present',
                       choices=['present', 'absent', 'list']),
            update_password=dict(type='bool', default='false', choices=BOOLEANS),
            append_roles=dict(type='bool', default='false', choices=BOOLEANS),
            # User settings
            splunk_user=dict(required=True),
            splunk_pass=dict(default=None, no_log=True),
            roles=dict(default="user"),
            tz=dict(default=None),
            realname=dict(default=None),
            defaultapp=dict(default=None),
            email=dict(default=None)
        ),
    )

    # Outputs
    #   result:     created, updated (merge), deleted
    #   endpoint:   The Splunk REST endpoint path used by this operation
    #   attributes:  The dictionary containing user values
    #   token:      Splunk auth token

    p = module.params

    if client is None:
        # Try to find the splunk-sdk bundled under $SPLUNK_HOME if it's not globally available
        if p["splunk_home"]:
            client = import_splunk_sdk(p["splunk_home"], SPLUNK_SDK_SEARCH_PATH)

    if client is None:
        module.fail_json(msg='splunk-sdk required for this module')

    if not ((p["username"] and p["password"]) or p["token"]):
        module.fail_json(msg="%s requires either (1) 'username' and 'password' parameters, "
                             "or (2) token parameter for Splunkd authentication" % (MODULE_NAME,))

    try:
        service = connect(module, p['splunkd_uri'], p['username'],
                          p['password'], p['token'], sharing="system")
    except Exception as e:
        module.fail_json(msg="Unable to connect to splunkd.  Exception: %s" % e)

    if p["state"] == "present":
        output = create_user(module, service, module.params)
    elif p["state"] == "absent":
        output = delete_user(module, service, module.params)
    elif p["state"] == "list":
        output = list_user(module, service, module.params)
    else:
        module.fail_json(msg="Unsupported state of '%s'" % p["state"])

    # For convenience, pass along some of the input parameters
    # Add auth 'token' which can be used for subsequent calls in the same play.
    output["token"] = service.token
    # DEBUG, or is this worth keeping?
    output["params"] = p
    output["_splunksdk_path"] = client.__file__
    module.exit_json(**output)


if __name__ == '__main__':
    client = import_splunk_sdk()
    main()


# Reset ugliness of SSL hack (this could matter when Ansible is running in pipelining mode)
if __default__create_default_https_context:
    ssl._create_default_https_context = __default__create_default_https_context
