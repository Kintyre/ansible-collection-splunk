# Ansible Collection - cdi.splunk


Modules for the collection.

| Module | Description |
| ------ | ----------- |
| `ksconf_package` | Build a Splunk app package from a source app containing [ksconf](https://github.com/Kintyre/ksconf) layers.  Individual layers can be enabled or disabled based on ansible variables.  (This works for non-layered apps too.)  This module is idempotent, making it possible to conditionally roll out changes.  Use this instead of `command: ksconf package ...` |
| `splunk_cli` | Execute a `splunk` command locally or remotely (via a remote Splunkd URI). Unlike using the built-in `command` module, the `password` field alone is marked NO_LOG, so it's possible to see the rest of the command in the logs making troubleshooting easier and auditing more accurate.   Use this instead of `command: "{{splunk_home}}/bin/splunk ..."` |
| `splunk_control` | Use the REST API to stop/restart a running Splunk instance.  This may replace the use of `service`, but both options have advantages in specific use cases. |
| `splunk_facts` | Collect various facts about a Splunk installation.  Supports multiple instance by specifying the `splunk_home` or standard install locations will be checked. | |
| `splunk_rest_conf` | Manipulate various `.conf` files of a running Splunk instance over the REST API.  Use this instead of  `uri: url=https://localhost:8089/services/configs/conf-{type}/... ` |
| `splunk_user` | Manipulate local Splunk user accounts.  Add, delete, modify, or change password. |



## Testing

Until we get automatic testing working, here are some commands to do testing

Inventory file:
```
localhost ansible_connection=local splunk_home=~/splunk
```


```bash
ansible-galaxy collection install . --force


export SPLUNK_HOME=~/splunk
ansible -i inventory -m cdi.splunk.splunk_cli -a "splunk_home={{splunk_home}} cmd=version" all
ansible -i inventory -m cdi.splunk.splunk_control -a "state=restarted username=admin password=PASSWORD timeout=20" all

ansible -m cdi.splunk.ksconf_package -a "source=/data/repos/my_apps/kintyre-spl file=/tmp/kintyre-splunk-app.spl local=preserve" localhost

```