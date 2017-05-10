#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Ansible VMWare Inventory.

Dynamic inventory for ansible.
"""

from __future__ import print_function
import signal
import logging
import os
import sys
import socket
import json
import yaml

REQUIRED_MODULES = dict()
try:
    from ansible.module_utils import vmware
    from ansible.module_utils.six import iteritems
    REQUIRED_MODULES['ansible'] = True
except ImportError:
    REQUIRED_MODULES['ansible'] = False

try:
    from pyVmomi import vim
    REQUIRED_MODULES['pyvmomi'] = True
except ImportError:
    REQUIRED_MODULES['pyvmomi'] = False

__title__ = 'Ansible VMWare Inventory'
__author__ = 'Brad Gibson'
__email__ = 'napalm255@gmail.com'
__version__ = '0.1.0'
__config__ = 'config.yml'


# pylint: disable=too-few-public-methods, too-many-instance-attributes
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
        self.config_true_values = ['true', 'yes', 1]
        self.config_prefix = 'vmware_'
        self.config_bools = ['validate_certs', 'gather_vm_facts',
                             'groupby_custom_values']
        self.config_lists = ['clusters', 'properties', 'custom_values_filters']
        self.config_required = ['hostname', 'username', 'password', 'clusters']
        self._load_config()
        logging.debug('module: %s', self.module.params)

        # connect to vcenter
        self.content = self._connect()
        logging.debug('content: %s', self.content.about)

    def __enter__(self):
        """Enter."""
        # setup ctrl-c handler
        signal.signal(signal.SIGINT, self._signal_handler)
        return self

    # pylint: disable=redefined-builtin
    def __exit__(self, type, value, traceback):
        """Exit."""

    def _connect(self):
        """Connect to vcenter and return content."""
        try:
            return vmware.connect_to_api(self.module)
        except socket.gaierror as ex:
            logging.error('connection error\n%s', ex)
        except vim.fault.InvalidLogin as ex:
            logging.error('authentication error\n%s', ex.msg)
        sys.exit(255)

    def _signal_handler(self, signum, frame):
        """Signal handler to catch Ctrl-C."""
        print()
        logging.error('signum: %s, frame: %s', signum, frame)
        logging.error('ctrl-c pressed. exiting.')
        logging.info('dumping output\n%s', json.dumps(self.inv, indent=4))
        sys.exit(255)

    def _str_to_bool(self, value):
        """Convert string to boolean."""
        return True if value in self.config_true_values else False

    def _load_config(self):
        """Load configuration from yaml or environment variables."""
        # define and load sane defaults
        sane_defaults = {'hostname': None,
                         'username': None,
                         'password': None,
                         'clusters': None,
                         'validate_certs': True,
                         'gather_vm_facts': False,
                         'groupby_custom_values': True,
                         'custom_values_filters': None,
                         'properties': None}
        self.module.params.update(sane_defaults)

        if os.path.isfile(__config__):
            logging.debug('loading configuration: %s', __config__)
            with open(__config__, 'r') as yaml_file:
                try:
                    self.module.params.update(yaml.load(yaml_file))
                except yaml.parser.ParserError as ex:
                    logging.debug('invalid syntax in config.yml\n%s', ex)

        # loop through environment variables starting with prefix
        for key, value in iteritems(os.environ):
            if self.config_prefix not in key.lower():
                continue

            key = key.lower().replace(self.config_prefix, '')
            if key in self.config_lists:
                if key == 'properties':
                    value = json.loads(value)
                else:
                    value = value.split(',')
                    value = [x.strip() for x in value]
            if key in self.config_bools:
                value = self._str_to_bool(value)

            self.module.params.update({key: value})
            logging.debug('environment variable: %s = %s', key, value)

        for param in self.config_lists:
            if isinstance(self.module.params.get(param), str):
                self.module.params[param] = [self.module.params[param]]

        self._validate_config()

    def _validate_config(self):
        """Validate configuration."""
        try:
            for param, value in iteritems(self.module.params):
                if param in self.config_required:
                    assert value, '"%s" is not defined' % param
                if param in self.config_bools:
                    assert isinstance(value, bool), '"%s" is not a boolean' % param
                if value is not None and param in self.config_lists:
                    assert isinstance(value, list), '"%s" is not a list.' % param
        except AssertionError as ex:
            logging.error(ex)
            sys.exit(255)

    def _get_cluster(self, cluster):
        """Find and return cluster by name."""
        return vmware.find_cluster_by_name(self.content, cluster)

    def _get_vms(self, host):
        """Get vms."""
        # loop through vms on host
        for vm_obj in host.vm:
            vm_name = vm_obj.config.name.lower()
            vm_ip = vm_obj.guest.ipAddress
            logging.debug('vm name: %s, ip: %s', vm_name, vm_ip)

            self.inv['_meta']['hostvars'].setdefault(vm_name, dict())
            if vm_ip:
                self.inv['_meta']['hostvars'][vm_name]['ansible_host'] = vm_ip

            if self.module.params.get('properties'):
                self._get_vm_properties(vm_obj)

            if self.module.params.get('groupby_custom_values'):
                self._get_customvalues(vm_obj)

            if self.module.params.get('gather_vm_facts'):
                facts = vmware.gather_vm_facts(self.content, vm_obj)
                # BUG: creation_time is not json serializable
                # issue is with vmware.gather_vm_facts
                # remove snapshot information from facts to bypass error
                facts.pop('snapshots', None)
                facts.pop('current_snapshot', None)
                self.inv['_meta']['hostvars'][vm_name] = facts
                logging.debug('vm facts: %s', json.dumps(facts, indent=4))

    def _get_vm_properties(self, vm_obj):
        """Get vm properties."""
        vm_name = vm_obj.config.name.lower()
        for prop in self.module.params.get('properties', list()):
            if isinstance(prop, str):
                prop = {'name': prop}
            parts = prop['name'].split('.')
            vm_prop = getattr(vm_obj, parts[0])
            for part in parts[1:]:
                vm_prop = getattr(vm_prop, part)
            if prop.get('group'):
                self.inv.setdefault(vm_prop, list())
                self.inv[vm_prop].append(vm_obj.config.name.lower())
            self.inv['_meta']['hostvars'][vm_name].update({parts[-1]: vm_prop})
            logging.debug('vm property: %s', {parts[-1]: vm_prop})

    def _get_customvalues(self, obj):
        """Get custom values."""
        filters = self.module.params.get('custom_values_filters')
        cfm = self.content.customFieldsManager
        # Resolve custom values
        for value_obj in obj.summary.customValue:
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
            self.inv[group_name].append(obj.config.name.lower())
            logging.debug('vm custom value: %s', group_name)

    def get_inventory(self):
        """Get inventory."""
        # loop through clusters
        for cluster in self.module.params.get('clusters', list):
            cluster_obj = self._get_cluster(cluster)
            logging.debug('cluster object: %s', cluster_obj)

            # loop through esxi hosts
            self.inv.setdefault('esxi', list())
            for host in cluster_obj.host:
                esxi_name = host.name.lower()
                esxi_ip = host.summary.managementServerIp
                self._get_customvalues(host)
                self.inv['esxi'].append(esxi_name)
                self.inv['_meta']['hostvars'].setdefault(esxi_name, dict())
                self.inv['_meta']['hostvars'][esxi_name].update({'ansible_host': esxi_ip})
                logging.debug('esxi host: %s', esxi_name)

                # get vms
                self._get_vms(host)


def main():
    """Entry point."""
    # pylint: disable = too-many-locals
    log_file, log_level = (None, logging.INFO)
    if '--debug' in sys.argv:
        log_level = logging.DEBUG

    log_format = '%(levelname)s: %(message)s'
    logging.basicConfig(filename=log_file, level=log_level, format=log_format)
    logging.debug('running %s', __file__)

    missing_requirements = False
    for req in [r for r in REQUIRED_MODULES if not REQUIRED_MODULES[r]]:
        logging.error('missing required module: %s', req)
        missing_requirements = True
    if missing_requirements:
        sys.exit(255)

    with VMWareInventory() as vminv:
        if '--list' in sys.argv:
            logging.debug('display list')
            vminv.get_inventory()
            print(json.dumps(vminv.inv, indent=4))
        elif '--host' in sys.argv:
            logging.debug('display host')
            logging.debug('not implemented.')
            print(json.dumps({}))


if __name__ == '__main__':
    main()
