from __future__ import absolute_import, division, print_function
import json


__metaclass__ = type

import os

from tempfile import NamedTemporaryFile
from ansible.errors import AnsibleAction, AnsibleActionFail, AnsibleActionSkip, AnsibleError
from ansible.module_utils._text import to_text
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.plugins.action import ActionBase
from ansible.utils.display import Display


display = Display()

from ansible_collections.lowell80.splunk.plugins.module_utils.ksconf_shared import \
    get_app_info_from_spl, SIDELOAD_STATE_FILE

class ActionModule(ActionBase):

    TRANSFERS_FILES = True

    def parse_remote_json_file(self, path):
        try:
            display.vvv(u"JSON state  file={0}".format(path))
            with NamedTemporaryFile("rb+") as temp_f:
                self._connection.fetch_file(path, temp_f.name)
                temp_f.seek(0)
                data = json.load(temp_f)
                display.vvv(u"JSON state  file={0} data={1!r}".format(path, data))
                return data

        # TODO: Capture file not found exception and return `None`
        except Exception as e:
            display.vvv(u"JSON state  file={0} Exception={1}".format(path, to_text(e)))
            raise e

    def run(self, tmp=None, task_vars=None):
        ''' handler for app side-load operation '''
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        # TODO: Check ksconf version on the control node (can't use check_ksconf_version() which needs a module)

        # Uses 'unarchive' like args
        source = self._task.args.get('src', None)
        dest = self._task.args.get('dest', None)
        decrypt = self._task.args.get('decrypt', True)

        try:
            if source is None or dest is None:
                raise AnsibleActionFail("src (or content) and dest are required")

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
                    raise AnsibleActionFail("Tarball must contain exactly one app.  Found {}".format(app_names))
                app_name = app_names.pop()
                state_file = os.path.join(dest, app_name, SIDELOAD_STATE_FILE)
                hash = extras["hash"]

                try:
                    state = self.parse_remote_json_file(state_file)
                    remote_hash = state["src_hash"]

                    changed = hash != remote_hash
                except AnsibleError as e:
                    raise AnsibleActionFail(to_text(e))

            except Exception as e:
                changed = True
                # Re rase for now .... track down better exception class!
                raise AnsibleActionFail(to_text(e))

            if changed:

                # transfer the file to a remote tmp location
                tmp_src = self._connection._shell.join_path(self._connection._shell.tmpdir, 'source')
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

                # execute the actual module now, with the updated args
                result.update(self._execute_module(module_name="lowell80.splunk.ksconf_app_sideload",
                                                   module_args=new_module_args,
                                                   task_vars=task_vars))
            else:
                result["changed"] = False

        except AnsibleAction as e:
            result.update(e.result)
        finally:
            self._remove_tmp_path(self._connection._shell.tmpdir)
        return result
