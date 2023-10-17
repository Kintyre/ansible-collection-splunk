# -*- coding: utf-8 -*-
#
# ACTION:  (This runs on the controller!)
#

from __future__ import absolute_import, division, print_function

from typing import Tuple

from ansible_collections.cdillc.splunk.plugins.module_utils.ksconf_shared import (
    SIDELOAD_STATE_FILE, check_ksconf_version)


__metaclass__ = type

import os

from ansible.errors import AnsibleAction, AnsibleActionFail, AnsibleError
from ansible.module_utils._text import to_text
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display
from ksconf.app.manifest import AppArchiveContentError, AppManifest, load_manifest_for_archive


display = Display()


class ActionModule(ActionBase):

    TRANSFERS_FILES = True

    def fetch_remote_manifest(self, app_dir, task_vars, *,
                              state_file=None,
                              rebuild_manifest=True
                              ) -> Tuple[AppManifest, dict]:
        res = self._execute_module(module_name='cdillc.splunk.ksconf_app_manifest',
                                   module_args=dict(app_dir=app_dir,
                                                    state_file=state_file,
                                                    rebuild_manifest=rebuild_manifest),
                                   task_vars=task_vars)
        manifest = state = None
        if "manifest" in res:
            manifest = res.pop("manifest")
        if "state" in res:
            state = res.pop("state")
        if manifest:
            manifest = AppManifest.from_dict(manifest)
        return manifest, state, res

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
        state_file = self._task.args.get("state_file", None)
        recreate_manifest = boolean(self._task.args.get("recreate_manifest", True))
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
                app_dir = os.path.join(dest, app_manifest.name)
                if state_file:
                    state_file = os.path.join(app_dir, state_file)
                else:
                    state_file = os.path.join(app_dir, SIDELOAD_STATE_FILE)

                remote_manifest, remote_state, kam_res = self.fetch_remote_manifest(
                    app_dir, task_vars,
                    state_file=state_file,
                    rebuild_manifest=recreate_manifest)

                result["ksconf_app_manifest_output"] = kam_res

                if remote_manifest:
                    display.vvv(f"fCheck  {app_manifest.hash} == {remote_manifest.hash}")

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
                for key in ('decrypt', 'recreate_manifest'):
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

                if "manifest_msg" in result and "result" in kam_res and kam_res["result"] != "loaded":
                    result["manifest_msg"] += f" after manifest was {kam_res['result']}"

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
                # Trying to match the 'list_files' behavior of the builtin unarchive module.)
                if list_files:
                    result["files"] = [os.fspath(f.path) for f in remote_manifest.files]

        except AnsibleAction as e:
            result.update(e.result)
        finally:
            self._remove_tmp_path(self._connection._shell.tmpdir)
        return result
