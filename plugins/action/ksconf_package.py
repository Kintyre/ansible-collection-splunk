# -*- coding: utf-8 -*-
#
# ACTION:  (This runs on the controller!)
#


from __future__ import absolute_import, division, print_function

import datetime
import os
import re
from io import StringIO
from pathlib import Path, PurePath

from ansible.errors import AnsibleError
from ansible.module_utils._text import to_text
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.plugins.action import ActionBase
from ansible.template import Templar
from ansible.utils.display import Display
from ansible_collections.cdillc.splunk.plugins.module_utils.ksconf_shared import (
    SIDELOAD_STATE_FILE, check_ksconf_version)
from ksconf.app.manifest import create_manifest_from_archive, load_manifest_for_archive
from ksconf.layer import LayerRenderedFile, layer_file_factory, register_file_handler
from ksconf.package import AppPackager


display = Display()
MODULE_NAME = "ksconf_package"


JINJA_HANDLERS = ["ansible", "ansible-jinja"]
# For now this is the same
TEMPLATE_HANDLERS = JINJA_HANDLERS


ksconf_min_version = (0, 11, 4)
ksconf_min_version_text = ".".join("{}".format(i) for i in ksconf_min_version)

ksconf_version = check_ksconf_version()
if ksconf_version < ksconf_min_version:
    raise AnsibleError(f"ksconf version {ksconf_version} is older than v{ksconf_min_version_text}."
                       "  This may result in unexpected behavior.  Please upgrade ksconf.")


@register_file_handler("ansible-jinja", priority=10, enabled=False)
class LayerFile_AnsibleJinja2(LayerRenderedFile):
    """
    Custom ansible render handler for Ksconf layers
    This makes a callback into Ansible's template functionality for actual rendering
    """
    SUFFIX_MATCH = {".j2"}

    module: ActionBase = None
    _templar: Templar = None

    @classmethod
    def set_module(cls, module: ActionBase):
        cls._templar = module._templar

    @classmethod
    def match(cls, path: PurePath) -> bool:
        return path.suffix in cls.SUFFIX_MATCH

    @property
    def templar(self) -> Templar:
        # Use context object to 'cache' the templar
        if not hasattr(self.layer.context, "ansible_templar"):
            self.layer.context.ansible_templar = self._build_templar()
        return self.layer.context.ansible_templar

    def _build_templar(self):
        updates = {
            "searchpath": [os.fspath(self.layer.root)]
        }
        if self.layer.context.template_variables:
            updates["available_variables"] = self.layer.context.template_variable
        templar = self._templar.copy_with_new_env(**updates)
        return templar

    def render(self, template_path: Path) -> str:
        # Note that because we do not call generate_ansible_template_vars(), we cannot make use
        # of 'template_*' variables (like path/mtime/host).  These tend to interfere with
        # idempotent behavior so not a big loss)
        template = template_path.read_text()
        value = self.templar.do_template(template)
        # TODO: If the file is a .conf or .meta file, then attempt to parse and report any errors to
        #       the caller.  This prevents broken .conf files from being deployed!
        return value


def translate_ksconf_vars(value):
    """
    Translate any '[[var]]' format into '{{var}}' format for ksconf.  This
    allows playbook authors to write:
        [[var]]
    instead of:
        {{'{{'}}version{{'}}'}}
    """
    if value:
        return re.sub(r'\[\[(\s*[\w_]+\s*)\]\]', r"{{\1}}", value)
    return value


def failed(msg, *args, **kwargs):
    d = {"failed": True,
         "msg": msg}
    d.update(*args, **kwargs)
    return d


