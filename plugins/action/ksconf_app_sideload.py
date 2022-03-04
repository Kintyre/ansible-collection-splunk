from __future__ import absolute_import, division, print_function

import json

from ansible_collections.lowell80.splunk.plugins.module_utils.ksconf_shared import (
    SIDELOAD_STATE_FILE, get_app_info_from_spl)


__metaclass__ = type

import os
from tempfile import NamedTemporaryFile

from ansible.errors import AnsibleAction, AnsibleActionFail, AnsibleActionSkip, AnsibleError
from ansible.module_utils._text import to_text
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display


display = Display()


class ActionModule(ActionBase):

    TRANSFERS_FILES = True

    def parse_remote_json_file(self, path):
        display.vvv(u"JSON state  file={0}".format(path))
        with NamedTemporaryFile("rb+") as temp_f:
            try:
                self._connection.fetch_file(path, temp_f.name)
            except AnsibleError as e:
                # Q:  Can we confirm that e contains "No such file or directory"? Is there a clean way?
                display.v(u"Missing JSON state file={0} exception={1}".format(path, to_text(e)))
                return {}
            temp_f.seek(0)
            data = json.load(temp_f)
            display.vvv(u"JSON state  file={0} data={1!r}".format(path, data))
            return data

    def run(self, tmp=None, task_vars=None):
        ''' handler for app side-load operation '''
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        # TODO: Check ksconf version on the control node (can't use check_ksconf_version() which needs a module)

        # Uses 'unarchive' like args
        source = src = self._task.args.get('src', None)
        dest = self._task.args.get('dest', None)
        decrypt = self._task.args.get('decrypt', True)

        try:
            if source is None or dest is None:
                raise AnsibleActionFail("src and dest are required")

            '''
            if creates:
                # do not run the command if the line contains creates=filename
                # and the filename already exists. This allows idempotence
                # of command executions.
                creates = self._remote_expand_user(creates)
                if self._remote_file_exists(creates):
                    raise AnsibleActionSkip("skipped, since %s exists" % creates)
            '''

            dest = self._remote_expand_user(dest)
            source = os.path.expanduser(source)

            try:
                source = self._loader.get_real_file(self._find_needle('files', source),
                                                    decrypt=decrypt)
            except AnsibleError as e:
                raise AnsibleActionFail(to_text(e))

            try:
                app_names, _, extras = get_app_info_from_spl(source, calc_hash=True)
                if len(app_names) != 1:
                    raise AnsibleActionFail("Tarball must contain exactly one app.  "
                                            "Found {0}:  {1}".format(len(app_names), app_names))
                app_name = app_names.pop()

                # Load state file, if present
                state_file = os.path.join(dest, app_name, SIDELOAD_STATE_FILE)
                hash = extras["hash"]
                try:
                    state = self.parse_remote_json_file(state_file)
                    remote_hash = state.get("src_hash", None)
                    if remote_hash:
                        changed = hash != remote_hash
                    else:
                        changed = True
                except AnsibleError as e:
                    # This shouldn't be possible any more....
                    raise AnsibleActionFail(to_text(e))
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
                result.update(self._execute_module(module_name="lowell80.splunk.ksconf_app_sideload",
                                                   module_args=new_module_args,
                                                   task_vars=task_vars))
            else:
                # TODO:  If list_files is set, we could (eventually) capture that from the state file (not yet present)
                result["changed"] = False

        except AnsibleAction as e:
            result.update(e.result)
        finally:
            self._remove_tmp_path(self._connection._shell.tmpdir)
        return result
