# -*- coding: utf-8 -*-
#
# MODULE:  (This runs on the target node)
#
from __future__ import absolute_import, division, print_function

import json
import os
import time
from pathlib import Path

from ansible.module_utils._text import to_bytes, to_native
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.cdillc.splunk.plugins.module_utils.ksconf_shared import (
    SIDELOAD_STATE_FILE, __version__ as collection_version,
    check_ksconf_version)


# Import module_utils notes....   These have to be top-level imports due to how ansiballz ships
# required modules to the target node (no try/except fallbacks allowed here)
#
# Module version:       ansible.module_utils.ksconf_shared
# Collection version:   ansible_collections.cdillc.splunk.plugins.module_utils.ksconf_shared


__metaclass__ = type

ksconf_min_version = (0, 11)
ksconf_min_version_text = ".".join("{}".format(i) for i in ksconf_min_version)


DOCUMENTATION = r'''
---
module: ksconf_app_sideload
short_description: Unpacks a Splunk app archive after copying it from the local machine
version_added: '0.10.0'
author: Lowell C. Alleman (@lowell80)
description:
     - By default, it will copy the source file from the local system to the target before unpacking.
     - For Windows targets, switch to Linux.
requirements:
  - ksconf>={}

options:
  src:
    description:
      - Local path to Splunk archive file to copy to the target server; can be absolute or relative.
    type: path
    required: true
  dest:
    description:
      - Remote absolute path where the archive should be unpacked.
      - Typically this will be C(/opt/splunk/etc/apps) or a management folder like C(deployment-apps), C(manager-apps) (or C(master-apps) pre Splunk 9.0), or C(shcluster/apps).
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
    - Requires ksconf package on controller and target host.
    - Can handle I(.tgz), I(.tar.gz), I(.spl), and I(.zip) files.
    - Note that only B(files) are extracted.
      This means empty directories will not be created.
      If this cause an issue for you, open a bug report and describe your use case.
#    - Existing files/directories in the destination which are not in the archive
#      are not touched. This is the same behavior as a normal archive extraction.
'''.format(ksconf_min_version_text)


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
    - If I(src) was a remote web URL, or location local to the ansible controller.
  returned: always
  type: str
  sample: "/home/paul/test.tar.gz"
state:
  description: State of the destination. Effectively always "directory".
  returned: always
  type: str
  sample: "directory"
state_file:
  description: Relative path to the json state tracking file where installation state and source hash information is stored.
  returned: always
  type: str
  sample: fire_brigade/.ksconf_sideload.json
uid:
  description: Numerical ID of the user that owns the destination directory.
  returned: always
  type: int
  sample: 1000