class ActionModule(ActionBase):

    # Don't support moving files.  Everything is done on the controller
    TRANSFERS_FILES = False

    def run(self, tmp=None, task_vars=None):
        ''' handler for ksconf app packaging operation '''
        if task_vars is None:
            task_vars = dict()
        result = super(ActionModule, self).run(tmp, task_vars)
        del tmp

        validation_result, params = self.validate_argument_spec(
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
                enable_handler=dict(type="list", elements="str", default=[]),
                # Do we need 'NO_LOG' here to protect sensitive information?
                template_vars=dict(type="dict", default=None, required=False),
                follow_symlink=dict(type="bool", default=False),
                app_name=dict(type="str", default=None),
                context=dict(type="dict", default=None),
            )
        )

        source = params["source"]
        dest_file = params["file"]
        block = params["block"]
        layer_method = params["layer_method"]
        layers = params["layers"]
        enable_handler = set(params["enable_handler"] or [])
        template_vars = params["template_vars"] or {}
        local = params["local"]
        follow_symlink = boolean(params["follow_symlink"])
        app_name = params["app_name"]

        # Convert any [[var]] --> {{var}} for ksconf
        dest_file = translate_ksconf_vars(dest_file)
        app_name = translate_ksconf_vars(app_name)

        # Copy 'context' through as-is
        if params["context"]:
            result["context"] = params["context"]

        for handler_name in enable_handler:
            # TODO:  Add error checking here to give better exceptions to caller
            layer_file_factory.enable(handler_name)

        if template_vars and not enable_handler.intersection(TEMPLATE_HANDLERS):
            # This is not technically an error, but likely to be a mistake.
            display.warning("Setting 'template_vars' without enabling a template "
                            f"handler (such as {', '.join(TEMPLATE_HANDLERS)} will "
                            "result in all variables being undefined")

        LayerFile_AnsibleJinja2.set_module(self)

        jinja_handlers_enabled = enable_handler.intersection(JINJA_HANDLERS)
        if len(jinja_handlers_enabled) > 1:
            display.warning("Multiple Jinja template handlers have been enabled.  "
                            f"Please pick one:  {', '.join(jinja_handlers_enabled)}")

        if not os.path.isdir(source):
            return failed(f"The source '{source}' is not a directory or is not accessible.")

        start_time = datetime.datetime.now()

        log_stream = StringIO()

        app_name_source = "set via 'app_name'"
        if not app_name:
            app_name = os.path.basename(source)
            app_name_source = "taken from source directory"

        display.display(f"Packaging {app_name}   (App name {app_name_source})")
        packager = AppPackager(source, app_name, output=log_stream,
                               template_variables=template_vars)

        with packager:
            # combine expects as list of (action, pattern)
            layer_filter = [(mode, pattern) for layer in layers
                            for mode, pattern in layer.items() if pattern]
            if layer_filter:
                display.debug(f"Applying layer filter:  {layer_filter}")
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
                # Does argument validation take care of this scenario?  Keep until confirmed....
                return failed(f"Unknown value for 'local': {local}")

            if block:
                display.debug(f"Applying blocklist:  {block!r}")
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

            # Should we default 'dest' if no value is given???? -- this seems problematic
            # (at least we need to be more specific, like include a hash of all found layers??)
            dest = dest_file or "{}-{{{{version}}}}.tgz".format(archive_base)

            # Check manifest of existing 'dest' archive to enable idempotent operation
            archive_path = Path(packager.expand_var(dest))

            # TODO:  Ensure that creation of dest is not interrupted (either in ksconf level or here)
            #        Incomplete output files should never end up in dest.  (temp file rename pattern?

            new_manifest = packager.make_manifest(calculate_hash=True)
            existing_manifest = None

            # Make this idempotent by checking for the output tarball, and determining if the app content changed
            if archive_path.is_file():
                existing_manifest = load_manifest_for_archive(archive_path)
                if existing_manifest.hash == new_manifest.hash:
                    resulting_action = "skipped"
                else:
                    resulting_action = "updated"
            else:
                resulting_action = "created"

            if resulting_action != "skipped":
                archive_path2 = packager.make_archive(dest)
                # Assuming this is true, we can just discard the output of .make_archive()
                assert str(archive_path) == archive_path2
                create_manifest_from_archive(archive_path, None, manifest=new_manifest)

            size = archive_path.stat().st_size
            display.display(f"Archive {resulting_action}:  "
                            f"file={archive_path.name} "
                            f"size={size / 1024.0:.2f}Kb")

            result["action"] = resulting_action
            # Should this be expanded to be an absolute path?
            result["archive"] = os.fspath(archive_path)
            result["app_name"] = packager.app_name
            result["archive_size"] = size

            # TODO: return DELTA, this is basically done and ready.  See DeploySequence.from_manifest_transformation(old, new)

            # TODO: return the layer names used.  Currently hidden behind AppPackager's internal call to "combine"
            # result["layers"] = list(...)
            # Ideally, the manifest would contain this metadata as well.

        end_time = datetime.datetime.now()
        delta = end_time - start_time

        result["start"] = to_text(start_time)
        result["end"] = to_text(end_time)
        result["delta"] = to_text(delta)
        result["stdout"] = to_text(log_stream.getvalue())

        result["changed"] = resulting_action != "skipped"

        result["new_hash"] = new_manifest.hash
        result["old_hash"] = existing_manifest.hash if existing_manifest else ""

        # Fixup the 'layers' output (invocation/module_args/layers); drop empty
        params["layers"] = {mode: pattern for layer in layers
                            for mode, pattern in layer.items() if pattern}
        return result
