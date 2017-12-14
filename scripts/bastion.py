#!/usr/bin/env python

# Copyright (c) 2016, wangkexiong <wangkexiong@gmail.com>

import os
import sys
import argparse
import shade
import os_client_config
import yaml

from string import Template

from openstack import CONFIG_FILES
from openstack import get_host_groups

try:
    import json
except:
    import simplejson as json


def build_bastion(sshconfig, sshkey, groups):
    interface_template = Template('''
Host $publicIP
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null

Host $host
  Hostname $publicIP
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
''')

    host_template1 = Template('''
Host $privateIP
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
  ProxyCommand ssh $publicIP -l $user -W %h:%p
  IdentityFile $sshkey

Host $host
  Hostname $privateIP
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
  ProxyCommand ssh $publicIP -l $user -W %h:%p
  IdentityFile $sshkey
''')

    host_template2 = Template('''
Host $privateIP
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
  ProxyCommand ssh $publicIP -l $user -W %h:%p

Host $host
  Hostname $privateIP
  StrictHostKeyChecking no
  UserKnownHostsFile=/dev/null
  ProxyCommand ssh $publicIP -l $user -W %h:%p
''')

    f = open(sshconfig, 'w')
    publicIP = {}
    user = {}

    groups_dict = json.loads(groups)
    if '_meta' in groups_dict and 'hostvars' in groups_dict['_meta']:
        hostvars = groups_dict['_meta']['hostvars']

        for x in hostvars:
            if 'openstack' in hostvars[x]:
                para = hostvars[x]['openstack']

                if 'interface_ip' in para \
                        and para['interface_ip'] != '' \
                        and para['cloud'] not in publicIP \
                        and 'metadata' in para \
                        and 'ansible_host_user' in para['metadata']:
                    cloud = para['cloud']
                    publicIP[cloud] = para['interface_ip']
                    user[cloud] = para['metadata']['ansible_host_user']

                    output = interface_template.safe_substitute(
                        dict(host=para['human_id'],
                             publicIP=para['interface_ip'])
                    )
                    f.write(output)

        if len(publicIP.keys()) > 0:
            for y in hostvars:
                if 'openstack' in hostvars[y]:
                    para = hostvars[y]['openstack']

                    if 'interface_ip' not in para \
                            or ('interface_ip' in para and para['interface_ip'] == ''):
                        cloud = para['cloud']
                        privateIP = para['private_v4']

                        if sshkey is not None:
                            output = host_template1.safe_substitute(
                                dict(publicIP=publicIP[cloud],
                                     privateIP=privateIP,
                                     host=para['human_id'],
                                     user=user[cloud],
                                     sshkey=sshkey)
                            )
                        else:
                            output = host_template2.safe_substitute(
                                dict(publicIP=publicIP[cloud],
                                     privateIP=privateIP,
                                     host=para['human_id'],
                                     user=user[cloud])
                            )

                        f.write(output)
        else:
            print "No floating IP or ansible_host_user not in metadata"
    else:
        print "No Groups information got from HTTP connection, Bad Cache?"

    f.close()


def build_sshconfig(overwrite):
    sshconfig = os.path.expanduser('~')+os.sep+'.ssh'+os.sep+'config'

    if os.path.exists(sshconfig) and not overwrite:
        print '~/.ssh/config already exists, backup and run with --ucl'
        return None
    else:
        return sshconfig


def build_sshkey(keyfile):
    if keyfile is not None:
        if os.path.exists(keyfile):
            return os.path.realpath(keyfile)
        else:
            print '%s does not exist, plz check' % keyfile
            return None


def parse_args():
    parser = argparse.ArgumentParser(description='Build SSH config for Bastion')

    parser.add_argument('--refresh', action='store_true',
                        help='Refresh cached information')
    parser.add_argument('--debug', action='store_true', default=False,
                        help='Enable debug output')
    parser.add_argument('--sshkey',
                        help='Private key using for servers behind Bastion')
    parser.add_argument('--ucl', action='store_true',
                        help='Overwrite SSH config file unconditionly')

    return parser.parse_args()


def store_group_vars(groups):
    result = {}

    group_info = json.loads(groups)
    if group_info and isinstance(group_info, dict):
        if '_meta' in group_info:
            if 'hostvars' in group_info['_meta']:
                for host, config in group_info['_meta']['hostvars'].items():
                    if 'openstack' in config:
                        op_info = config['openstack']
                        if 'private_v4' in op_info and 'human_id' in op_info:
                            cloud = op_info['cloud']
                            private_ipv4 = op_info['private_v4']
                            name = op_info['human_id']

                            if cloud != 'envvars':
                                if cloud not in result:
                                    result[cloud] = {}

                                host_info = result[cloud]
                                host_info[name] = private_ipv4

    if not os.path.exists('group_vars'):
        os.mkdir('group_vars')
    with open('group_vars/cloud_host.yml', 'w') as group_file:
        group_file.write(yaml.safe_dump(result, default_flow_style=False))


def main():
    args = parse_args()
    try:
        config_files = os_client_config.config.CONFIG_FILES + CONFIG_FILES
        shade.simple_logging(debug=args.debug)
        inventory_args = dict(
            refresh=args.refresh,
            config_files=config_files,
        )
        if hasattr(shade.inventory.OpenStackInventory, 'extra_config'):
            inventory_args.update(dict(
                config_key='ansible',
                config_defaults={
                    'use_hostnames': False,
                    'expand_hostvars': True,
                }
            ))

        inventory = shade.inventory.OpenStackInventory(**inventory_args)

        sshconfig = build_sshconfig(args.ucl)
        sshkey = build_sshkey(args.sshkey)

        if (sshconfig is not None):
            infor = get_host_groups(inventory, refresh=args.refresh)

            build_bastion(sshconfig, sshkey, infor)
            store_group_vars(infor)

    except shade.OpenStackCloudException as e:
        sys.stderr.write('%s\n' % e.message)
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
