#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

import datetime
import os

from ansible.module_utils._text import to_text
from ansible.module_utils.basic import AnsibleModule
from ksconf.package import AppPackager


__metaclass__ = type

MODULE_NAME = "ksconf_package"

DOCUMENTATION = r'''
---
module: ksconf_package
short_description: Create a Splunk app from a local directory
description:
    - Build a Splunk app using the I(ksconf package) functionality.
    - The source directory may contain layers
version_added: "0.10.0"
author: Lowell C. Alleman (@lowell80)
requirements:
  - kintyre-splunk-conf>=0.9.1
attributes:
# TODO --
#    check_mode:
#        support: full
#    diff_mode:
#       support: none
    platform:
      support: full
      platforms: posix

options:
    source:
        description: Path to input directory for the app
        type: path
        aliases: [src]
        required: true

    file:
        description: >
            Tarball file created of the app.  This can be I(.spl) or I(.tar.gz)
            This parameter supports dynamic placeholders.
            Variables are listed L(here,https://ksconf.readthedocs.io/en/stable/cmd_package.html#variables)
        type: path
        required: true

    block:
        description: Pattern for files/directories to exclude.
        type: list
        elements: path
        default: []

    layer_method:
        description: Type of layers used within the I(source) directory.
        choices: ["auto", "dir.d", "disable"]
        default: dir.d

    layers:
        description:
          - Include and exclude rules regarding which layers to include in the generated app.
          - Layer filters rules are evaluated sequentially, and the last match wins.
          - List of dictionaries with a single key, either I(include) or I(exclude)
        type: list
        elements: dict
        default: []
        suboptions:
            include:
                description: Specify a layer or layer glob pattern to include.
                type: str
            exclude:
                description: Specify a layer or layer glob pattern to exclude.
                type: str

    local:
        description:
          - Define handling of of C(local) directory and C(local.meta) file.
          - Use I(preserve) to keep the local artifacts as-is.
          - I(block) will exclude local artifacts from the generated app archive.
          - I(promote) will merge any local artifacts into the default layer.
        choices: ["preserve", "block", "promote"]
        type: str
        default: preserve

    follow_symlink:
        description:
            - Follow symbolic links pointing to directories.
            - Symlinks to files are always followed.
        type: bool
        default: false

    app_name:
        description:
          - Specify the top-level folder (app) name.
          - If this is not given, the app folder name is automatically extracted
            from the basename of C(source).
          - Placeholder variables, such as ``{{app_id}}`` can be used here.
        type: str

    context:
        description:
            -Free-form metadata that is passed through to the output.
            - Use this to pass around important app context variables that can
              be conveniently retained when looping and using C(register).
        type: dict

# set_version
# set_build


notes:
    - Add comments about magic vars
'''


RETURN_ = r'''
app_name:
    description: >
        Final name of the splunk app, which is the top-level directory
        included in the generated archive.
    type: str
    returned: always
    sample: org_custom_tech
archive:
    description: >
        The location where the generated archive lives.
        This could vary dynamically if C(file) contained a placeholder.
    type: path
    returned: always
    sample: /tmp/splunk_apps/org_custom_tech-1.4.3.tgz
archive_size:
    description: Size of the generated C(archive) file in bytes.
    type: int
    returned: always
    sample:
stdout:
    description: Output stream of details from the ksconf packaging operations.
    type: str
    returned: always
    sample:

new_hash:
    description: >
        Checksum of the previous (existing) tarball, if present.
        This is a SHA256 of the uncompressed content.
    type: str
    returned: always
    sample:

old_hash:
    description: Checksum of the new tarball.  See notes regarding I(new_hash) for more details.
    type: str
    returned: always
    sample: e1617a87ea51c0ca930285c0ce60af4308513ea426ae04be42b1d7b47aba16a5

context:
    description: Optional pass-through field.  See the C(context) paramater.
    type: dict
    returned: when provided
'''


EXAMPLES_ = r'''

- name: Build addon using a specific set of layers
  cdi.splunk.ksconf_package:
  source: "{{app_repo}}/Splunk_TA_nix"
  file: "{{install_root}}/build/Splunk_TA_nix.spl"
  block: [*.sample]
  local: preserve
  follow_symlink: false
  layers:
    - exclude: 30-*
    - include: 30-{{role}}
    - exclude: 40-*
    - include: 40-{{env}}
'''
VALID_LAYER_ACTIONS = ["include", "exclude"]


def gzip_content_hash(filename, blocksize=64 * 1024):
    """ Get the hash of the contents of a compressed (gz) file.  Otherwise,
    using AnsibleModule.digest_from_file() would be better option.

    Unfortunately, in our use case, the gzip header of the tgz file contains a
    reference to the creation time of the archive, hence the exact same input
    will show as a modification.  Eventually, input change detection support
    should supersede all this wonkyness.
    """
    from gzip import GzipFile
    from hashlib import sha256
    filename = os.path.realpath(filename)
    if not os.path.isfile(filename):
        return None

    digest = sha256()
    with GzipFile(filename, "rb") as stream:
        block = stream.read(blocksize)
        while block:
            digest.update(block)
            block = stream.read(blocksize)
        return digest.hexdigest()