'''
"""


def ksconf_sideload_app(src, dest, src_orig=None):
    from ksconf import __version__ as ksconf_version
    from ksconf.app import get_facts_manifest_from_archive
    from ksconf.app.deploy import DeployActionType, DeployApply as DeployApplyBase, DeploySequence
    from ksconf.app.manifest import AppManifest

    src = Path(src)
    dest = Path(dest)

    class DeployApply(DeployApplyBase):
        def resolve_source(self, source, hash):
            # For right now, we only are dealing with a *single* app, so just always return 'src'
            return src

    deployer = DeployApply(dest)

    app_facts, app_manifest = get_facts_manifest_from_archive(src, calculate_hash=True,
                                                              check_paths=True)

    # Correct 'source' field to match the filename on the controller node
    app_manifest.source = src_orig or os.fspath(src)

    result = {
        # For legacy reasons, we are keeping "app_info" (may drop this in favor of app_conf below)
        "app_info": {
            "name": app_facts.name,
            "author": app_facts.author,
            "version": app_facts.version,
            "deprecated": "NOTE 'app_info' is going away, use 'app_facts' instead!",
        },
        # This is the new output that should be used
        "app_facts": app_facts.to_tiny_dict("name", "author", "version"),
    }

    # state file
    app_dir: Path = dest / app_manifest.name
    state_file: Path = app_dir / SIDELOAD_STATE_FILE

    current_manifest = None
    if app_dir.is_dir():
        if state_file.is_file():
            try:
                data = json.loads(state_file.read_text())["manifest"]
                current_manifest = AppManifest.from_dict(data)
                del data
                manifest_msg = "manifest for transformational upgrade"
            except (IOError, KeyError, ValueError) as e:
                manifest_msg = f"manifest unusable due to {type(e)}: {e}"
        else:
            manifest_msg = "manifest missing"
    else:
        manifest_msg = "newly created manifest file (fresh app install)"

    if current_manifest is not None:
        # current_manifest.hash
        seq = DeploySequence.from_manifest_transformation(current_manifest, app_manifest)

        # Need some kind of context manager here that (1) locks manifest file, (2) Puts an in-progress marker in the manifest file so that we know the state is corrupted / interrupted.
        deployer.apply_sequence(seq)

    result["manifest_msg"] = manifest_msg

    # Don't rely on this to be stable.... more work to be done here.  Eventually want to report on what actually
    # happened, not just the deployment plan (sequence)
    result["files_changed"] = {}
    result["file_change_counts"] = {}
    for type_, actions in seq.actions_by_type.items():
        type_ = str(type_)
        result["file_change_counts"][type_] = actions
        '''
        if type_ in (DeployActionType.EXTRACT_FILE, DeployActionType.REMOVE_FILE):
            result["files_changed"][type_] = [action.path for action in actions]
        '''

    with open(state_file, "w") as marker_f:
        data = {
            "src_path": src_orig or src,
            "src_hash": app_manifest.hash,
            "ansible_module_version": collection_version,
            "ksconf_version": ksconf_version,
            "installed_at": time.time(),
            "manifest": app_manifest.to_dict(),
        }
        json.dump(data, marker_f, indent=1)

    file_list = [os.fspath(f.path) for f in app_manifest.files]
    file_list.append(os.fspath(state_file))

    # Hard code this for now!
    result["changed"] = True
    return result, file_list


def main():
    module = AnsibleModule(
        argument_spec=dict(
            src=dict(type='path', required=True),
            src_orig=dict(type="path", required=False),  # Internal (added by action)
            dest=dict(type='path', required=True),
            # show_manifest=dict(type=bool, default=False, alias="list_files")
            list_files=dict(type='bool', default=False)
        ),
        add_file_common_args=True,
        # supports_check_mode=True
    )

    ksconf_version = check_ksconf_version(module)
    if ksconf_version < ksconf_min_version:
        module.warn("ksconf version {} is older than v{}.  This may result in "
                    "unexpected behavior.  Please upgrade ksconf.".format(ksconf_version,
                                                                          ksconf_min_version_text))

    src = module.params['src']
    src_orig = module.params["src_orig"]
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

    if module.check_mode:
        module.exit_json(msg="Check mode unsupported....  Please finish the implementation!")

    res_args, files = ksconf_sideload_app(src, dest, src_orig=src_orig)

    if res_args.get('diff', True) and not module.check_mode:
        # do we need to change perms?
        # Reset permissions on all files (mode,owner,group,attr,se*)
        for filename in files:
            file_args['path'] = os.path.join(b_dest, to_bytes(
                filename, errors='surrogate_or_strict'))
            try:
                res_args['changed'] = module.set_fs_attributes_if_different(
                    file_args, res_args['changed'], expand=False)
            except (IOError, OSError) as e:
                module.fail_json(msg="Unexpected error when accessing file: %s"
                                 % to_native(e), **res_args)

    if list_files:
        # Copy to results; skip very last file (which is always the state file)
        res_args["files"] = files[:-1]

    res_args["state_file"] = files[-1]
    # DEBUG
    # res_args['check_results'] = check_results

    # Cleanup parameter to better match user's intention (Impacts the invocation/module_args output)
    module.params["src"] = src_orig
    del module.params["src_orig"]

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

    '''

    module.exit_json(**res_args)


if __name__ == '__main__':
    main()
