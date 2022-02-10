# Ansible Collection - cdi.splunk

Documentation for the collection.



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