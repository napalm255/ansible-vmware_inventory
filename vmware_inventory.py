#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ansible VMWare Inventory.

Dynamic inventory for ansible.
"""

from __future__ import print_function
import logging
import os
from sys import argv
import json
import yaml
from ansible.module_utils import vmware
# connect_to_api, gather_vm_facts, find_cluster_by_name

__title__ = 'VMWare Inventory'
__author__ = 'Brad Gibson'
__email__ = 'napalm255@gmail.com'
__version__ = '0.1.0'
__config__ = 'config.yml'

# for development purposes
if os.path.isfile('dev.yml'):
    __config__ = 'dev.yml'


# pylint: disable=too-few-public-methods
class VMWareInventory(object):
    """VMWare Inventory Class."""

    def __init__(self):
        """Init."""
        # initialize module parameters
        self.module = lambda: None
        setattr(self.module, 'params', dict())

        # initialize inventory
        self.inv = dict()
        self.inv.setdefault('_meta', dict(hostvars=dict()))

        # load configuration
        self.config_prefix = 'vmware_'
        self.config_lists = ['clusters', 'properties', 'custom_values_filters']
        self._load_config()
        logging.debug('module: %s', self.module)

        # connect to vcenter
        self.content = vmware.connect_to_api(self.module)
        logging.debug('content: %s', self.content)

    def __enter__(self):
        """Enter."""
        return self

    # pylint: disable=redefined-builtin
    def __exit__(self, type, value, traceback):
        """Exit."""

    def _load_config(self):
        """Load configuration from yaml or environment variables."""
        # define and load sane defaults
        sane_defaults = {'hostname': None,
                         'username': None,
                         'password': None,
                         'clusters': None,
                         'validate_certs': True,
                         'gather_facts': False,
                         'custom_values': True,
                         'custom_values_filters': None,
                         'properties': list()}
        self.module.params.update(sane_defaults)

        if os.path.isfile(__config__):
            logging.debug('loading configuration: %s', __config__)
            with open(__config__, 'r') as yaml_file:
                self.module.params.update(yaml.load(yaml_file))

        # loop through environment variables starting with prefix
        for key, value in os.environ.iteritems():
            if self.config_prefix not in key.lower():
                continue
            key = key.lower().replace(self.config_prefix, '')
            if key in self.config_lists:
                value = list(value.split(','))
            self.module.params.update({key: value})
            logging.debug('env: %s = %s', key, value)

        if isinstance(self.module.params.get('clusters'), str):
            self.module.params['clusters'] = list(self.module.params['clusters'])

        if isinstance(self.module.params.get('properties'), str):
            self.module.params['properties'] = list(self.module.params['properties'])

        self._validate_config()

    def _validate_config(self):
        """Validate configuration."""
        try:
            required_params = ['hostname', 'username', 'password', 'clusters']
            for param in required_params:
                assert self.module.params[param], '"%s" is not defined' % param
        except AssertionError as ex:
            logging.error(ex)
            exit()

    def _get_cluster(self, cluster):
        return vmware.find_cluster_by_name(self.content, cluster)

    def _get_vms(self, host):
        """Get vms."""
        # loop through vms on host
        for vm_obj in host.vm:
            vm_name = vm_obj.config.name.lower()
            vm_ip = vm_obj.guest.ipAddress
            logging.debug('name: %s, ip: %s', vm_name, vm_ip)

            self.inv['_meta']['hostvars'].setdefault(vm_name, dict())
            if self.module.params.get('gather_vm_facts', False):
                facts = vmware.gather_vm_facts(self.content, vm_obj)
                self.inv['_meta']['hostvars'][vm_name] = facts
                logging.debug('facts: %s', json.dumps(facts, indent=4))

            if self.module.params.get('properties'):
                self._get_vm_properties(vm_obj)

            if self.module.params.get('custom_values'):
                self._get_vm_customvalues(vm_obj)

    def _get_vm_properties(self, vm_obj):
        """Get vm properties."""
        for prop in self.module.params.get('properties', list()):
            parts = prop.split('.')
            vm_prop = getattr(vm_obj, parts[0])
            parts.pop(0)
            for part in parts:
                vm_prop = getattr(vm_prop, part)
            self.inv.setdefault(vm_prop, list())
            self.inv[vm_prop].append(vm_obj.config.name.lower())
            logging.debug('property: %s', vm_prop)

    def _get_vm_customvalues(self, vm_obj):
        """Get vm custom values."""
        filters = self.module.params['custom_values_filters']
        cfm = self.content.customFieldsManager
        # Resolve custom values
        for value_obj in vm_obj.summary.customValue:
            key = value_obj.key
            if cfm is not None and cfm.field:
                for field in cfm.field:
                    if field.key == value_obj.key:
                        key = field.name
                        # Exit the loop immediately, we found it
                        break
            if filters and key not in filters:
                continue
            group_name = '%s_%s' % (key, value_obj.value)
            self.inv.setdefault(group_name, list())
            self.inv[group_name].append(vm_obj.config.name.lower())
            logging.debug('custom value: %s', group_name)

    def get_inventory(self):
        """Get inventory."""
        logging.debug('getting inventory')

        # loop through clusters
        for cluster in self.module.params.get('clusters', list):
            cluster_obj = self._get_cluster(cluster)
            logging.debug('cluster object: %s', cluster_obj)

            # loop through esxi hosts
            self.inv.setdefault('esxi', list())
            for host in cluster_obj.host:
                self.inv['esxi'].append(host.name)
                self.inv['_meta']['hostvars'].setdefault(host.name, dict())
                logging.debug('esxi host: %s', host.name)

                # get vms
                self._get_vms(host)


def main():
    """Entry point."""
    # pylint: disable = too-many-locals
    log_file, log_level = (None, logging.INFO)
    if '--debug' in argv:
        log_level = logging.DEBUG

    log_format = '%(levelname)s: %(message)s'
    logging.basicConfig(filename=log_file, level=log_level, format=log_format)
    logging.debug('running %s', __file__)

    with VMWareInventory() as vminv:
        if '--list' in argv:
            logging.debug('Display list')
            vminv.get_inventory()
            print(json.dumps(vminv.inv))
            # print(json.dumps(inv, indent=4))
        elif '--host' in argv:
            logging.debug('Display host')
            # print(json.dumps({}))


if __name__ == '__main__':
    main()
