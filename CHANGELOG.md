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