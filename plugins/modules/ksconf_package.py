#!/usr/bin/python
# -*- coding: utf-8 -*-

# This is a virtual module entirely implemented as an action plugin that runs on the controller

from __future__ import absolute_import, division, print_function


__metaclass__ = type


DOCUMENTATION = r'''
---
module: ksconf_package
short_description: Create a Splunk app from a local directory
description:
    - Build a Splunk app using the ksconf I(package) command.
      This can be as simple drop-in replacement for the M(community.general.archive) module.
      Advanced use cases can be supported by a combination of ksconf layers and/or file handlers.
      Idempotent behavior is fully supported.
    - The file handling mechanism allows for things like template rendering based on file matching.
    - Jinja2 template expansion is supported for (C(*.j2)) files by either using pure Jinja or
      Ansible Jinja handlers.
    - Ksconf I(layers) are fully supported and can be dynamically included or excluded with filters.
    - |
      There are two Jinja template modes:
      Standard C(jinja) mode uses plain Jinja syntax and is more portable (e.g., as it's also
      available via the C(ksconf package) command.)
      The C(ansible-jinja) mode supports all the features of Jinja within Ansible, which includes
      access to inventory variables, Ansible's full range of filters and tests, as well as lookup
      functionality.
      By default, all file handling is disabled to avoid any unwanted content modification.
      Use the I(enable_handler) option to enable a template handler.

version_added: "0.10.0"
author: Lowell C. Alleman (@lowell80)
requirements:
    - ksconf>=0.11.5

extends_documentation_fragment: action_common_attributes

attributes:
    check_mode:
        support: none
    diff_mode:
        support: none
    platform:
        support: full
        platforms: posix

options:
    source:
        description: Path of app directory
        type: path
        aliases: [src]
        required: true

    file:
        description: >
            - Tarball file created of the app.  This can be I(.spl) or I(.tar.gz)
            - This parameter supports dynamic placeholders.
              Variables are listed L(here,https://ksconf.readthedocs.io/en/stable/cmd_package.html#variables)
            - This value may require extra planning in scenarios where ksconf layers are in use
              and/or when templates are being used in combinations with variables.
              Any time a single I(source) input directory is used to build multiple variations or
              versions of an app a unique output I(file) is needed.
              Without taking this into consideration, various inefficiencies (cache misses)
              or the wrong variation being deployed or other confusing behavior.
              This can be avoided with planning.
              When using various layers, add C([[layers_hash]]) to the filename
              to easily solve this problem.
              When using templates with variables a custom approach is needed.
              For example, if building apps for different regions based on the I(region) variable.
              simply ensure that C({{region}}) appears in in I(file) value.
              These approaches are not mutually exclusive.
              It's possible to combine both layers and Jinja variable approaches in combination.
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
            - Placeholder variables, such as C({{app_id}}) can be used here.
        type: str

    enable_handler:
        description:
            - Enable one or more file handlers for template expansion and encrypted file support.
            - Use C(jinja) for basic Jinja2 syntax support.
              All necessary variables must be passed in via the I(template_vars) argument.
            - Use C(ansible-jinja) to use the Ansible engine to handle all jinja rendering.
              By default, all Ansible variables, filters, tests, and lookups are available.
              This is effectively like using the M(ansible.builtin.template) module to render all
              C(*.j2) files before packaging an app.
            - Use C(ansible-vault) to enable ansible vault decryption of files.
              This will only decrypt files matching C(*.vault).
        type: list
        choices:
          - ansible-jinja
          - ansible-vault
          - jinja
        elements: str

    template_vars:
        description:
            - Add-hoc variables useable during template expansion.
            - This dictionary can be structured any way that's helpful.
              There are no restrictions imposed, but be aware that sending more variables than
              needed could result in extra processing.
            - When using the C(ansible-jinja) handler, these values will be added to existing Ansible variables.
              Variables set here will have the highest precedence.
        type: dict
        required: false
        default: {}

    context:
        description:
            - Free-form metadata that is passed through to the output.
            - Use this to pass around important app context variables that can
              be conveniently retained when looping and using C(register).
        type: dict

    encrypt:
        description:
            - Encrypt the resulting archive I(file).
              Set to C(vault) to encrypt with ansible-vault.
        type: str
        default: false
        choices:
            - false
            - vault

    cache_storage:
        description:
            - Path to local cache storage.
            - Avoid sharing this too broadly, for example in a multitenant scenario.
        type: path
        default: ~/.cache/cdillc-splunk-ksconf-package

    cache:
        description:
            - Control caching behavior.
            - To fully enable or disable cache use C(on) or C(off).
              Use C(rebuild) to ignore an existing cache entries and force but allow cache to be stored.
              C(read-only) allows existing cache to be used but writes or updates to cache is prohibited.
              Generally C(rebuild) and C(read-only) shouldn't be necessary unless debugging the caching mechanism
              or a bug is found or suspected.
            - Note that using C(rebuild) may not result in an actual C(updated) I(action).
              The package will fully repackaged internally but this does not bypass the idempotent mechanism.
              Please see the general notes for additional explanation of this behavior.
        choices: ["on", "off", "rebuild", "read-only"]
        default: "on"

# set_version
# set_build

notes:
    - |
      As of v0.19.0, the C(ksconf_package) modules is implemented as an action.
      This means that it must run on the controller not the target machine.
      In practice, this should not impact most use cases as specifying I(delegate_to: localhost)
      was the most common way to use this module anyways.
      Switching from a module to an action allows us access to the full variable inventory that
      isn't accessible to remote modules without explicitly passing in every variable needed.
    - Several parameters accept ksconf variables.  Traditionally these are written in a Jinja-2 like
      syntax, which is familiar, but leads to some confusion when embedded in an Ansible playbook.
      To avoid Jinja escaping these variables manually, this modules supports C([[var]]) syntax too.
      If the path includes C([[version]]) that will be translated to C({{version}}) before be
      handed to the ksconf tool.
    - Jinja template files are detected based on the C(*.j2) pattern.
      The C(.j2) extension will be removed from the final name.
      Remember this off by default, and must be enabled with I(enable_handler).
    - Idempotent operations are supported by rendering the app to a temporary file and then
      comparing the content signature of a newly generated tarball against the previous one.
      To speed this up a cached C(.manifest) file is stored along side I(file) so that the
      previous hash doesn't need to be recalculated in many cases.
      As this requires a non-trivial amount of work for larger apps, this can feel slow.
    - As of v0.26 caching behavior is supported to reduce the amount of work that needs to be done
      in many no-change operations.
      (Please avoid the first attempt of caching support added v0.25.)
      Caching is implemented by saving the output of previous runs and determining if any parameters
      or if the I(source) directory itself has undergone any changes since the last execution.
      A cache hit occurs when no changes have been detected, and therefore reuse occurs;
      the output file and return values are re-used from a previous execution.

      Specifically any change to I(file), I(block), I(layer_method), I(local),
      I(follow_symlink), I(app_name), or I(encrypt) can modify the resulting
      tarball, and therefore will trigger a cache miss.
      Any I(layers) given are also taken into consideration, but only changes to which layers match
      or the content within those layers will result in a cache miss.
      For non-layered apps, the entire I(source) directory is scanned for changes
      Any change will trigger a full rebuild, even if the change is to a file that is blocked.

      Change detection for I(source) is based on file name, size, timestamps and not a hash.
      This allows quick execution when no inputs have changed which is a very common scenario.
      Templates are handled differently from normal files.
      All templates are expanded and a hash of the rendered content is compared.
      This is more expensive, but it ensures that templates or variable changes are handled predictably.
    - |
      How to force a I(changed) outcome?  Or, how to force an app re-deployment.
      This is a bit difficult to do by design and should not be necessary most of the time.
      Both caching and idempotent mechanisms will attempt to keep avoid unnecessary changes.
      So simply clearing the cache, or deleting the manifest file is not enough.
      Simply touching a files modification time will trigger a cache miss, but ultimately will report
      C(action=unchanged) as there is no change to the actual content.
      To force a change result (or I(created) action), either change the actual content of a file, or
      remove the I(archive) file from the filesystem.
      Also keep in mind that if the ultimate goal is to trigger an app re-install and if installation is
      handle by M(cdillc.splunk.ksconf_app_sideload), then simply removing the I(archive) file will still
      be irrelevant as that module also builds a local manifest in attempt to avoid unnecessary installations,
      unless app content has changed.

    - When using both templates and layering, be aware that Jinja2 templates are expanded before
      layer filtering.  This allows one layer to include C(indexes.conf) and another layer to
      include C(indexes.conf.j2).  All templates will be expanded first, then the resulting layers
      will be merged.
    - |
      Normal use case:
      Often apps are contained within a version control system are packaged on
      the controller node and shipped to various Splunk nodes.
      App installation can be done using the M(cdillc.splunk.ksconf_app_sideload) module.
      Alternative installation methods include using Splunk's app install CLI, or ship apps to Splunk Cloud via API.

'''


