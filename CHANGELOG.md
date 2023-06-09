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
