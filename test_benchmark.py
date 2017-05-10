#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Performance testing of vmware_inventory."""

from __future__ import print_function
import subprocess
import os

try:
    import pytest
except ImportError:
    print('pytest not found.')
    exit(1)


def test_ansible_list_hosts(benchmark):
    """Test performance using ansible-playbook --list-hosts."""

    @benchmark
    def run():
        """Run test."""
        dir_path = os.path.dirname(os.path.realpath(__file__))
        play = '%s/test.yml' % dir_path
        inventory = '%s/vmware_inventory.py' % dir_path
        res = subprocess.call(['ansible-playbook', play, '-i', inventory, '--list-hosts'])
        return res

    assert run()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
