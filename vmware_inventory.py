#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ansible VMWare Inventory.

Dynamic inventory for ansible.
"""

from __future__ import print_function
import logging
from sys import argv
import json
import yaml
from ansible.module_utils.vmware import connect_to_api, gather_vm_facts
from ansible.module_utils.vmware import find_cluster_by_name

__title__ = 'VMWare Inventory'
__author__ = 'Brad Gibson'
__email__ = 'napalm255@gmail.com'
__version__ = '0.1.0'
__config__ = 'config.yml'


def main():
    """Entry point."""
    # pylint: disable = too-many-locals
    log_file, log_level = (None, logging.INFO)
    if '--debug' in argv:
        log_level = logging.DEBUG

    log_format = '%(levelname)s: %(message)s'
    logging.basicConfig(filename=log_file, level=log_level, format=log_format)
    logging.debug('running %s', __file__)

    def module():
        """Mock module."""
        return lambda: None

    with open(__config__, 'r') as yaml_file:
        setattr(module, 'params', yaml.load(yaml_file))

    content = connect_to_api(module)
    logging.debug(content)
    # pylint: disable = no-member
    cluster = find_cluster_by_name(content, module.params['cluster'])
    logging.debug(cluster)

    inv = dict()
    inv.setdefault('_meta', dict(hostvars=dict()))
    inv.setdefault('esxi', list())
    # pylint: disable = too-many-nested-blocks
    for host in cluster.host:
        logging.debug('esxi host: %s', host.name)
        inv['esxi'].append(host.name)
        for vm_obj in host.vm:
            vm_name = vm_obj.config.name.lower()
            vm_ip = vm_obj.guest.ipAddress
            logging.debug('name: %s, ip: %s', vm_name, vm_ip)

            inv['_meta']['hostvars'].setdefault(vm_name, dict())
            if module.params['gather_vm_facts']:
                inv['_meta']['hostvars'][vm_name] = gather_vm_facts(content, vm_obj)

            for prop in module.params['properties']:
                parts = prop.split('.')
                vm_prop = getattr(vm_obj, parts[0])
                parts.pop(0)
                for part in parts:
                    vm_prop = getattr(vm_prop, part)
                inv.setdefault(vm_prop, list())
                inv[vm_prop].append(vm_name)

            cfm = content.customFieldsManager
            # Resolve custom values
            for value_obj in vm_obj.summary.customValue:
                key = value_obj.key
                if cfm is not None and cfm.field:
                    for field in cfm.field:
                        if field.key == value_obj.key:
                            key = field.name
                            # Exit the loop immediately, we found it
                            break
                group_name = '%s_%s' % (key, value_obj.value)
                inv.setdefault(group_name, list())
                inv[group_name].append(vm_name)

    if '--list' in argv:
        logging.debug('Display list')
        print(json.dumps(inv))
    elif '--host' in argv:
        logging.debug('Display host')
        print(json.dumps({}))


if __name__ == '__main__':
    main()
