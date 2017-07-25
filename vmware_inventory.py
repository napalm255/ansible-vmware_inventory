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
import time
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
__version__ = '0.3.0'
__script__ = os.path.basename(__file__)
__path__ = os.path.dirname(os.path.realpath(__file__))
__config__ = '%s/%s' % (__path__, os.path.splitext(__script__)[0] + '.yml')
__log__ = '%s/%s' % (__path__, os.path.splitext(__script__)[0] + '.log')


# pylint: disable=too-few-public-methods, too-many-instance-attributes
class VMWareInventory(object):
    """VMWare Inventory Class."""

    def __init__(self, config, refresh=False):
        """Init."""
        self.path = __path__
        # initialize module parameters
        self.module = lambda: None
        setattr(self.module, 'params', dict())
        # initialize sane defaults
        self.module.params.update({'hostname': None,
                                   'username': None,
                                   'password': None,
                                   'clusters': None,
                                   'validate_certs': True,
                                   'caching': False,
                                   'cache_path': self.path,
                                   'cache_file': '.vminv.json',
                                   'cache_max_age': 300,
                                   'gather_vm_facts': False,
                                   'custom_values_groupby_keyval': True,
                                   'custom_values_groupby_val': list(),
                                   'custom_values_filters': None,
                                   'properties': [{'name': 'config.guestId',
                                                   'group': True}]})

        # initialize inventory
        self.inv = dict()
        self.inv.setdefault('_meta', dict(hostvars=dict()))

        # truth handling
        self.true_vals = ['true', 'yes', 'y', 1]
        self._str_to_bool = lambda x: True if x.lower() in self.true_vals else False

        # configuration handling
        self.config = config
        self.config_redacted = '*REDACTED*'
        self.config_prefix = 'vmware_'
        self.config_ints = ['cache_max_age']
        self.config_bools = ['validate_certs',
                             'caching',
                             'gather_vm_facts',
                             'custom_values_groupby_keyval']
        self.config_lists = ['clusters',
                             'properties',
                             'custom_values_filters',
                             'custom_values_groupby_val']
        self.config_required = ['hostname', 'username', 'password', 'clusters']
        self._load_config()
        self._validate_config()

        # cache handling
        self.caching = self.module.params.get('caching')
        self.cache = (self.module.params.get('cache_path').rstrip('/') + '/' +
                      self.module.params.get('cache_file'))
        self.cached = self._check_cache()
        self.refresh = refresh
        if self.refresh or not self.cached:
            self._delete_cache()
            self.cached = False

        # connect to vcenter
        self.content = self._connect()
        logging.debug('vcenter information:\n%s', self.content.about)

    def __enter__(self):
        """Enter."""
        # setup ctrl-c handler
        signal.signal(signal.SIGINT, self._signal_handler)
        return self

    # pylint: disable=redefined-builtin
    def __exit__(self, type, value, traceback):
        """Exit."""
        if self.caching and not self.cached:
            self._write_cache()

    def _connect(self):
        """Connect to vcenter and return content."""
        try:
            return vmware.connect_to_api(self.module)
        except socket.gaierror as ex:
            logging.critical('connection error\n%s', ex)
        except vim.fault.InvalidLogin as ex:
            logging.critical('authentication error\n%s', ex.msg)
        except AttributeError:
            logging.error('error connecting to vcenter')
        sys.exit(1)

    def _signal_handler(self, signum, frame):
        """Signal handler to catch Ctrl-C."""
        print()
        logging.critical('signum: %s, frame: %s', signum, frame)
        logging.critical('ctrl-c pressed. exiting.')
        logging.info('dumping inventory\n%s', json.dumps(self.inv, indent=4))
        sys.exit(255)

    def _load_config(self):
        """Load configuration from yaml or environment variables."""
        if os.path.isfile(__config__):
            logging.debug('loading configuration: %s', __config__)
            with open(__config__, 'r') as yaml_file:
                try:
                    self.module.params.update(yaml.load(yaml_file))
                except yaml.parser.ParserError as ex:
                    logging.debug('invalid syntax in %s\n%s', __config__, ex)

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
            # redact password for debug
            if key == 'password':
                value = self.config_redacted
            logging.debug('environment variable: %s = %s', key, value)

        for param in self.config_lists:
            if isinstance(self.module.params.get(param), str):
                self.module.params[param] = [self.module.params[param]]

        for param in self.config_ints:
            self.module.params[param] = int(self.module.params[param])

        # sort properties, prioritizing exclusions
        properties = sorted(self.module.params.get('properties', list()),
                            key=lambda k: ('exclude_if' not in k,
                                           k.get('exclude_if', None)))
        self.module.params['properties'] = properties

    def _validate_config(self):
        """Validate configuration."""
        try:
            for param, value in iteritems(self.module.params):
                if param in self.config_required:
                    assert value, '"%s" is not defined' % param
                if param in self.config_ints:
                    assert isinstance(value, int), '"%s" is not a integer' % param
                if param in self.config_bools:
                    assert isinstance(value, bool), '"%s" is not a boolean' % param
                if value is not None and param in self.config_lists:
                    assert isinstance(value, list), '"%s" is not a list.' % param
        except AssertionError as ex:
            logging.error(ex)
            sys.exit(1)

        validated_config = dict(self.module.params)
        # redact password for debug
        validated_config['password'] = self.config_redacted
        logging.debug('configuration validated:\n%s',
                      json.dumps(validated_config, indent=4))

    def _check_cache(self):
        """Check cache."""
        if self.module.params.get('caching'):
            if os.path.isfile(self.cache):
                now = time.time()
                limit = now - self.module.params.get('cache_max_age')
                ftime = os.path.getctime(self.cache)
                if ftime < limit:
                    logging.debug('cache is old. refreshing.')
                    return False
                return True
        return False

    def _load_cache(self):
        """Load cache."""
        the_cache = dict()
        logging.debug('loading cache: %s', self.cache)
        try:
            with open(self.cache) as cache:
                the_cache = cache.read()
            self.inv.update(json.loads(the_cache))
        except IOError as ex:
            logging.debug('error loading cache: %s', ex)

    def _write_cache(self):
        """Write cache."""
        logging.debug('writing cache: %s', self.cache)
        try:
            with open(self.cache, 'w') as cache:
                cache.write(json.dumps(self.inv, indent=4))
        except IOError as ex:
            logging.error('error writing cache: %s', ex)

    def _delete_cache(self):
        """Delete cache."""
        logging.debug('deleting cache: %s', self.cache)
        try:
            os.remove(self.cache)
        except OSError as ex:
            logging.debug('error deleting cache: %s', ex)

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
                if not self._get_vm_properties(vm_obj):
                    self.inv['_meta']['hostvars'].pop(vm_name)
                    continue

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
        excluded = False
        for prop in self.module.params.get('properties', list()):
            if isinstance(prop, str):
                prop = {'name': prop}
            parts = prop['name'].split('.')
            vm_prop = getattr(vm_obj, parts[0])
            for part in parts[1:]:
                vm_prop = getattr(vm_prop, part)
            # handle exclusions
            exclude = prop.get('exclude_if')
            if isinstance(exclude, str):
                if exclude.lower() == vm_prop.lower():
                    excluded = True
            elif exclude == vm_prop:
                excluded = True
            if excluded:
                logging.debug('excluded by property value: %s', vm_name)
                return False
            # group properties
            if prop.get('group'):
                group_name = vm_prop
                if prop.get('group_alias'):
                    group_name = prop.get('group_alias')
                # when property is boolean only group when true
                group_name = group_name.lower()
                self.inv.setdefault(group_name, list())
                if isinstance(vm_prop, bool) and vm_prop:
                    self.inv[group_name].append(vm_obj.config.name.lower())
                elif not isinstance(vm_prop, bool):
                    self.inv[group_name].append(vm_obj.config.name.lower())
            prop_key = parts[-1].lower()
            if isinstance(vm_prop, str):
                vm_prop = vm_prop.lower()
            self.inv['_meta']['hostvars'].setdefault(vm_name, dict())
            self.inv['_meta']['hostvars'][vm_name].update({prop_key: vm_prop})
            logging.debug('vm property: %s', {parts[-1]: vm_prop})
        return True

    def _get_customvalues(self, obj):
        """Get custom values."""
        filters = self.module.params.get('custom_values_filters')
        obj_name = obj.name.lower()
        cfm = self.content.customFieldsManager
        self.inv['_meta']['hostvars'][obj_name].setdefault('customvalues', dict())
        for value_obj in obj.summary.customValue:
            key = value_obj.key
            group_name = None
            if cfm is not None and cfm.field:
                for field in cfm.field:
                    if field.key == value_obj.key:
                        key = field.name
                        # Exit the loop immediately, we found it
                        break
            if filters and key not in filters:
                continue
            cval = {key.lower(): value_obj.value.lower()}
            self.inv['_meta']['hostvars'][obj_name]['customvalues'].update(cval)
            if key in self.module.params.get('custom_values_groupby_val'):
                group_name = value_obj.value.lower()
            elif self.module.params.get('custom_values_groupby_keyval'):
                group_name = '%s_%s' % (key.lower(), value_obj.value.lower())
            if group_name:
                self.inv.setdefault(group_name, list())
                self.inv[group_name].append(obj.config.name.lower())
                logging.debug('vm custom value (group name): %s', group_name)

    def _get_inventory(self):
        """Get inventory."""
        # loop through clusters
        for cluster in self.module.params.get('clusters', list):
            try:
                cluster_obj = self._get_cluster(cluster)
                assert cluster_obj is not None, 'invalid cluster name: %s' % cluster
                logging.debug('cluster name: %s', cluster)
            except AssertionError as ex:
                logging.error(ex)
                continue

            # loop through esxi hosts
            self.inv.setdefault('esxi', list())
            for host in cluster_obj.host:
                esxi_name = host.name.lower()
                esxi_ip = host.summary.managementServerIp
                self.inv['esxi'].append(esxi_name)
                self.inv['_meta']['hostvars'].setdefault(esxi_name, dict())
                self.inv['_meta']['hostvars'][esxi_name].update({'ansible_host': esxi_ip})
                self._get_customvalues(host)
                logging.debug('esxi host: %s', esxi_name)

                # get vms
                self._get_vms(host)

    def inventory(self):
        """Return inventory."""
        if self.caching:
            if not self.refresh and self.cached:
                self._load_cache()
            else:
                self._get_inventory()
        else:
            self._get_inventory()
        return self.inv


def main():
    """Entry point."""
    # pylint: disable = too-many-locals
    log_file, log_level = (None, logging.INFO)
    if '--debug' in sys.argv:
        log_level = logging.DEBUG
    if '--log' in sys.argv:
        log_file = __log__

    log_format = '%(levelname)s: %(message)s'
    logging.basicConfig(filename=log_file, level=log_level, format=log_format)

    logging.debug('%s %s v%s %s', '/' * 5, __title__, __version__, '\\' * 5)

    missing_requirements = False
    for req in [r for r in REQUIRED_MODULES if not REQUIRED_MODULES[r]]:
        logging.critical('missing required module: %s', req)
        missing_requirements = True
    if missing_requirements:
        sys.exit(1)

    refresh = False
    if '--refresh-cache' in sys.argv:
        logging.debug('forcing refresh of cache')
        refresh = True
    with VMWareInventory(__config__, refresh) as vminv:
        if '--list' in sys.argv:
            logging.debug('display list')
            print(json.dumps(vminv.inventory(), indent=4))
        elif '--host' in sys.argv:
            logging.debug('display host')
            logging.debug('not implemented.')
            print(json.dumps({}))


if __name__ == '__main__':
    main()
