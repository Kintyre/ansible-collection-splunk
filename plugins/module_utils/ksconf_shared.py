# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function


__metaclass__ = type

import json
import os
import re

from ansible.module_utils.basic import AnsibleModule


__version__ = "0.17.0"

SIDELOAD_STATE_FILE = ".ksconf_sideload.json"

# Traditional Splunk home (install paths)
SPLUNK_HOME_PATH = [
    "/opt/splunk",
    "/Applications/Splunk",
    "/opt/splunkforwarder"
]


def find_splunk_home():
    if "SPLUNK_HOME" in os.environ:
        return os.environ["SPLUNK_HOME"]
    for path in SPLUNK_HOME_PATH:
        if os.path.isdir(path):
            return path
    return None


def check_ksconf_version(module):
    # type: (AnsibleModule) -> tuple
    try:
        from ksconf import __version__ as ksconf_version
    except ImportError:
        module.fail_json(msg="Unable to import the 'ksconf' python module.  "
                             "Try running 'pip install -U ksconf'")

    match = re.match(r'(\d+)\.(\d+)\.(\d+)(.*)$', ksconf_version)
    if match:
        p = match.groups()
        return int(p[0]), int(p[1]), int(p[2]), p[3]
    else:
        module.warn("Unable to parse ksconf version.  '{}'".format(ksconf_version))
        return 0, 0, 0, ksconf_version


def gzip_content_hash(filename, blocksize=64 * 1024):
    """ Get the hash of the contents of a compressed (gz) file.  Otherwise,
    using AnsibleModule.digest_from_file() would be better option.

    Unfortunately, in our use case, the gzip header of the tgz file contains a
    reference to the creation time of the archive, hence the exact same input
    will show as a modification.  Eventually, input change detection support
    should supersede all this wonkyness.
    """
    from gzip import BadGzipFile, GzipFile
    from hashlib import sha256
    filename = os.path.realpath(filename)
    if not os.path.isfile(filename):
        return None

    try:
        digest = sha256()
        with GzipFile(filename, "rb") as stream:
            block = stream.read(blocksize)
            while block:
                digest.update(block)
                block = stream.read(blocksize)
            return digest.hexdigest()
    except BadGzipFile:
        # Ideally this would be logged...
        return None


def get_app_info_from_spl(tarball, calc_hash=True):
    ''' Returns list of app names, merged app_conf and a dictionary of extra facts that may be useful '''
    # XXX: Move this into ksconf.archive and share it with ksconf.commands.unarchive
    from io import StringIO

    from ksconf.archive import extract_archive, gaf_filter_name_like, sanity_checker
    from ksconf.conf.parser import (PARSECONF_LOOSE, ConfParserException,
                                    default_encoding, parse_conf)

    app_names = set()
    app_conf = {}
    files = 0
    local_files = set()
    a = extract_archive(tarball, extract_filter=gaf_filter_name_like("app.conf"))
    for gaf in sanity_checker(a):
        gaf_app, gaf_relpath = gaf.path.split("/", 1)
        files += 1
        # TODO: Can we ensure that local vs default is extracted in the correct order?  Actually, we don't even look at the path at all!  This needs some cleanup!
        if gaf.path.endswith("app.conf") and gaf.payload:
            conffile = StringIO(gaf.payload.decode(default_encoding))
            conffile.name = os.path.join(tarball, gaf.path)
            app_conf = parse_conf(conffile, profile=PARSECONF_LOOSE)
            del conffile
        elif gaf_relpath.startswith("local" + os.path.sep) or \
                gaf_relpath.endswith("local.meta"):
            local_files.add(gaf_relpath)
        app_names.add(gaf_app)
        del gaf_app, gaf_relpath
    extras = {
        "local_files": local_files,
        "file_count": files,
    }

    if calc_hash:
        # TODO: Find a more efficient way to get this hash (instead of reading from disk twice)
        extras["hash"] = gzip_content_hash(tarball)
    return app_names, app_conf, extras


# Which app.conf stanzas / attributes should be returned as facts
keep_app_conf_pairs = [
    ("launcher", [
        "version",
        "author",
        "description"]),
    ("install", [
        "state",
        "build",
        "is_configured",
        "allows_disable",
        "install_source_checksum",
        "install_source_local_checksum",
        "state_change_requires_restart",
    ]),
    ("package", [
        "id",
        "check_for_updates"]),
    ("ui", [
        "label",
        "is_visible"]),
    ("shclustering", [
        "deployer_lookups_push_mode",
        "deployer_push_mode"]
     )
]


def get_app_facts(app_path,
                  use_appconf=True,
                  use_sideload_state=True):
    """
    Get various facts related to a local Splunk application.
    """
    facts = {}
    from pathlib import Path

    from ksconf.conf.merge import merge_conf_dicts
    from ksconf.conf.parser import PARSECONF_LOOSE, parse_conf

    app_path = Path(app_path)

    if use_appconf:
        app_conf_paths = [
            app_path / "default" / "app.conf",
            app_path / "local" / "app.conf"]
        conf = {}
        for app_conf_path in app_conf_paths:
            if app_conf_path.is_file():
                conf = merge_conf_dicts(conf, parse_conf(app_conf_path, PARSECONF_LOOSE))
        if conf:
            facts["app_conf"] = {}

        for stanza_name, attributes in keep_app_conf_pairs:
            if stanza_name in conf:
                stanza = conf[stanza_name]
                for attr in attributes:
                    if attr in stanza:
                        facts["app_conf"][attr] = stanza[attr]

    if use_sideload_state:
        state_file = app_path / SIDELOAD_STATE_FILE
        if state_file.is_file():
            with open(state_file) as fp:
                data = json.load(fp)
            # XXX: Maybe filter / pre-process this info somehow (this could get very large
            #      once manifest is added)
            facts["sideload"] = data

    return facts
