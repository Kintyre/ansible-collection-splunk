from __future__ import absolute_import, division, print_function


__metaclass__ = type

import os

from ansible.errors import AnsibleAction, AnsibleActionFail, AnsibleActionSkip, AnsibleError
from ansible.module_utils._text import to_text
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.plugins.action import ActionBase


class ActionModule(ActionBase):

    TRANSFERS_FILES = True

    def run(self, tmp=None, task_vars=None):
        ''' handler for app side-load operation '''
        if task_vars is None:
            task_vars = dict()

        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

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

            # This is way to limited....
            # TODO:  Replace this with some kind of remote state file fetch
            try:
                remote_stat = self._execute_remote_stat(dest, all_vars=task_vars, follow=True)
            except AnsibleError as e:
                raise AnsibleActionFail(to_text(e))

            if not remote_stat['exists'] or not remote_stat['isdir']:
                raise AnsibleActionFail("dest '%s' must be an existing dir" % dest)

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
        except AnsibleAction as e:
            result.update(e.result)
        finally:
            self._remove_tmp_path(self._connection._shell.tmpdir)
        return result
