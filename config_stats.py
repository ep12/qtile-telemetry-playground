import os
import sys
import ast
import importlib

from pprint import pprint
import functools

import astor

cproperty = getattr(functools, 'cached_property', property)

CONFIG_DIR = os.path.expanduser('~/.config/qtile')

EXCLUDE_ATTRS = {'_attributes', '_fields', 'col_offset', 'end_col_offset', 'end_lineno', 'lineno'}

ALLOWED_RAW_ITEMS = {'FileSize', 'LineCount', 'FunctionDef', 'ClassDef'}


# NOTE: the type of the value does not really matter, only `bool(value)` matters.
DEFAULT_DATA_COLLECTION_SETTINGS = {
    'recurse': True,  # will include user helper module path names
    'file_stats_items': {
        'FileSize': True,  # not critical
        'LineCount': True,  # not critical
        'Attribute': True,  # not critical
        'ClassDef': True,  # probably okay
        'Imports': True,  # maybe okay
        'HelperModules': True,  # maybe okay
        'FunctionDef': True,  # probably okay
    }
}


def config_path(*args):
    return os.path.join(CONFIG_DIR, *args)


def pdir(obj):
    return {x for x in dir(obj) if not x.startswith('__')} - EXCLUDE_ATTRS


def pdict(obj):
    return {a: getattr(obj, a) for a in pdir(obj)}


def attribute_node_to_str(node):
    return astor.to_source(node).rstrip()


class StatsVisitor(ast.NodeVisitor):

    def __init__(self, path: str = None, filesize: int = -1, linecount: int = -1,
                 settings: dict = DEFAULT_DATA_COLLECTION_SETTINGS):
        ast.NodeVisitor.__init__(self)
        self.sd = {
            'Path': path,
            'LineCount': linecount,
            'FileSize': filesize,
            'Import': {},
            'ImportFrom': {},
            'Attribute': {},
            'ClassDef': {},
            'FunctionDef': {},
        }
        self.settings = settings
        
    def visit_Import(self, node):
        for name_node in node.names:
            self.sd['Import'][name_node.name] = name_node.asname

    def visit_ImportFrom(self, node):
        key = (node.module, node.level)
        self.sd['ImportFrom'][key] = {}
        for name_node in node.names:
            self.sd['ImportFrom'][key][name_node.name] = name_node.asname

    def visit_Attribute(self, node):
        s = attribute_node_to_str(node)
        if s in self.sd['Attribute']:
            self.sd['Attribute'][s] += 1
        else:
            self.sd['Attribute'][s] = 1
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.sd['ClassDef'][node.name] = {
            'bases': list(map(attribute_node_to_str, node.bases)),
            'defs': [x.name for x in node.body if isinstance(x, ast.FunctionDef)],
        }
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        try:
            if node.args.args[0].arg == 'self':
                return
        except AttributeError:
            pass
        except IndexError:
            pass
        self.sd['FunctionDef'][node.name] = astor.to_source(node).count('\n')
        self.generic_visit(node)

    @cproperty
    def imported_modules(self):
        return (set(self.sd['Import'].keys())
                | set(map(lambda t: t[0], self.sd['ImportFrom'].keys())))

    @cproperty
    def imported_names(self):
        names = {}
        for k, v in self.sd['Import'].items():
            if k.startswith('libqtile'):
                names[k if v is None else v] = k
        for (k, _), v in self.sd['ImportFrom'].items():
            if k.startswith('libqtile'):
                for x, y in v.items():
                    names[x if y is None else y] = '%s.%s' % (k, x)
        return names

    def lookup_attribute(self, attr):
        for bound_name, real_name in self.imported_names.items():
            if attr.startswith(bound_name):
                return attr.replace(bound_name, real_name)
        return attr

    @cproperty
    def libqtile_attributes(self):
        d = {}
        for a, c in self.sd['Attribute'].items():
            real_name = self.lookup_attribute(a)
            if not real_name.startswith('libqtile'):
                continue
            d[real_name] = c
        return d

    @cproperty
    def stats(self):
        d = {k: v for k, v in self.sd.items() if k in ALLOWED_RAW_ITEMS}
        d['Attribute'] = self.libqtile_attributes
        d['Imports'] = self.imported_modules
        d['HelperModules'] = find_user_config_helper_modules(self.imported_modules)
        return {k: v for k, v in d.items()
                if self.settings.get('file_stats_items', {}).get(k, False)}


def find_user_config_helper_modules(module_names):
    not_found = set(filter(lambda m: importlib.util.find_spec(m) is None, module_names))
    # TODO: filter: only return those in the config dir
    return not_found


def handle_file(path: str, settings: dict = DEFAULT_DATA_COLLECTION_SETTINGS):
    with open(path) as f:
        data = f.read()
    file_ast = ast.parse(data, path)
    sv = StatsVisitor(path, os.stat(path).st_size, data.count('\n'), settings)
    sv.visit(file_ast)
    return sv


def find_module_spec(module_name: str, path=None):
    sys.path.append(path)
    s = importlib.util.find_spec(module_name)
    sys.path.pop()
    return s


def parse_config_files(settings: dict = DEFAULT_DATA_COLLECTION_SETTINGS):
    root = handle_file(config_path('config.py'), settings)
    d = {'~/.config/qtile/config.py': root}
    if settings.get('recurse', False) == True:
        # if not specified: be nice and default to False.
        unhandled = {x: config_path('config.py') for x in root.stats['HelperModules']}
        handled = set(config_path('config.py'))
        while unhandled:
            name, path = unhandled.popitem()
            spec = find_module_spec(name, os.path.dirname(path))
            if spec is None:
                continue
            path = spec.origin
            if path in handled:
                continue
            spath = path.replace(CONFIG_DIR, '~/.config/qtile')
            sv = d[spath] = handle_file(path, settings)
            for name in sv.stats['HelperModules']:
                unhandled[name] = path
            handled.add(path)
    return {k: v.stats for k, v in d.items()}

if __name__ == '__main__':
    import os
    data = parse_config_files()
    pprint(data)

    # when transmitting data:
    #  import json
    #  with open(cache_folder plus time stamp fd) as f:
    #      json.dump(data, f, indent=None, separators=(',', ':))
