#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Performance testing of vmware_inventory."""

import subprocess
import os
import pytest


def ansible_list_hosts():
    """Test performance using ansible-playbook --list-hosts."""
    dir_path = os.path.dirname(os.path.realpath(__file__))
    play = '%s/test.yml' % dir_path
    inventory = '%s/vmware_inventory.py' % dir_path
    subprocess.call(['ansible-playbook', play, '-i', inventory, '--list-hosts'])


def test_benchmarks(benchmark):
    """Benchmark tests."""
    benchmark(ansible_list_hosts)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
