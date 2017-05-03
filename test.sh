#!/usr/bin/env bash
#
# Helper script for loading environment variables in order to use config.yml
#
# This script needs to be sourced.
#
#

if [[ $_ != $0 ]]; then
  export VMWARE_HOSTNAME=$(read -p "Hostname: " && echo $REPLY)
  export VMWARE_USERNAME=$(read -p "Username: " && echo $REPLY)
  export VMWARE_PASSWORD=$(read -p "Password: " -s && echo $REPLY)
  echo
  export VMWARE_CLUSTERS=$(read -p "Cluster Name(s): " && echo $REPLY)
  export VMWARE_VALIDATE_CERTS=false
else
  echo "usage: source $_"
fi
