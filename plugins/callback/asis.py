# Heavily "borrowed" from the 'ansible.builtin.minimal' callback handler
# (c) 2023 Lowell Alleman <lowell.alleman@cdillc.com>
# (c) 2012-2014, Michael DeHaan <michael.dehaan@gmail.com>
# (c) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)


from __future__ import absolute_import, division, print_function

from ansible import constants as C
from ansible.plugins.callback import CallbackBase


__metaclass__ = type

DOCUMENTATION = '''
    name: asis
    type: stdout
    short_description: As-is Ansible screen output
    version_added: v0.19.4
    description:
        - This output callback will simply dump the values of C(stdout), C(stderr), and C(msg) fields to the screen, as is.
'''


class CallbackModule(CallbackBase):

    '''
    This is the most minimal callback interface ever, which simply dumps the contents
    of 'stdout', 'stderr', and 'msg' to stdout "AS IS".
    '''

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'stdout'
    CALLBACK_NAME = 'asis'

    def _command_generic_msg(self, host, result, caption):
        ''' output the result of a command run '''
        # TODO:  Add some kind of indentation here (defaults to 4 elsewhere)
        buf = ["%s | %s | rc=%s >>\n" % (host, caption, result.get('rc', -1))]

        def add(s):
            if isinstance(s, (list, tuple)):
                buf.append("\n".join(str(i) for i in s) + "\n")
                return
            s = str(s)
            buf.append(s)
            if s and isinstance(s, str) and not s.endswith("\n"):
                buf.append("\n")

        add(result.get('stdout', ''))
        add(result.get('stderr', ''))
        add(result.get('msg', ''))
        return "".join(buf)

    def v2_runner_on_failed(self, result, ignore_errors=False):

        self._handle_exception(result._result)
        self._handle_warnings(result._result)

        if result._task.action in C.MODULE_NO_JSON and 'module_stderr' not in result._result:
            self._display.display(self._command_generic_msg(result._host.get_name(),
                                                            result._result, "FAILED"),
                                  color=C.COLOR_ERROR)
        else:
            self._display.display("%s | FAILED! => %s" % (result._host.get_name(),
                                                          self._dump_results(result._result, indent=4)),
                                  color=C.COLOR_ERROR)

    def v2_runner_on_ok(self, result):
        self._clean_results(result._result, result._task.action)

        self._handle_warnings(result._result)

        # self._display.display(f"{result._host.get_name()}\n{result._result.get('stdout')}")
        if result._result.get('changed', False):
            color = C.COLOR_CHANGED
            state = 'CHANGED'
        else:
            color = C.COLOR_OK
            state = 'SUCCESS'

        priority_msg = result._result.get("priority_msg", "")
        if result._result.get("no_log", None):
            # Not sure how to check if "no_log" was set on the module paramaters....
            pass
        elif priority_msg:
            self._display.display(priority_msg, color=color)
        else:
            self._display.display(self._command_generic_msg(result._host.get_name(),
                                                            result._result, state),
                                  color=color)

        '''
        if result._task.action in C.MODULE_NO_JSON and 'ansible_job_id' not in result._result:
            self._display.display(self._command_generic_msg(result._host.get_name(), result._result, state), color=color)
        else:
            self._display.display("%s | %s => %s" % (result._host.get_name(), state, self._dump_results(result._result, indent=4)), color=color)
        '''

    def v2_runner_on_skipped(self, result):
        self._display.display("%s | SKIPPED" % (result._host.get_name()), color=C.COLOR_SKIP)

    def v2_runner_on_unreachable(self, result):
        self._display.display("%s | UNREACHABLE! => %s" % (result._host.get_name(
        ), self._dump_results(result._result, indent=4)), color=C.COLOR_UNREACHABLE)

    def v2_on_file_diff(self, result):
        if 'diff' in result._result and result._result['diff']:
            self._display.display(self._get_diff(result._result['diff']))