RETURN = '''
app_name:
    description: >
        Final name of the splunk app, which is the top-level directory
        included in the generated archive.
    type: str
    returned: always
    sample: org_custom_tech

action:
  description: >
    Resulting action code.
    Values are C(created), C(updated), C(unchanged), or C(cached).
    Both C(cached) and C(unchanged) indicate that the output file was reused from a previous run.
    C(cached) means that no-changes were found early in the process (based on the I(source) folder and parameters),
    whereas C(unchanged) means that no change was detected but only after packaging the entire app.
    C(created) means no existing output file was present.
    C(updated) means that the output checksum changed.
    If I(encrypt) has changed, without any changes in I(source), then actions
    will be either C(encrypt) and C(decrypt).
  type: str
  returned: always
  sample: unchanged

archive:
    description: >
        Location of the generated archive.
        This will either be the literal value passed to I(file), or
        the expanded version of I(file) when ksconf variables are used.
    type: path
    returned: always
    sample: /tmp/splunk_apps/org_custom_tech-1.4.3.tgz

archive_size:
    description: Size of the generated C(archive) file in bytes.
    type: int
    returned: always
    sample:

encryption:
    description: Final encryption state of the archive.
    type: str
    returned: always
    sample: vault

encryption_size:
    description: Size of file on disk, after encryption.
    type: int
    returned: if I(encrypt) is enabled

stdout:
    description: Output stream of details from the ksconf packaging operations.
    type: str
    returned: when package created
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
    description: Optional pass-through field.  See the C(context) parameter.
    type: dict
    returned: when provided

cache:
    description:
      - Cache result status or message in case of a cache error.
      - Values include:  C(hit), C(miss), C(created), C(updated), or C(disabled).
        Other values start with C(failed) and a reason message.
        Note that C(miss) will rarely occur unless new cache cannot be created or if I(cache) is set to C(read-only).
        Both C(updated) and C(created) imply a cache miss.
    type: dict
    returned: always

'''


