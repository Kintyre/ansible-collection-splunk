# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import codecs
import fnmatch
import os

from ansible.module_utils._text import to_bytes, to_native, to_text
from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.common.locale import get_best_parsable_locale
from ansible.module_utils.common.process import get_bin_path
# Module version
# from ansible.module_utils.ksconf_shared import check_ksconf_version
# Collection version
from ansible_collections.lowell80.splunk.plugins.module_utils.ksconf_shared import \
    check_ksconf_version, get_app_info_from_spl, SIDELOAD_STATE_FILE


__metaclass__ = type


DOCUMENTATION = r'''
---
module: ksconf_app_sideload
short_description: Unpacks a Splunk app archive after copying it from the local machine
version_added: '0.10.0'
author: Lowell C. Alleman (@lowell80)
description:
     - By default, it will copy the source file from the local system to the target before unpacking.
     - For Windows targets, switch to Linux.
options:
  src:
    description:
      - Local path to Splunk archive file to copy to the target server; can be absolute or relative.
    type: path
    required: true
  dest:
    description:
      - Remote absolute path where the archive should be unpacked.
      - Typically this will be C(/opt/splunk/etc/apps) or a management folder like C(deployment-apps), C(slave-apps), or C(shcluster/apps).
    type: path
    required: true
  io_buffer_size:
    description:
      - Size of the volatile memory buffer that is used for extracting files from the archive in bytes.
    type: int
    default: 64 KiB
  list_files:
    description:
      - If set to True, return the list of files that are contained in the tarball.
    type: bool
    default: no
    version_added: "2.0"
#  exclude:
#    description:
#      - List the directory and file entries that you would like to exclude from the unarchive action.
#      - Mutually exclusive with C(include).
#    type: list
#    default: []
#    elements: str
#    version_added: "2.1"
#  include:
#    description:
#      - List of directory and file entries that you would like to extract from the archive. If C(include)
#        is not empty, only files listed here will be extracted.
#      - Mutually exclusive with C(exclude).
#    type: list
#    default: []
#    elements: str
#    version_added: "2.11"

extends_documentation_fragment:
- action_common_attributes
- action_common_attributes.flow
- action_common_attributes.files
- decrypt
- files
attributes:
    action:
      support: full
    async:
      support: none
    bypass_host_loop:
      support: none
    check_mode:
      support: full
#    diff_mode:
#      support: partial
#      details: Uses gtar's C(--diff) arg to calculate if changed or not. If this C(arg) is not supported, it will always unpack the archive.
    platform:
      platforms: posix
    safe_file_operations:
      support: none
    vault:
      support: full
notes:
#    - Requires ksconf package on target host.
    - Can handle I(.tgz), I(.tar.gz), I(.spl), and I(.zip) files.
    - Note that B(only) files are extracted.  This means empty directories will not be created.  Open a bug report if this cause an issue for you and describe the use case.
#    - Existing files/directories in the destination which are not in the archive
#      are not touched. This is the same behavior as a normal archive extraction.

'''


"""
EXAMPLES = r'''
- name: Extract foo.tgz into /var/lib/foo
  ansible.builtin.unarchive:
    src: foo.tgz
    dest: /var/lib/foo

- name: Unarchive a file that is already on the remote machine
  ansible.builtin.unarchive:
    src: /tmp/foo.zip
    dest: /usr/local/bin
    remote_src: yes

- name: Unarchive a file that needs to be downloaded (added in 2.0)
  ansible.builtin.unarchive:
    src: https://example.com/example.zip
    dest: /usr/local/bin
    remote_src: yes

- name: Unarchive a file with extra options
  ansible.builtin.unarchive:
    src: /tmp/foo.zip
    dest: /usr/local/bin
    extra_opts:
    - --transform
    - s/^xxx/yyy/
'''

RETURN = r'''
dest:
  description: Path to the destination directory.
  returned: always
  type: str
  sample: /opt/software
files:
  description: List of all the files in the archive.
  returned: When I(list_files) is True
  type: list
  sample: '["file1", "file2"]'
gid:
  description: Numerical ID of the group that owns the destination directory.
  returned: always
  type: int
  sample: 1000
group:
  description: Name of the group that owns the destination directory.
  returned: always
  type: str
  sample: "librarians"
handler:
  description: Archive software handler used to extract and decompress the archive.
  returned: always
  type: str
  sample: "TgzArchive"
mode:
  description: String that represents the octal permissions of the destination directory.
  returned: always
  type: str
  sample: "0755"
owner:
  description: Name of the user that owns the destination directory.
  returned: always
  type: str
  sample: "paul"
size:
  description: The size of destination directory in bytes. Does not include the size of files or subdirectories contained within.
  returned: always
  type: int
  sample: 36
src:
  description:
    - The source archive's path.
    - If I(src) was a remote web URL, or from the local ansible controller, this shows the temporary location where the download was stored.
  returned: always
  type: str
  sample: "/home/paul/test.tar.gz"
state:
  description: State of the destination. Effectively always "directory".
  returned: always
  type: str
  sample: "directory"
uid:
  description: Numerical ID of the user that owns the destination directory.
  returned: always
  type: int
  sample: 1000
'''
"""


