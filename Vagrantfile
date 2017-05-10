Vagrant.configure("2") do |config|

  config.vm.define "virtualenv" do |virtualenv|
    virtualenv.vm.box = "bento/centos-6.8"
    virtualenv.vm.provision :ansible do |ansible|
      ansible.playbook = "vagrant_bootstrap.yml"
      ansible.verbose = true
    end
    virtualenv.vm.provision :shell do |shell|
      shell.inline = "pip install -r /vagrant/requirements_dev.txt"
    end
  end

end