def main():
    module = AnsibleModule(
        argument_spec=dict(
            source=dict(type="path", required=True),
            file=dict(type="path", required=True),
            block=dict(type="list", elements="str", default=[]),
            layer_method=dict(type="str",
                              choices=["auto", "dir.d", "disable"],
                              default="dir.d"),
            layers=dict(type="list", default=[],
                        elements="dict",
                        options=dict(include=dict(type="str", default=None),
                                     exclude=dict(type="str", default=None),
                                     ),
                        mutually_exclusive=[("include", "exclude")],
                        required_one_of=[("include", "exclude")]
                        ),
            local=dict(type="str",
                       choices=["preserve", "block", "promote"],
                       default="preserve"
                       ),

            follow_symlink=dict(type="bool", default=False),
            app_name=dict(type="str", default=None),
            context=dict(type="dict", default=None),
        )
    )
    params = module.params
    ret = {}

    source = params["source"]
    dest_file = params["file"]
    block = params["block"]
    layer_method = params["layer_method"]
    layers = params["layers"]
    local = params["local"]
    follow_symlink = module.boolean(params["follow_symlink"])
    app_name = params["app_name"]

    # Copy 'context' through as-is
    if params["context"]:
        ret["context"] = params["context"]

    # Validate 'layers' paramater
    # It's possible that the 'options' configuration in Ansible's argument_spec will handle all this for us...?
    if layers is None:
        # No explicit layers given.
        # TODO: Note this in the output, somewhere
        pass
    elif not isinstance(layers, list):
        module.fail_json(msg="The 'layers' paramater must be a list of "
                         "dictionaries.  Given {}.".format(type(layers)))
    elif not all(isinstance(layer, dict) and len(layer) == 1 for layer in layers):
        module.fail_json(msg="All elements in the 'layers' list must be "
                         "dictionaries with a single key")
    else:
        for layer in layers:
            key, value = layer.items()[0]
            if key not in VALID_LAYER_ACTIONS:
                module.fail_json(msg="Entry {0}={1} in the layer list is not allowed.  "
                                 "The key '{0}' must be one of {2}".format(
                                     key, value, ", ".join(VALID_LAYER_ACTIONS)))

    if not os.path.isdir(source):
        module.fail_json(msg="The source '{}' is not a directory or is not "
                         "accessible.".format(source))

    # if (splunk_user or splunk_pass) and not (splunk_user and splunk_pass):
    #    module.fail_json(msg="Both 'username' and 'password' must be specified at the same time.")

    '''
    if creates:
        # do not run the command if the line contains creates=filename
        # and the filename already exists.
        v = os.path.expanduser(creates)
        if os.path.exists(v):
            module.exit_json(
                cmd=args, changed=False, rc=0,
                stdout="skipped, since %s exists" % v,
                stderr=False
            )

    if removes:
        # do not run the command if the line contains removes=filename
        # and the filename does not exist.  This allows idempotence
        # of command executions.
        v = os.path.expanduser(removes)
        if not os.path.exists(v):
            module.exit_json(
                cmd=args, changed=False, rc=0,
                stdout="skipped, since %s does not exist" % v,
                stderr=False
            )
    '''
    start_time = datetime.datetime.now()

    from io import StringIO
    log_stream = StringIO()

    # XXX: This currently ignores the possibility of 'dest_file' containing arbitrary placeholders
    existing_hash = gzip_content_hash(dest_file)

    # Just call combine (writing to a temporary directory) and the tar it up.
    # At some point this should all be done in memory, as this would allow for quicker
    # detection/reporting of changes to support idepotent behavior more efficiently.

    app_name_source = "set via 'app_name'"
    if not app_name:
        app_name = os.path.basename(source)
        app_name_source = "taken from source directory"

    log_stream.write("Packaging {}   (App name {})\n".format(app_name, app_name_source))
    packager = AppPackager(source, app_name, output=log_stream)

    with packager:
        # combine expects as list of (action, pattern)
        layer_filter = [layer.items() for layer in layers]
        packager.combine(source, layer_filter,
                         layer_method=layer_method,
                         allow_symlink=follow_symlink)
        # Handle local files
        if local == "promote":
            packager.merge_local()
        elif local == "block":
            packager.block_local()
        elif local == "preserve":
            pass
        else:   # pragma: no cover
            raise ValueError("Unknown value for 'local': {}".format(local))

        if block:
            log_stream.write("Applying blocklist:  {!r}\n".format(block))
            packager.blocklist(block)

        '''
        if args.set_build or args.set_version:
            packager.update_app_conf(
                version=args.set_version,
                build=args.set_build)
        '''

        packager.check()
        # os.system("ls -lR {}".format(packager.app_dir))

        archive_base = packager.app_name.lower().replace("-", "_")

        # Should we default 'dest' if no value is given???? -- this seems problematic (at least we need to be more specific, like include a hash of all found layers??)
        dest = dest_file or "{}-{{{{version}}}}.tgz".format(archive_base)
        archive_path = packager.make_archive(dest)
        size = os.stat(archive_path).st_size
        log_stream.write("Archive created:  file={} size={:.2f}Kb\n".format(
            os.path.basename(archive_path), size / 1024.0))

        # Should this be expanded to be an absolute path?
        ret["archive"] = archive_path
        ret["app_name"] = packager.app_name
        ret["archive_size"] = size

        # TODO: Return the layer names used.  Currently hidden behind AppPackager's internal call to "combine"
        # ret["layers"] = list(...)

    end_time = datetime.datetime.now()
    delta = end_time - start_time

    ret["start"] = to_text(start_time)
    ret["end"] = to_text(end_time)
    ret["delta"] = to_text(delta)
    ret["stdout"] = to_text(log_stream.getvalue())

    # Inefficient idepotent implementation; but it works with ksconf 0.9.1
    new_hash = gzip_content_hash(ret["archive"])
    ret["changed"] = new_hash != existing_hash

    ret["new_hash"] = new_hash
    ret["old_hash"] = existing_hash
    module.exit_json(**ret)


if __name__ == '__main__':
    main()
