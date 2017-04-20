#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ansible VMWare Inventory

Dynamic inventory for ansible.
"""

from __future__ import print_function
import logging
from sys import argv
import json
import yaml
from ansible.module_utils.vmware import connect_to_api, gather_vm_facts
from ansible.module_utils.vmware import find_vm_by_name, find_cluster_by_name
from ansible.module_utils.vmware import wait_for_task

__title__ = 'VMWare Inventory'
__author__ = 'Brad Gibson'
__email__ = 'napalm255@gmail.com'
__version__ = '0.1.0'
__config__ = 'config.yml'


def main():
    """Entry point."""
    log_file, log_level = (None, logging.INFO)
    if '--debug' in argv:
        log_level = logging.DEBUG

    log_format = '%(levelname)s: %(message)s'
    logging.basicConfig(filename=log_file, level=log_level, format=log_format)
    logging.debug('running %s', __file__)

    the_list = {}

    def module():
        """Mock module."""
        return lambda: None

    with open(__config__, 'r') as yaml_file:
        setattr(module, 'params', yaml.load(yaml_file))

    content = connect_to_api(module)
    logging.debug(content)
    cluster = find_cluster_by_name(content, module.params['cluster'])
    logging.debug(cluster)
    for host in cluster.host:
        logging.debug(host.name)
        for vm in host.vm:
            logging.debug(vm.name)
            facts = dict()
            facts['uuid'] = vm.summary.config.uuid
            facts['name'] = vm.summary.config.name
            facts['guestId'] = vm.summary.config.guestId
            facts['hostname'] = vm.summary.guest.hostName
            facts['ipaddress'] = vm.summary.guest.ipAddress
            facts['customvalues'] = dict()
            cfm = content.customFieldsManager
            # Resolve custom values
            for value_obj in vm.summary.customValue:
                key = value_obj.key
                if cfm is not None and cfm.field:
                    for field in cfm.field:
                        if field.key == value_obj.key:
                            key = field.name
                            # Exit the loop immediately, we found it
                            break
                facts['customvalues'][key] = value_obj.value
            logging.debug(facts)

    if '--list' in argv:
        logging.debug('Display list')
        print(json.dumps(the_list))
    elif '--host' in argv:
        logging.debug('Display host')
        print(json.dumps({}))


if __name__ == '__main__':
    main()
