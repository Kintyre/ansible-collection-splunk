#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Ansible module to manage Splunk props via the Splunkd REST API.


To-do:
    - Finish the DOCUMENTATION string with parameters!!
    - Improve error handling.  Not sure what all stuff can throw exceptions.
    - Add support for tracking which keys were updated.  See note below on complexities.
    - Handle round-trip issues.  See notes below.
    - Come up with a way to remove settings.  (Possibly by adding a key and setting it to None/null)


===== Round-trip issues =====
It's possible that updates to "special" fields like "eai:*" and maybe even
"disabled" will cause issues. Right now all keys are returned when
"state=list" which means that a round-trip from one call to another could
break things.

Possible solutions could include (1) stripping out
these values from the output, (2) moving these values to a separate output or
"metadata" sub dictionary, or (3) apply some kind of filtering to the inbound
'settings' dictionary.  It's also possible that this is all natively handled
by the Splunk Python SDK.  Not sure.  This all needs tested.


===== Tracking changes =====
Q:  Do we want to track which keys were updated?  Seems like it could be
helpful but a solid use case hasn't emerged.  It's more complicated that first
thought.  Is a change
    (1) a full listing of all keys in settings,
    (2) the difference between server content and given 'settings', or
    (3) keys that were actually updated on the server?
We don't know if some keys may be rejected when pushed to the server.  Also,
booleans have multiple identical values which could trigger false positives.
Seems like we should wait until we actually need this functionality before
adding it.
"""

MODULE_NAME = "splunk_rest_conf"

# CONF_CHOICES:  Not sure if listing config options is a good idea or not.
# Does the ansible module restrict parameters to this list, or if it still
# accepts other values... If I go with this option, find a way to dynamically
# UPDATE The DOCUMENTATION string too.

CONF_CHOICES = ["server", "props", "transforms", "macros", ]



DOCUMENTATION = '''
---
# If a key doesn't apply to your module (ex: choices, default, or
# aliases) you can use the word 'null', or an empty list, [], where
# appropriate.
module: splunk_rest_conf
short_description: Ansible module to manage Splunk configurations via the Splunkd REST API
description:
    - Longer description of the module
    - You might include instructions
version_added: "1.9"
author: Lowell C. Alleman <lalleman@turnberrysolutions.com>
notes:
    - Other things consumers of your module should know
requirements:
    - splunk-sdk
options:
# One or more of the following
    option_name:
        description:
            - Words go here
            - that describe
            - this option
        required: true or false
        default: a string or the word null
        choices: [list, of, choices]
        aliases: [list, of, aliases]
'''



try:
    import splunklib.client as client
    HAVE_SPLUNK_SDK = True
except ImportError:
    HAVE_SPLUNK_SDK = False


class SplunkRestConf(object):
    def __init__(self, module):
        self.module = module

    def connectUri(self, uri, username, password, token=None, owner=None, app=None, sharing=None):
        from urlparse import urlparse
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
            self.module.fail_json(msg="Failure connecting to Splunkd:  splunklib.client.connect() returned None.")
        self.service = service

    def getToken(self):
        return self.service.token

    '''
    def filterDictKeys(self, d):
        """
        Remove Splunk internal 'eai:*' keys from a dictionary to allow round
        trips between "list" and "present" (update) calls.
        """
    '''

    def contentEquals(self, baseline, update):
        """
        Compare to 'content' dictionaries.  No need to do a full comparison,
        we only need to know if there's anything different in update.  Keys
        that are unique to baseline don't matter since they will not be
        updated.

        TODO:  Add support for boolean comparison.  The "disabled" key is
        easy, the others will be more complicated.  (Of course the simplest
        solution is to teach the users to use the canonical names for boolean
        values.)
        """
        for (key, value) in update.iteritems():
            if key not in baseline:
                return False
            if str(baseline[key]) != str(value):
                return False
        return True
    
    def applySettings(self, confName, stanzaName, settings, defaults=None, del_unknown=False):
        """
        Create or update a record
        """
        if del_unknown:
            output["failed"] = True
            output["msg"] = "The 'del_unknown' functionality hasn't been implemented yet!"
            return
        stanza_dict = {}
        output = {}
        created = False
        do_update = False

        # Attempt to fetch existing entry, or create a new one
        try:
            stanza = self.service.confs[confName][stanzaName]
        except KeyError:
            stanza = self.service.confs[confName].create(stanzaName)
            created = True

        # Determine if settings need to be updated
        if created:
            output["result"] = "created"
            # Only apply defaults when creating a new stanza
            if defaults:
                stanza_dict.update(defaults)
            stanza_dict.update(settings)
            init_content = {}
        else:
            output["result"] = "updated"
            stanza_dict = settings
            init_content = dict(stanza.content)
            if not self.contentEquals(init_content, stanza_dict):
                do_update = True

        if created or do_update:
            # Update local entity (I think)
            stanza.submit(stanza_dict)
            # Send updates to splunkd
            stanza.update()
            # Refresh my local copy based on what the server accepted
            stanza.refresh()

        #output["stanza_dict"] = stanza_dict          #DEBUGGING
        output["content"] = dict(stanza.content)
        #output["content_inital"] = init_content     # For debugging
        output["changed"] = created or do_update    # Or is it better to do a before/after comparison?
        #output["changed_dictdiff"] = init_content != output["content"]      # DEBUGGING
        output["endpoint"] = str(stanza.links['edit'])
        return output


    def listSettings(self, confName, stanzaName):
        """
        Return an existing configuration record
        """
        output = {}
        try:
            stanza = self.service.confs[confName][stanzaName]
            output["result"] = "present"
        except KeyError:
            output["result"] = "missing"
            output["msg"] = "Unable to find [%s] in %s.conf" % (stanzaName, confName)
            output["failed"] = True
            return output
        output["content"] = dict(stanza.content)
        output["endpoint"] = str(stanza.links['list'])
        return output


    def deleteSettings(self, confName, stanzaName):
        """
        Remove an existing configuration record, if it exists.
        """
        output = {}
        try:
            stanza = self.service.confs[confName][stanzaName]
            # May be informative to the caller (possibly a "move" use-case)
            output["content"] = dict(stanza.content)
            output["result"] = "deleted"
            try:
                stanza.delete()
            except Exception, e:
                output["failed"] = True
                output["msg"] = "Unable to delete [%] in %s.conf.  "\
                                " Exception:  %s" % (stanzaName, confName, e)
            output["changed"] = True
        except KeyError:
            output["result"] = "missing"
            output["changed"] = False
            # Empty content - For output consistency
            output["content"] = {}
        return output



def main():
    module = AnsibleModule(
        argument_spec = dict(
            # Splunkd endpoint and authentication
            splunkd_uri = dict(default="https://localhost:8089", aliases=["uri"]),
            username    = dict(default=None),
            password    = dict(default=None, no_log=True),
            token       = dict(default=None, no_log=True),
            # Conf settings change
            state       = dict(default='present',
                               choices=['present', 'absent', 'list']),
            conf        = dict(required=True, choices=CONF_CHOICES), 
            stanza      = dict(required=True, aliases=["name"]),
            del_unknown = dict(default='false', choices=BOOLEANS),
            # settings are required when state=present.
            settings    = dict(type='dict', default={}),
            defaults    = dict(type='dict', default={}),
            # Splunk namespace options
            owner       = dict(default=None),
            app         = dict(default=None),
            sharing     = dict(default="global",
                               choices=["user", "app", "global", "system"])
        )
    )

    # Outputs
    #   result:     created, updated (merge), deleted
    #   
    #   content:    The dictionary containing the values
    #   token:      Splunk auth token (for subsequent call?)     - To do
    if not HAVE_SPLUNK_SDK:
        module.fail_json(msg='splunk-sdk required for this module')

    srConf = SplunkRestConf(module)
    p = module.params

    if not ((p["username"] and p["password"]) or p["token"]):
        module.fail_json(msg="%s requires either (1) 'username' and 'password' parameters, "
                             "or (2) token parameter for Splunkd authentication" % (MODULE_NAME,))

    try:
        srConf.connectUri(p['splunkd_uri'], p['username'], 
                          p['password'], p['token'],
                          p["owner"], p["app"], p["sharing"])
    except Exception, e:
        module.fail_json(msg="Unable to connect to splunkd.  Exception: %s" % e)

    if p["state"] == "present":
        if not p["settings"]:
            module.fail_json(msg="Parameter 'settings' is required for state=present.")
        output = srConf.applySettings(p['conf'], p['stanza'],
                                      p['settings'], p['defaults'])
    elif p["state"] == "absent":
        output = srConf.deleteSettings(p['conf'], p['stanza'])
    elif p["state"] == "list":
        output = srConf.listSettings(p['conf'], p['stanza'])
    else:
        module.fail_json(msg="Unsupported state of '%s'" % p["state"])

    # For convenience, pass along some of the input parameters
    output["conf"]   = p["conf"]
    output["stanza"] = p["stanza"]
    # Add auth 'token' which can be used for subsequent calls in the same play.
    output["token"]  = srConf.getToken()
    # DEBUG, or is this worth keeping?
    output["params"] = p
    module.exit_json(**output)

# import module snippets
from ansible.module_utils.basic import *

main()
