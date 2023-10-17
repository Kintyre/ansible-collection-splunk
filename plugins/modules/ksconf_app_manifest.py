# -*- coding: utf-8 -*-
#
# MODULE:  (This runs on the target node)
#
"""

Eventually this module should be expanded to support:

1.) Fast hash check.   No need to return the entire payload if the hash matches on the target
2.) Check for differences.   Report which (if any) files vary from the known manifest.
3.) Check against an explicit manifest???  (needs more consideration)

"""

from __future__ import absolute_import, division, print_function

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.cdillc.splunk.plugins.module_utils.ksconf_shared import (
    __version__ as collection_version, check_ksconf_version)


try:
    from ksconf.version import version as ksconf_version
except ImportError:
    from ksconf._version import version as ksconf_version


if TYPE_CHECKING:
    from ksconf.app.manifest import AppManifest
else:
    AppManifest = Any


__metaclass__ = type

ksconf_min_version = (0, 11, 5)
ksconf_warn_version = (0, 13, 4)

ksconf_min_version_text = ".".join(f"{i}" for i in ksconf_min_version)
ksconf_warn_version_text = ".".join(f"{i}" for i in ksconf_warn_version)


DOCUMENTATION = r'''
---
module: ksconf_app_manifest
short_description: Splunk app manifest
version_added: '0.22.0'
author: Lowell C. Alleman (@lowell80)
description:
  - This is used internally by the M(ksconf_app_sideload).
    This is not currently intended to be used directly by users.

requirements:
  - ksconf>=0.11

options:
  app_dir:
    description: Path to Splunk application
    type: path
    required: true
  manifest:
    description: Location of manifest file
    type: path
    required: true

attributes:
  action:
    support: full
  async:
    support: none
  bypass_host_loop:
    support: none
  check_mode:
    support: full
  diff_mode:
    support: none
  platform:
    platforms: posix
  safe_file_operations:
    support: none
  vault:
    support: none

notes:
  - Requires ksconf on the target host.

'''


EXAMPLES = r'''
- name: Extract ta-nix.tgz into /opt/splunk/etc/apps
  cdillc.splunk.ksconf_app_manifest:
    app_dir: /opt/splunk/etc/apps/myapp
    state_file: app_dir: /opt/splunk/etc/apps/myapp/.ksconf_sideload.json

'''


RETURN = r'''
app_dir:
  description:  Expanded application directory
    - The source archive's path.
  returned: always
  type: str
  sample: "/home/paul/test.tar.gz"
state:
  description: State of the state file / manifest
  returned: always
  type: str
  sample:
# state_file:
#  description: Relative path to the json state tracking file where installation state, source hash,
#               and application manifest is stored.
#  returned: always
#  type: str
#  sample: fire_brigade/.ksconf_sideload.json
'''


def get_app_manifest(state_file: Path) -> AppManifest:
    from ksconf.app.manifest import AppManifest
    try:
        with open(state_file) as fp:
            try:
                state_data = json.load(fp)
            except ValueError:
                # Or json.decoder.JSONDecodeError?
                return None, None, "corrupted"
            if "manifest" in state_data:
                return AppManifest.from_dict(state_data.pop("manifest")), state_data, "present"
            else:
                return None, state_data, "old-version"
    except FileNotFoundError:
        return None, None, "missing"


def build_app_manifest(app_dir: Path, state_file: Path) -> AppManifest:
    from ksconf.app.manifest import AppManifest

    # Is this overcomplicated?   Is the better option:   lambda p: p.name != SIDELOAD_STATE_FILE
    if state_file.exists() and state_file.is_relative_to(app_dir):
        rel_statefile = state_file.relative_to(app_dir)

        def filter_state_file(path):
            return path != rel_statefile
    else:
        # Paths not relative no existing state file, therefore no filter needed
        filter_state_file = None

    try:
        # Ksconf v0.13.4 adds 'filter_file'
        manifest = AppManifest.from_filesystem(app_dir, calculate_hash=True,
                                               filter_file=filter_state_file)
    except TypeError:
        # Older ksconf.  Simply remove (and then restore) the manifest file
        try:
            if state_file.exists():
                temp_state = app_dir.parent.joinpath(f".{app_dir.name}.ksconf-manifest-rebuild.tmp")
                state_file.replace(temp_state)
            else:
                temp_state = None
            manifest = AppManifest.from_filesystem(app_dir, calculate_hash=True)
        finally:
            if temp_state:
                temp_state.replace(state_file)
    return manifest


def write_app_state(state_file: Path,
                    app_manifest: AppManifest,
                    existing_state: dict = None):
    from ksconf.util.file import atomic_open
    if existing_state:
        data = existing_state.copy()
    else:
        data = {}

    data.setdefault("src_path", None)
    data.setdefault("installed_at", time.time())
    data.update(src_hash=app_manifest.hash,
                ansible_module_version=collection_version,
                ksconf_version=ksconf_version,
                manifest=app_manifest.to_dict())
    data["rebuilt_from_filesystem"] = True
    with atomic_open(state_file, mode="w", temp_name="tmp.sideload") as marker_f:
        json.dump(data, marker_f, indent=1)
    return data


def main():
    module = AnsibleModule(
        argument_spec=dict(
            app_dir=dict(type='path', required=True),
            state_file=dict(type="path", required=False),
            rebuild_manifest=dict(type=bool, default=False),
        ),
        supports_check_mode=False,
    )

    ksconf_version = check_ksconf_version(module)
    if ksconf_version < ksconf_min_version:
        module.fail_json(
            msg=f"ksconf version {ksconf_version} is older than {ksconf_min_version_text}.  "
            "This may result in unexpected behavior.  Please upgrade ksconf to "
            f"{ksconf_warn_version_text} or higher.  Please run:  \n"
            "    ansible-playbook cdillc.splunk.install_dependencies -e splunk_host=all")
    if ksconf_version < ksconf_warn_version:
        # It *should* still work, but your milage may vary
        module.warn(f"ksconf version {ksconf_version} is older than {ksconf_warn_version_text}.")

    app_dir = Path(module.params['app_dir'])
    state_file = Path(module.params["state_file"])
    rebuild_manifest = module.params['rebuild_manifest']

    if module.check_mode:
        module.exit_json(msg="Check mode unsupported....  Please finish the implementation!")

    results = {
        "app_dir": os.fspath(app_dir),
        "state_file": os.fspath(state_file),
    }
    if not app_dir.is_dir():
        module.fail_json(msg=f"App directory {app_dir} does not exists", result="no-app")
    if not os.access(app_dir, os.R_OK):
        module.fail_json(msg=f"App directory {app_dir} is not readable", result="no-app")

    # Is the state file missing (only a problem if rebuild_manifest is not present)
    manifest, state, results["result"] = get_app_manifest(state_file)

    if not manifest and rebuild_manifest:
        manifest = build_app_manifest(app_dir, state_file)
        state = write_app_state(state_file, manifest, state)
        results["result"] = "rebuilt"

    if not manifest:
        module.fail_json(msg=f"State file {state_file} does not exist",
                         result="no-manifest")
        return

    results["state"] = state
    results["manifest"] = manifest.to_dict()
    module.exit_json(**results)


if __name__ == '__main__':
    main()