class UnarchiveError(Exception):
    pass


class TgzArchive(object):

    def __init__(self, src, b_dest, file_args, module):
        self.src = src
        self.b_dest = b_dest
        self.file_args = file_args
        self.opts = module.params['extra_opts']
        self.module = module
        if self.module.check_mode:
            self.module.exit_json(
                skipped=True, msg="remote module (%s) does not support check mode when using gtar" % self.module._name)
        self.excludes = [path.rstrip('/') for path in self.module.params['exclude']]
        self.include_files = self.module.params['include']
        self.cmd_path = None
        self.tar_type = None
        self.zipflag = '-z'
        self._files_in_archive = []

    def _get_tar_type(self):
        cmd = [self.cmd_path, '--version']
        (rc, out, err) = self.module.run_command(cmd)
        tar_type = None
        if out.startswith('bsdtar'):
            tar_type = 'bsd'
        elif out.startswith('tar') and 'GNU' in out:
            tar_type = 'gnu'
        return tar_type

    @property
    def files_in_archive(self):
        if self._files_in_archive:
            return self._files_in_archive

        cmd = [self.cmd_path, '--list', '-C', self.b_dest]
        if self.zipflag:
            cmd.append(self.zipflag)
        if self.opts:
            cmd.extend(['--show-transformed-names'] + self.opts)
        if self.excludes:
            cmd.extend(['--exclude=' + f for f in self.excludes])
        cmd.extend(['-f', self.src])
        if self.include_files:
            cmd.extend(self.include_files)

        locale = get_best_parsable_locale(self.module)
        rc, out, err = self.module.run_command(cmd, cwd=self.b_dest, environ_update=dict(
            LANG=locale, LC_ALL=locale, LC_MESSAGES=locale, LANGUAGE=locale))
        if rc != 0:
            raise UnarchiveError('Unable to list files in the archive: %s' % err)

        for filename in out.splitlines():
            # Compensate for locale-related problems in gtar output (octal unicode representation) #11348
            # filename = filename.decode('string_escape')
            filename = to_native(codecs.escape_decode(filename)[0])

            # We don't allow absolute filenames.  If the user wants to unarchive rooted in "/"
            # they need to use "dest: '/'".  This follows the defaults for gtar, pax, etc.
            # Allowing absolute filenames here also causes bugs: https://github.com/ansible/ansible/issues/21397
            if filename.startswith('/'):
                filename = filename[1:]

            exclude_flag = False
            if self.excludes:
                for exclude in self.excludes:
                    if fnmatch.fnmatch(filename, exclude):
                        exclude_flag = True
                        break

            if not exclude_flag:
                self._files_in_archive.append(to_native(filename))

        return self._files_in_archive

    def is_unarchived(self):
        cmd = [self.cmd_path, '--diff', '-C', self.b_dest]
        if self.zipflag:
            cmd.append(self.zipflag)
        if self.opts:
            cmd.extend(['--show-transformed-names'] + self.opts)
        if self.file_args['owner']:
            cmd.append('--owner=' + quote(self.file_args['owner']))
        if self.file_args['group']:
            cmd.append('--group=' + quote(self.file_args['group']))
        if self.module.params['keep_newer']:
            cmd.append('--keep-newer-files')
        if self.excludes:
            cmd.extend(['--exclude=' + f for f in self.excludes])
        cmd.extend(['-f', self.src])
        if self.include_files:
            cmd.extend(self.include_files)
        locale = get_best_parsable_locale(self.module)
        rc, out, err = self.module.run_command(cmd, cwd=self.b_dest, environ_update=dict(
            LANG=locale, LC_ALL=locale, LC_MESSAGES=locale, LANGUAGE=locale))

        # Check whether the differences are in something that we're
        # setting anyway

        # What is different
        unarchived = True
        old_out = out
        out = ''
        run_uid = os.getuid()
        # When unarchiving as a user, or when owner/group/mode is supplied --diff is insufficient
        # Only way to be sure is to check request with what is on disk (as we do for zip)
        # Leave this up to set_fs_attributes_if_different() instead of inducing a (false) change
        for line in old_out.splitlines() + err.splitlines():
            # FIXME: Remove the bogus lines from error-output as well !
            # Ignore bogus errors on empty filenames (when using --split-component)
            if EMPTY_FILE_RE.search(line):
                continue
            if run_uid == 0 and not self.file_args['owner'] and OWNER_DIFF_RE.search(line):
                out += line + '\n'
            if run_uid == 0 and not self.file_args['group'] and GROUP_DIFF_RE.search(line):
                out += line + '\n'
            if not self.file_args['mode'] and MODE_DIFF_RE.search(line):
                out += line + '\n'
            if MOD_TIME_DIFF_RE.search(line):
                out += line + '\n'
            if MISSING_FILE_RE.search(line):
                out += line + '\n'
            if INVALID_OWNER_RE.search(line):
                out += line + '\n'
            if INVALID_GROUP_RE.search(line):
                out += line + '\n'
        if out:
            unarchived = False
        return dict(unarchived=unarchived, rc=rc, out=out, err=err, cmd=cmd)

    def unarchive(self):
        cmd = [self.cmd_path, '--extract', '-C', self.b_dest]
        if self.zipflag:
            cmd.append(self.zipflag)
        if self.opts:
            cmd.extend(['--show-transformed-names'] + self.opts)
        if self.file_args['owner']:
            cmd.append('--owner=' + quote(self.file_args['owner']))
        if self.file_args['group']:
            cmd.append('--group=' + quote(self.file_args['group']))
        if self.module.params['keep_newer']:
            cmd.append('--keep-newer-files')
        if self.excludes:
            cmd.extend(['--exclude=' + f for f in self.excludes])
        cmd.extend(['-f', self.src])
        if self.include_files:
            cmd.extend(self.include_files)
        locale = get_best_parsable_locale(self.module)
        rc, out, err = self.module.run_command(cmd, cwd=self.b_dest, environ_update=dict(
            LANG=locale, LC_ALL=locale, LC_MESSAGES=locale, LANGUAGE=locale))
        return dict(cmd=cmd, rc=rc, out=out, err=err)

    def can_handle_archive(self):
        # Prefer gtar (GNU tar) as it supports the compression options -z, -j and -J
        try:
            self.cmd_path = get_bin_path('gtar')
        except ValueError:
            # Fallback to tar
            try:
                self.cmd_path = get_bin_path('tar')
            except ValueError:
                return False, "Unable to find required 'gtar' or 'tar' binary in the path"

        self.tar_type = self._get_tar_type()

        if self.tar_type != 'gnu':
            return False, 'Command "%s" detected as tar type %s. GNU tar required.' % (self.cmd_path, self.tar_type)

        try:
            if self.files_in_archive:
                return True, None
        except UnarchiveError as e:
            return False, 'Command "%s" could not handle archive: %s' % (self.cmd_path, to_native(e))
        # Errors and no files in archive assume that we weren't able to
        # properly unarchive it
        return False, 'Command "%s" found no files in archive. Empty archive files are not supported.' % self.cmd_path


