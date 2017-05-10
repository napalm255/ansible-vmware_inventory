Vagrant.configure("2") do |config|

  config.vm.define "virtualenv" do |virtualenv|
    virtualenv.vm.box = "bento/centos-6.8"
    virtualenv.vm.provision :ansible do |ansible|
      ansible.playbook = "vagrant_bootstrap.yml"
      ansible.verbose = true
    end
    virtualenv.vm.provision :shell do |shell|
      shell.inline = "source /home/vagrant/py26/bin/activate && pip install -r /vagrant/requirements_dev.txt"
    end
    virtualenv.vm.provision :shell do |shell|
      shell.inline = "source /home/vagrant/py27/bin/activate && pip install -r /vagrant/requirements_dev.txt"
    end
    # for those wthout ansible installed on their system you can swap out
    # to the shell script instead. it does less and is not as fancy but works.
    # comment out the above provisioning steps and uncomment the one below.
    #
    # virtualenv.vm.provision :shell do |shell|
    #   shell.path = "vagrant_bootstrap.sh"
    # end
  end

end
