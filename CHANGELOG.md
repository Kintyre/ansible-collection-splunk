## Release 0.22.0 (DRAFT)
* `ksconf_app_sideload` - Add support for (re-)creating metadata when missing.
* `ksconf_app_manifest` - Internal module (not for end-users; or at least use-at-your-own-risk, this can change on a whim!)

## Release 0.21.3-4 (2023-10-12)
* Github action and galaxy publish fixes (no changes to collection content)

## Release 0.21.2 (2023-10-12)
* Add support for ksconf v0.13 which has some package namespace changes.

## Release 0.21.1 (2023-09-06)
* Bug fix for `ksconf_app_sideload` file existence checks.
* Bug fix for encrypting new tarballs using `ksconf_package`.

## Release 0.21.0 (2023-08-25)
* `ksconf_package`: Add ability to decrypt vaulted source files with `enable_handler=ansible-vault` and encrypted the generated tarballs using `encrypt=vault`.
* The controller node now requires ksconf v0.11.5 or later.

## Release 0.20.2 (2023-07-21)
* `splunk_user`: Got `force_change_pass` working.  The documentation was updated accordingly.

## Release 0.20.1 (2023-07-21)
* `splunk_cli`:  Rename the `splunk_uri` option to `splunkd_uri` to be consistent across modules.  Added alias for backwards compatibility.  (Aso fixed an example in the splunk_user docs)

## Release 0.20.0 (2023-07-21)
* `splunk_cli`: Allow full splunk path in `cmd` so that the `splunk_home` argument isn't needed.
  This arguably feels more natural and is more of a drop-in replacement for the command module.
* `splunk_user`: Started to add support for `force_change_pass` argument which sets the `force-change-pass` Splunk REST parameter.
  This currently is NOT working, but there were a enough documentation updates to justify putting the updated code into place.
* `asis`: Add support for overriding output by setting an output field named: `priority_msg`.
  Additionally, any task marked with "no_log" is silently bypassed from the output.

## Release 0.19.4 (2023-07-20)
* Add the most basic stdout callback handler ever `asis` which simply dumps any 'stdout', 'stderr', and 'msg' fields with minimal no formatting.  All other result fields are disregarded.

## Release 0.19.3 (2023-07-19)
* `splunk_cli`:
  * Fix but with `hidden_args` processing bug.
  * Improve error handling while parsing `cmd` into args.
* `ksconf_package`:
  * Reduce amount of output produced during normal processing.  Use `-v` or `-vv` to get additional feedback.
  * Changed output `action` slightly.  Now using "unchanged" rather than "skipped".  This field has been added to the docs.

## Release 0.19.2 (2023-07-07)
* Disable `escape_backslashes` when using ansible-jinja templating mode.
  For example, this was causing some `\n` to come though as a literal value, instead of a newline.
* Update ksconf_app_sideload module's ksconf version check fail when ksconf is too old.  If it's just slightly old, a warning is issued.
* Updated requirements to drop the 'requests' library, which we don't use so I'm not sure how it got in there.

## Release 0.19.1 (2023-06-21)
* Fix minor import bug with shared module (possibly only impacting older version of Ansible?)
* Make find_splunk_home() heuristic slightly smarter.  It will now correctly skip over an empty splunk home and pick the correct one when multiple are present, but one is empty.
* Add `splunk-launch.conf` and `swidtag` output to the `splunk_facts` module.

## Release 0.19.0 (2023-06-15)
* Add Jinja2 template rendering support to the `ksconf_package` module.
* The `ksconf_package` module is now an "action" which means it has to be run from the controller.
  This allows access to all variables, which is not possible when run from the remote machine, as modules are.
* Add some validation for `.conf.j2` files; ensuring that they render to valid `.conf` files, and therefore avoid building broken files.
* Increase atomic file operations (mostly in the ksconf package; when using v0.11.5 or higher)

## Release 0.18.1 (2023-06-08)
* NO changes.  Re-uploading the same codebase to workaround issue with Ansible Galaxy where it apparently gets confused about beta releases.

## Release 0.18.0 (2023-06-08)
* First version of stateful deployment ready for wider use.
* NOTICE: Ksconf version 0.11.0 or later must be used. 
* Add read-the-docs docs support and various docs fixups.  See:  https://cdillc-splunk.readthedocs.io/

## Release 0.18.0-beta2 (2023-05-13)
* Completed first pass at adding stateful deployment to `ksconf_app_sideload`

## Release 0.18.0-beta1 (2023-05-13)
* Working towards stateful app deployment.  This enabled the ability to remove files that are no longer shipped with the app.
* Ksconf version 0.11.0 or later must be used.  Partial support for older versions was fully dropped (I'm not sure it ever was fully tested anyways).  Changes here were significant enough that being up-to-date is a must!
* More embracement of pathlib and f-strings!  We *must* have Python 3.7 for ksconf on controller and target, so there's no value in half-supporting Python 2.7 anywhere in this codebase.

## Release 0.17.1 (2023-05-13)
* Minor error handling improvements around json parsing.
* Add support for app detection under `peer-apps` and `slave-apps`
* Additional app.conf field mappings

## Release 0.17.0 (2023-03-23)
* Add app tracking support in `splunk_facts` module.

## Release 0.16.2 (2023-02-28)
* `splunk_cli` now supports `hidden_args` which allows things like `-secret` and `-remotePassword` to be passed in securely without being logged.
* Minor documentation improvements.

## Release 0.16.1 (2023-02-27)
* Minor improvements to `reltime_to_sec` to support weeks, months, and years & add to main README.

## Release 0.16.0 (2023-02-27)
* Add `reltime_to_sec` filter that will convert human a subset of Splunk's readable "relative time" format to seconds.
  For example `{{reltime_to_sec("7d")}}` will return `604800`
* Minor doc/example improvements
* Minor tweaks to argument handling for the `splunk_user` module.

## Release 0.15.1 (2023-02-14)
* Fixed typo in `splunk_rest_conf` module.

## Release 0.15.0 (2023-02-14)
* Minor improvements to `splunk_rest_conf` module.
  This includes a bug fix and some minor output enhancements during exceptions.

## Release 0.14.2 (2022-03-28)
Start of change log