EXAMPLES = r'''

- name: Build addon using a specific set of layers
  cdillc.splunk.ksconf_package:
    source: "{{ app_repo }}/Splunk_TA_nix"
    file: "{{ install_root }}/build/Splunk_TA_nix.spl"
    block: ["*.sample"]
    local: preserve
    follow_symlink: false
    layers:
      - exclude: "30-*"
      - include: "30-{{role}}"
      - exclude: "40-*"
      - include: "40-{{env}}"

# More complex example that loops over an 'apps_inventory' list that contains both
# local directories and pre-packaged tarballs (which don't need to be re-packaged)
- name: Render apps from version control
  cdillc.splunk.ksconf_package:
    source: "{{ rendered_apps_folder }}/{{ item.name }}"
    file: "{{ tarred_apps_folder }}/{{ item.name }}-[[ layers_hash ]].tgz"
    local: preserve
    layers:
      - include: "10-upstream"
      - include: "20-common"
      - include: "30-{{ app_role }}"
      - include: "40-{{ layer_env }}"
      - include: "50-{{ app_role }}-{{ layer_env }}"
      - include: "60-{{ org }}"
    enable_handler: ansible-jinja
    template_vars:
      org_name: acme
      default_retention: 7d
      splunk:
        key_password: "{{ splunk.key_password }}"
  delegate_to: localhost
  run_once: true
  loop: >
    {{ apps_inventory
    | selectattr("state", "eq", "present")
    | rejectattr("tarball")
    }}
  register: app_render_output
  tags: render
'''
