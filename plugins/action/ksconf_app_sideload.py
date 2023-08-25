# -*- coding: utf-8 -*-
#
# ACTION:  (This runs on the controller!)
#

from __future__ import absolute_import, division, print_function

import json
from typing import Tuple

from ansible_collections.cdillc.splunk.plugins.module_utils.ksconf_shared import (
    SIDELOAD_STATE_FILE, check_ksconf_version)


__metaclass__ = type

import os
from base64 import b64decode
from tempfile import NamedTemporaryFile

from ansible.errors import AnsibleAction, AnsibleActionFail, AnsibleError
from ansible.module_utils._text import to_text
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ksconf.app.manifest import AppArchiveContentError, AppManifest, load_manifest_for_archive


display = Display()


class ActionModule(ActionBase):

    TRANSFERS_FILES = True

    def parse_remote_json_file(self, path, task_vars):
        """
        Fetch remote state file (.json) to determine if the app has changed
        since last deployment.

        The remote json file must be copied to a temporary named file to be
        parsed locally.
        """
        display.vvv(f"JSON state file={path}")
        with NamedTemporaryFile("rb+") as temp_f:
            try:
                self._connection.fetch_file(path, temp_f.name)
            except AnsibleError as e:
                # Sometimes this logic results in incorrect, but ignorable message on the first
                # deploy when running with a single verbose ('-v') mode.
                #  1:  Could not find file on the Ansible Controller.
                #  2:  If you are using a module and expect the file to exist on the remote, see the remote_src option
                # Maybe there's a way to clean that up?  Possibly by calling _execute_remote_stat() first???

                # Try the legacy 'slurp' module.  This technique is borrowed from the builtin fetch
                # action when "permissions are lacking or privilege escalation is needed"
                slurp_res = self._execute_module(module_name='ansible.legacy.slurp',
                                                 module_args=dict(src=path),
                                                 task_vars=task_vars)
                slurp_msg = to_text(slurp_res.get("msg", ""))
                if slurp_res.get('failed') or slurp_msg:
                    if slurp_msg.startswith("file not found:"):
                        # No need to show a message
                        return {}
                    display.vv("Failed to fetch JSON state using slurp.  "
                               f"file={path} msg={slurp_msg} first_exception={e}")
                    return {}
                else:
                    display.v(f"Found JSON state file={path} using slurp!")

                    if slurp_res['encoding'] == 'base64':
                        temp_f.write(b64decode(slurp_res['content']))

            temp_f.seek(0)
            data = json.load(temp_f)

            # Stupid dump of state data
            d = data
            if display.verbosity >= 3:
                d = d.copy()
                if "manifest" in data:
                    d["manifest"] = d["manifest"].copy()
                    d["manifest"]["files"] = f"Total of {len(data['manifest']['files'])} files ...."
            display.vvv(f"JSON state file={path} data={d!r}")

            return data

    def fetch_remote_manifest(self, state_file, task_vars) -> Tuple[AppManifest, dict]:
        try:
            data = self.parse_remote_json_file(state_file, task_vars)
            if "manifest" not in data:
                # Possible upgrade scenario.  Nothing we can do but fresh install
                return None, data
            return AppManifest.from_dict(data.pop("manifest")), data
        except json.decoder.JSONDecodeError as e:
            display.warning(f"Remote JSON state file {state_file} is corrupt.  "
                            f"App will be replaced.  {e}")
            return None, None

    def run(self, tmp=None, task_vars=None):
        ''' handler for app side-load operation '''
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        ksconf_version = check_ksconf_version()
        if ksconf_version < (0, 11):
            return {'failed': True,
                    'msg': f"ksconf version>=0.11 is required.  Found {ksconf_version}"}

        # Uses 'unarchive' like args
        source = src = self._task.args.get('src', None)
        dest = self._task.args.get('dest', None)
        decrypt = self._task.args.get('decrypt', True)
        list_files = self._task.args.get('list_files', False)

        changed = True
        try:

            if source is None or dest is None:
                raise AnsibleActionFail("src and dest are required")

            dest = self._remote_expand_user(dest)
            source = os.path.expanduser(source)

            try:
                # Q: Do we really want loose path finding behavior of _find_needle()?
                #    It seems like the path should be typically known.
                real_source = self._find_needle('files', source)
                source = self._loader.get_real_file(real_source, decrypt=decrypt)

                # Copy file timestamp as manifest process checks for mtime changes
                stat = os.stat(real_source)
                os.utime(source, (stat.st_atime, stat.st_mtime))

            except AnsibleError as e:
                raise AnsibleActionFail(to_text(e))

            # Get hash of local archive.  This is cached between runs to reduce overhead.
            try:
                # This requires writing to the controller's filesystem along side `source`
                # Source should be relative to the real file (not the temporary decrypted one)
                app_manifest = load_manifest_for_archive(source, permanent_archive=real_source)
            except AppArchiveContentError as e:
                raise AnsibleActionFail(f"Unable to process tarball {source} due to {e}")

            try:
                '''
                extras = {
                    "local_files": list(app_manifest.find_local()),
                    "file_count": len(app_manifest.files),
                }
                '''
                # Pull back remote sideload state data, if present
                # TODO: Check ansible facts first (Does this need an override parameter to skip?)
                state_file = os.path.join(dest, app_manifest.name, SIDELOAD_STATE_FILE)
                remote_manifest, remote_state = self.fetch_remote_manifest(state_file, task_vars)

                if remote_manifest and app_manifest.hash == remote_manifest.hash:
                    changed = False

            except AnsibleActionFail:
                raise

            except Exception as e:
                changed = True
                display.v("Exception while trying to grab remote app deployment state.   "
                          "Exception: {0}".format(to_text(e)))
                raise AnsibleActionFail(to_text(e))

            if changed:
                # transfer the file to a remote tmp location
                tmp_src = self._connection._shell.join_path(
                    self._connection._shell.tmpdir, 'source')
                self._transfer_file(source, tmp_src)

                # handle diff mode client side
                # handle check mode client side

                # remove action plugin only keys
                new_module_args = self._task.args.copy()
                for key in ('decrypt',):
                    if key in new_module_args:
                        del new_module_args[key]

                # fix file permissions when the copy is done as a different user
                self._fixup_perms2((self._connection._shell.tmpdir, tmp_src))
                new_module_args['src'] = tmp_src

                # Pass the original 'src' field over to the module (for logging)
                new_module_args['src_orig'] = src

                # execute the actual module now, with the updated args
                result.update(self._execute_module(module_name="cdillc.splunk.ksconf_app_sideload",
                                                   module_args=new_module_args,
                                                   task_vars=task_vars))
            else:
                # Simulate the output of the ksconf_app_sideload module
                result["changed"] = False
                result["state_file"] = state_file
                result["hash"] = remote_manifest.hash
                result["installed_at"] = remote_state.get("installed_at", None)
                result["app_info"] = {
                    "name": remote_manifest.name,
                    "deprecated": "NOTE 'app_info' is going away, use 'app_facts' instead!"}
                result["app_facts"] = {"name": remote_manifest.name}

                # Note that this version does NOT include directories.
                # (Not sure why we care; I suppose we are trying to match the 'list_files' behavior of the builtin unarchive module.)
                if list_files:
                    result["files"] = [os.fspath(f.path) for f in remote_manifest.files]

        except AnsibleAction as e:
            result.update(e.result)
        finally:
            self._remove_tmp_path(self._connection._shell.tmpdir)
        return result
