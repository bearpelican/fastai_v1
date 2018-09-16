
# use tools/build to autogenerate all relevant files automatically

import json, fire, re, os.path
from pathlib import Path

def is_export(cell):
    if cell['cell_type'] != 'code': return False
    src = cell['source']
    if len(src) == 0 or len(src[0]) < 7: return False
    #import pdb; pdb.set_trace()
    return re.match(r'^\s*#\s*export\s*$', src[0], re.IGNORECASE) is not None

def get_py_fname(fname):
    fname = os.path.splitext(fname)[0]
    number = fname.split('_')[0]
    return f'nb_{number}.py'

def notebook2script(fname):
    fname = Path(fname)
    fname_out = get_py_fname(fname.name)
    main_dic = json.load(open(fname,'r'))
    cells = main_dic['cells']
    code_cells = [c for c in cells if is_export(c)]
    module = f'''
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################
        # file to edit: dev_nb/{fname.name}\n\n'''
    for cell in code_cells: module += ''.join(cell['source'][1:]) + '\n\n'
    # remove trailing spaces
    module = re.sub(r' +$', '', module, flags=re.MULTILINE)
    with open(fname_out,'w') as f: f.write(module[:-2])
    print(f"Converted {fname} to {fname_out}")

if __name__ == '__main__': fire.Fire(notebook2script)
