# Ansible Collection - cdillc.splunk


Modules for the collection.

| Module | Description |
| ------ | ----------- |
| `ksconf_package` | Build a Splunk app package from a source app containing [ksconf](https://github.com/Kintyre/ksconf) layers.  Individual layers can be enabled or disabled based on ansible variables.  (This works for non-layered apps too.)  This module is idempotent, making it possible to conditionally roll out changes.  Use this instead of `command: ksconf package ...` |
| `ksconf_app_sideload` | Install a Splunk app from a tarball (`.tar.gz` or `.spl`) into a Splunk instance using a sideload technique.  The tarball is extracted into `apps` (where a normal "install" is suitable, or into management folders (i.e., `deployment-apps`, `manager-apps`, `shcluster/apps`) where Splunk provides no official install utility.  On the surface, this is similar to Ansible's `unarchive` module except with much better idempotent behavior; `unarchive` checks to see if the top-level destination folder exists, whereas this module can track installation version and checksum to determine when the archive should be expanded.  (Some of these features are a work in progress; at the moment this is *very* much like Ansible's `unarchive`)  (Please don't confuse this with `ksconf unarchive` which handles getting tarballs into a repository, not installing apps into a Splunk instance.) |
| `splunk_cli` | Execute a `splunk` command locally or remotely (via a remote Splunkd URI). Unlike using the built-in `command` module, the `password` field alone is marked NO_LOG, so it's possible to see the rest of the command in the logs making troubleshooting easier and auditing more accurate.   Use this instead of `command: "{{splunk_home}}/bin/splunk ..."` |
| `splunk_control` | Use the REST API to stop/restart a running Splunk instance.  This may replace the use of `service`, but both options have advantages in specific use cases. |
| `splunk_facts` | Collect various facts about a Splunk installation.  Supports multiple instance by specifying the `splunk_home` or standard install locations will be checked. | |
| `splunk_rest_conf` | Manipulate various `.conf` files of a running Splunk instance over the REST API.  Use this instead of  `uri: url=https://localhost:8089/services/configs/conf-{type}/... ` |
| `splunk_user` | Manipulate local Splunk user accounts.  Add, delete, modify, or change password. |


Filters for the collection

| Filter | Description |
| ------ | ----------- |
| `reltime_to_sec` | Convert a Splunk relative time string into seconds.  For example, in indexes.conf: `frozenTimePeriodInSecs = {{ "7d" \|  cdillc.splunk.reltime_to_sec }}`.  The suffixes `s`, `m`, `h`, `d`, `y` are supported. |

## Testing

Until we get automatic testing working, here are some commands to do testing

Inventory file:
```
localhost ansible_connection=local splunk_home=~/splunk
```


```bash
ansible-galaxy collection install . --force


export SPLUNK_HOME=~/splunk
ansible -i inventory -m cdillc.splunk.splunk_cli -a "splunk_home={{splunk_home}} cmd=version" all
ansible -i inventory -m cdillc.splunk.splunk_control -a "state=restarted username=admin password=PASSWORD timeout=20" all

ansible -m cdillc.splunk.ksconf_package -a "source=/data/repos/my_apps/kintyre-spl file=/tmp/kintyre-splunk-app.spl local=preserve" localhost
ansible -m cdillc.splunk.ksconf_app_sideload -a "src=/tmp/kintyre-splunk-app.spl dest=$SPLUNK_HOME/etc/apps list_files=true" localhost

ansible -m debug  -a 'msg="Keep day for {{ "7d" | cdillc.splunk.reltime_to_sec }} seconds"' localhost

ansible -i inventory -m cdillc.splunk.splunk_user -a "state=present splunk_user=new_user splunk_pass=anewpassword username=admin password=$SPLUNK_PASS roles=user" splunk

ansible -m cdillc.splunk.ksconf_app_sideload -a "src=splunk-ta-aws-5.0.0-e3e6808.spl dest=/opt/splunk/etc/deployment-apps" -b --become-user splunk --become-password-file x splunk -i inventory

ansible -m cdillc.splunk.splunk_facts splunk -i inventory -b --become-user splunk --become-password-file x
```