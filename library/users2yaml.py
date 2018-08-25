""" Convert users from puppet to yaml """

import os
import re
from contextlib import contextmanager
from functools import reduce

import yaml
from ansible.module_utils.basic import AnsibleModule

from parsley import makeGrammar


@contextmanager
def working_directory(path):
    current_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(current_dir)


def strip_comments(text):
    """Strip comments from text, note that it does not catch all cases, eg.
    it won't strip <<'blah # something  ' # comment >> """
    arr = []
    re_strip = re.compile("([^#]*)")
    for x in text.splitlines():
        res = re_strip.match(x).groups()
        # take lines like "blah  'corner # case '"
        # into consideration
        if '#' in x and res[0].count("'") == 1:
            arr.append(x)
            continue
        if not res[0]:
            continue
        arr.append(res[0])
    return '\n'.join(arr)


def run_module():
    # Synopsys
    #
    # 1. get arguments
    # 2. check / create destination directory
    # 3. load input
    # 4. parse it
    # 5. prepare output
    # 6. load previous output and look for changes
    # 7. write new output in case of changes
    # 8. return results

    # 1. get arguments
    argument_spec = dict(
        src_file=dict(required=True, type="str"),
        dst_dir=dict(required=True, type="str"),
        skip_absent=dict(required=False, type="bool", default=True),
        target_uid_ranges=dict(required=True, type="list"),
        target_gids=dict(required=False, type="list"),
        user_class=dict(required=False, type="str", default="user"),
        users_output_keyname=dict(required=False, type="str", default="target_users"),
        group_class=dict(required=False, type="str", default="group"),
        groups_output_keyname=dict(required=False, type="str", default="target_groups")
    )
    module = AnsibleModule(argument_spec=argument_spec)
    dst_dir = module.params['dst_dir']
    user_class = module.params['user_class']
    users_output_keyname = module.params['users_output_keyname']
    group_class = module.params['group_class']
    groups_output_keyname = module.params['groups_output_keyname']

    msg_arr = []  # collect some info messages

    # check input
    if not os.path.exists(module.params['src_file']):
        module.fail_json(msg="file not found: " + (module.params['src_file']))

    # Here we create a "big" set containing all valid uids
    target_uids = reduce(lambda a, b: a.union(range(b[0], b[1] + 1)),
                         module.params['target_uid_ranges'], set())

    target_gids = module.params['target_gids']

    # 2. check / create destination dir

    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)

    # 3. load input

    with open(module.params['src_file'], 'r') as f:
        text = strip_comments(f.read())

    # 4. parse it
    text = strip_comments(text)
    gid2group = {}
    groups = {}
    users = {}
    warnings = []
    changed = False

    grammar = r"""
    traverse       = klass
    klass          = ws 'class' ws  kname:x entity_open  kbody:y entity_close  -> (x,y)
    kbody          = (record:first (ws record)*:rest -> [first] + rest) | -> []
    entity_open    = ws '{' ws
    entity_close   = ws '}' ws
    kname          = <letter+ '::' letter+>:a -> a
    record         = ws '@' record_type:a entity_open quoted_string:b ws ':' key_value_list:c entity_close -> add_rec(a,b,c)
    record_type    = <letter+ '::' letter+ '::' letter+>:a -> a
    key_value      = ( key_value_int | key_value_gen )
    key_value_int  = ws <(('u'|'g')'id')>:k    ws '=>' ws quoted_digit:v -> (k,int(v))
    key_value_gen  = ws <string>:k ws '=>' ws value:v -> (k,v)
    key_value_list = (key_value:first ws  (ws ',' ws key_value)*:rest ws ','* -> [first]+rest) | -> []
    value          = (quoted_string|undef|true|false|v_class|<letterOrDigit+>|array):a -> a
    true           = 'true'  -> True
    false          = 'false' -> False
    undef          = 'undef' -> None
    array          = ('[' quoted_string:first ws (ws ',' ws quoted_string)*:rest ws ','* ws ']' -> [first]+rest) | -> []
    v_class        = <letterOrDigit+ '[' quoted_string ']'>:a -> a
    quoted_string  = "'" <(anything:x ?(x != "'"))*>:a "'" -> a
    quoted_digit   = "'"<digit+>:a"'" -> a
    string         = (letterOrDigit | '.' | ','|'_')+
    """

    def add_rec(rtype, name, attr_list):
        """Add records. Use to build the final output while traversing the
        parse tree."""
        # filter values
        attrs = dict(attr_list)
        if module.params['skip_absent'] and attrs.get('ensure') == 'absent':
            return
        if rtype == group_class:
            groups[name] = attrs
            groups[name]['name'] = name
            if attrs.get('gid'):
                gid2group[attrs['gid']] = name
        elif rtype == user_class:
            if int(attrs.get('uid')) in target_uids:
                users[name] = attrs
                users[name]['name'] = name

    parser = makeGrammar(grammar, {'add_rec': add_rec})
    parser(text).traverse()

    # 5. prepare output

    # Building output group_name -> { name: str, gid: int , users=[]}
    # - resolve group_name, sometimes we get the gid, but we need the name
    for k in sorted(users.keys()):
        group_name = users[k].get('gid')
        if not groups.get(group_name):
            group_name = gid2group.get(group_name)
        if not group_name:
            warnings.append("missing group name for user: %s" % k)
            continue

    # delete groups not in target_gids, if it were defined
    delete_list = []
    for group_name, group in groups.items():
        if (target_gids and group_name not in target_gids):
            delete_list.append(group_name)
    for group_name in delete_list:
        groups.pop(group_name)

    with working_directory(dst_dir):
        # 6. load previous output and look for changes
        changed = False
        for (dtype, data) in [(groups_output_keyname, groups), (users_output_keyname, users)]:
            fname = dtype + '.yml'
            prev_data = {}
            if os.path.isfile(fname):
                with open(fname, 'r') as f:
                    prev_data = yaml.load(f)

            # 7. write new output in case of changes
            if not prev_data or not prev_data.get(dtype):
                msg_arr.append("initialized %s" % dtype)
                changed = True
            elif prev_data[dtype] != data:
                changed = True
                prev_keys = set(prev_data[dtype].keys())
                curr_keys = set(data.keys())
                added_set = curr_keys - prev_keys
                removed_set = prev_keys - curr_keys

                if len(added_set) > 0:
                    msg_arr.append("added %s: %s" %
                                   (dtype, ", ".join(added_set)))
                if len(removed_set) > 0:
                    msg_arr.append("removed %s: %s" %
                                   (dtype, ", ".join(removed_set)))

            if changed:
                with open(fname, 'w') as f:
                    f.write(yaml.dump({dtype: data},
                                      default_flow_style=False,
                                      allow_unicode=True))
    # 8. return results
    module.exit_json(changed=changed, warnings=warnings,
                     msg="; ".join(msg_arr))


def main():
    run_module()

if __name__ == '__main__':
    main()
