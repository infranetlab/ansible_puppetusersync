infranetlab.puppetusersync
==========================

An ansible role to synchronize users and groups defined in puppet to ansible.


Requirements
------------

    pip3 install python-parsely

Role Variables
--------------

Please see  defaults/main.yml

Dependencies
------------

No role dependencies.

Example Playbook
----------------

    - name: Import myusers.pp
      include_role:
        name: infranetlab.puppetusersync
        tasks_from: import_puppet_users.yml
      vars:
        usync_puppet_user_class: "user"
        usync_puppet_group_class: "group"
        usync_target_uid_ranges:  
          - [1000, 1050]
          - [2000, 2010]
        usync_target_gids:
          - group1
          - group2
        usync_skip_absent: yes
        usync_puppet_src_file: myusers.pp
        usync_export_dir: "var/user_db/"

    - name: User sync
      include_role:
        name: infranetlab.puppetusersync
      vars:
        usync_target_uid_ranges:  
        usync_target_gids: "{{ user_db.target_gids }}"
        usync_target_uid_ranges:  
          - [1000, 1050]
          - [2000, 2010]
        usync_target_gids:
          - group1
          - group2
        usync_export_dir: "var/user_db/"


License
-------

MIT
