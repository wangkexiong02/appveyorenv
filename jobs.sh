#!/bin/sh

sed -i -e "s/\$TRYSTACK_USER1/$TRYSTACK_USER1/g" keystone_trystack1
sed -i -e "s/\$TRYSTACK_PWD1/$TRYSTACK_PWD1/g" keystone_trystack1

sed -i -e "s/\$TRYSTACK_USER2/$TRYSTACK_USER2/g" keystone_trystack2
sed -i -e "s/\$TRYSTACK_PWD2/$TRYSTACK_PWD2/g" keystone_trystack2

sed -i -e "s/\$TRYSTACK_USER1/$TRYSTACK_USER1/g" clouds.yml
sed -i -e "s/\$TRYSTACK_USER2/$TRYSTACK_USER2/g" clouds.yml
sed -i -e "s/\$TRYSTACK_PWD1/$TRYSTACK_PWD1/g" clouds.yml
sed -i -e "s/\$TRYSTACK_PWD2/$TRYSTACK_PWD2/g" clouds.yml

TIME=`date +%s`
HOUR=`expr $TIME / 3600 % 24`

source keystone_trystack1 && nova delete beijing hangzhou huhhot
source keystone_trystack2 && nova delete master1-k8s worker1-k8s worker2-k8s

if [ $HOUR -eq 21 ]; then
  source keystone_trystack1 && nova delete beijing hangzhou huhhot
  source keystone_trystack2 && nova delete master1-k8s worker1-k8s worker2-k8s
fi

wget -T 10 -t 2 -qO- ftp://$BEIJING_DOMAIN > /dev/null || (
  # Redirect stdio to LOGFILE
  if [ "$LOGPATH" != "" ]; then
    exec 1>"$LOGPATH"
  fi

  # Repeat if SSH connection fail
  REPEAT=${SS_REPEAT:-3}

  # Create the necessary instances
  #
  for i in `seq $REPEAT`
  do
    ansible-playbook instances-create.yml
    if [ -f instances-create.retry ]
    then
      rm -rf instances-create.retry
    else
      break
    fi

    sleep 5
  done

  # Not enough public IPs, use SSH bastion for private IP connections
  chmod 400 roles/infrastructure/files/ansible_id*
  chmod +x scripts/*.py

  SSHFILE=~/.ssh/config
  SSHFILESIZE=0
  SSHFILEOK=False

  for i in `seq $REPEAT`
  do
    echo "Prepare SSH bastion configuration for $i time ..."
    python scripts/bastion.py --ucl --sshkey roles/infrastructure/files/ansible_id --refresh
    if [ -f $SSHFILE ]
    then
      SSHFILESIZE=`stat -c%s $SSHFILE`
      if [ $SSHFILESIZE -gt 0 ]
      then
        SSHFILEOK=True
        break
      fi
    fi

    sleep 5
  done

  if [ "$SSHFILEOK" == "True" ]
  then
    # Prepare the instances for ansible working
    #   - if no python installed, just DO IT
    #
    for i in `seq $REPEAT`
    do
      ansible-playbook -i scripts/openstack.py instances-prepare.yml --private-key=roles/infrastructure/files/ansible_id -T ${SSH_TIMEOUT:-60} 
      if [ -f instances-prepare.retry ]
      then
        rm -rf instances-prepare.retry
      else
        break
      fi

      sleep 5
    done

    # Setup instances with playbook
    #
    for i in `seq $REPEAT`
    do
      ansible-playbook -i scripts/openstack.py instances-setup.yml -T ${SSH_TIMEOUT:-60}
      if [ -f instances-setup.retry ]
      then
        rm -rf instances-setup.retry
      else
        break
      fi

      sleep 5
    done
  else
    echo "SSH bastion configuration failed ..."
  fi

  exec 1>&2
)
