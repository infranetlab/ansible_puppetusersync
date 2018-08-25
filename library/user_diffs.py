""" Compute user diffs """

import pwd
from functools import reduce

from ansible.module_utils.basic import AnsibleModule


def run_module():
    """Run user_diff module."""
    # Synopsys
    # 1. load / prepare arguments and variables
    # 2. get the list of current users
    # 3. compute
    #    - users_to_add
    #    - users_to_delete
    # 4. return results

    #
    # 1. load/prepare arguemtns
    #
    argument_spec = dict(
        users=dict(required=True, type="dict"),
        target_uid_ranges=dict(required=True, type="list"),
        target_gids=dict(required=True, type="list"),
    )
    module = AnsibleModule(argument_spec=argument_spec)
    users = module.params['users']
    # Here we create a "big" set containing all valid uids
    target_uid_set = reduce(lambda a, b: a.union(range(b[0], b[1] + 1)),
                            module.params['target_uid_ranges'], set())
    target_gids = module.params['target_gids']

    warnings = []
    changed = False
    sync_lists = {}

    #  2. get the list of current users and uids
    curr_users = [x for x in pwd.getpwall() if x.pw_uid in target_uid_set]
    curr_uids = set([x.pw_uid for x in curr_users])

    # module.exit_json(changed=True, warnings=warnings,
    # sync_lists=[users, module.params['target_uid_ranges'], module.params['target_gids']] )

    # 3. compute lists
    target_users = [x for x in users.values() if x['gid']
                    in target_gids and x['uid'] in target_uid_set]
    target_uids = set([x['uid'] for x in target_users])

    uids_to_add = target_uids - curr_uids
    uids_to_delete = curr_uids - target_uids

    sync_lists['users_to_add'] = [
        x for x in target_users if x['uid'] in uids_to_add]
    sync_lists['users_to_delete'] = [
        {'name': x.pw_name, 'uid': x.pw_uid}
        for x in curr_users if x.pw_uid in uids_to_delete]

    # 4. return results
    changed = len(uids_to_add.union(uids_to_delete)) != 0
    module.exit_json(changed=changed, warnings=warnings,
                     sync_lists=sync_lists)


def main():
    run_module()


if __name__ == '__main__':
    main()