class KsconfArchive(object):

    def can_handle_archive(self):
        try:
            import ksconf.archive
            del ksconf.archive
        except ImportError:
            return False, "Unable to import ksconf python package"


# Informative stanza, attributes combos from app.conf
APP_ATTRIBUTES = [
    ("ui", "label"),
    ("launcher", "author"),
    ("launcher", "version"),
]


def ksconf_sideload_app(src, dest, list_files=False):
    from ksconf.archive import extract_archive, sanity_checker
    from ksconf.util.file import dir_exists

    app_names, app_conf, extras = get_app_info_from_spl(src, calc_hash=True)
    if len(app_names) > 1:
        raise UnarchiveError("This module only supports extracting a single splunk app.  "
                             "Found {} apps named:  {}".format(len(app_names),
                                                               ", ".join(app_names)))
    app_name = app_names.pop()
    del app_names

    result = {
        "app_info": {
            "name": app_name},
    }
    hash_sig = result["hash"] = extras.pop("hash")
    # Preserve this?
    if extras:
        result["app_info"]["extras"] = extras
    for stanza, attribute in APP_ATTRIBUTES:
        value = app_conf.get(stanza, {}).get(attribute)
        result["app_info"][attribute] = value

    files = extract_archive(src)
    files = sanity_checker(files)    # Check for bad paths (absolute, or relative with "..")
    if list_files:
        result["files"] = file_list = []
    # gen_arch_file_remapper -- Optionally add this one if we need to remap output destination
    for f in files:
        full_path = os.path.join(dest, f.path)
        dir_exists(os.path.dirname(full_path))
        with open(full_path, "wb") as fp:
            fp.write(f.payload)
        os.chmod(full_path, f.mode)
        # TODO:  Set owner, SE linux attributes, .... inherited from `file` module.
        # TODO:  Preserve modification time?   Currently not part of the GenArchFile data structure
        if list_files:
            file_list.append(f.path)

    with open(os.path.join(dest, app_name, SIDELOAD_STATE_FILE), "w") as marker_f:
        data = {
            "src_path": src,
            "src_hash": hash_sig,
            # Todo: Add install timestamp
        }
        import json
        json.dump(data, marker_f)

    # Hard code this for now!
    result["changed"] = True
    return result


def main():
    module = AnsibleModule(
        argument_spec=dict(
            src=dict(type='path', required=True),
            dest=dict(type='path', required=True),
            list_files=dict(type='bool', default=False)
        ),
        add_file_common_args=True,
        # check-mode only works for zip files, we cover that later
        # supports_check_mode=True
    )

    ksconf_version = check_ksconf_version(module)
    if ksconf_version < (0, 9):
        module.warn("ksconf version {} is older than v0.9.  This may result in "
                    "unexpected behavior.  Please upgrade ksconf.".format(ksconf_version))

    src = module.params['src']
    dest = module.params['dest']
    list_files = module.params["list_files"]
    b_dest = to_bytes(dest, errors='surrogate_or_strict')
    file_args = module.load_file_common_arguments(module.params)

    # did tar file arrive?
    if not os.path.exists(src):
        module.fail_json(msg="Source '%s' failed to transfer" % src)
    if not os.access(src, os.R_OK):
        module.fail_json(msg="Source '%s' not readable" % src)

    # skip working with 0 size archives
    try:
        if os.path.getsize(src) == 0:
            module.fail_json(msg="Invalid archive '%s', the file is 0 bytes" % src)
    except Exception as e:
        module.fail_json(msg="Source '%s' not readable, %s" % (src, to_native(e)))

    # is dest OK to receive tar file?
    if not os.path.isdir(b_dest):
        module.fail_json(msg="Destination '%s' is not a directory" % dest)

    #  DO ACTUAL WORK HERE!
    # handler = pick_handler(src, b_dest, file_args, module)

    if module.check_mode:
        module.exit_json(msg="Check mode unsupported....  Please finish the implementation!")

    res_args = ksconf_sideload_app(src, dest, list_files)

    # do we need to do unpack?
    # check_results = handler.is_unarchived()

    # DEBUG
    # res_args['check_results'] = check_results

    '''
    if module.check_mode:
        res_args['changed'] = not check_results['unarchived']
    elif check_results['unarchived']:
        res_args['changed'] = False
    else:
        # do the unpack
        try:
            res_args['extract_results'] = handler.unarchive()
            if res_args['extract_results']['rc'] != 0:
                module.fail_json(msg="failed to unpack %s to %s" % (src, dest), **res_args)
        except IOError:
            module.fail_json(msg="failed to unpack %s to %s" % (src, dest), **res_args)
        else:
            res_args['changed'] = True
    # Get diff if required
    if check_results.get('diff', False):
        res_args['diff'] = {'prepared': check_results['diff']}


    # Run only if we found differences (idempotence) or diff was missing
    if res_args.get('diff', True) and not module.check_mode:
        # do we need to change perms?
        for filename in handler.files_in_archive:
            file_args['path'] = os.path.join(b_dest, to_bytes(filename, errors='surrogate_or_strict'))

            try:
                res_args['changed'] = module.set_fs_attributes_if_different(file_args, res_args['changed'], expand=False)
            except (IOError, OSError) as e:
                module.fail_json(msg="Unexpected error when accessing exploded file: %s" % to_native(e), **res_args)

    if module.params['list_files']:
        res_args['files'] = handler.files_in_archive
    '''

    module.exit_json(**res_args)


if __name__ == '__main__':
    main()
