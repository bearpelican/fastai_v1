
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################

import nb_002
from nb_002c import *

import operator
from random import sample
from torch.utils.data.sampler import Sampler

class FilesDataset(Dataset):
    def __init__(self, fns, labels, classes=None):
        if classes is None: classes = list(set(labels))
        self.classes = classes
        self.class2idx = {v:k for k,v in enumerate(classes)}
        self.fns = np.array(fns)
        self.y = [self.class2idx[o] for o in labels]
        
    def __len__(self): return len(self.fns)

    def __getitem__(self,i):
        x = Image.open(self.fns[i]).convert('RGB')
        return pil2tensor(x),self.y[i]
    
    @classmethod
    def from_folder(cls, folder, classes=None, test_pct=0.):
        if classes is None: classes = [cls.name for cls in find_classes(folder)]
            
        fns,labels = [],[]
        for cl in classes:
            fnames = get_image_files(folder/cl)
            fns += fnames
            labels += [cl] * len(fnames)
            
        if test_pct==0.: return cls(fns, labels)
        
        fns,labels = np.array(fns),np.array(labels)
        is_test = np.random.uniform(size=(len(fns),)) < test_pct
        return cls(fns[~is_test], labels[~is_test]), cls(fns[is_test], labels[is_test])

def affine_grid(x, matrix, size=None):
    h,w = x.shape[1:]
    if size is None: size=x.shape
    matrix[0,1] *= h/w; matrix[1,0] *= w/h
    return F.affine_grid(matrix[None,:2], torch.Size((1,)+size))

nb_002.affine_grid = affine_grid

@reg_transform
def pad(x, padding, mode='reflect') -> TfmType.Pixel:
    return F.pad(x[None], (padding,)*4, mode=mode)[0]

@reg_transform
def crop(x, size, row_pct:uniform, col_pct:uniform) -> TfmType.Final:
    size = listify(size,2)
    rows,cols = size
    row = int((x.size(1)-rows+1)*row_pct)
    col = int((x.size(2)-cols+1)*col_pct)
    return x[:, row:row+rows, col:col+cols]

TfmType = IntEnum('TfmType', 'Start Affine Coord Pixel Lighting Crop')

@reg_transform
def crop_pad(x, size, padding_mode='reflect',
             row_pct:uniform = 0.5, col_pct:uniform = 0.5) -> TfmType.Crop:
    size = listify(size,2)
    rows,cols = size
    if x.size(1)<rows or x.size(2)<cols:
        row_pad = max((rows-x.size(1)+1)//2, 0)
        col_pad = max((cols-x.size(2)+1)//2, 0)
        x = F.pad(x[None], (col_pad,col_pad,row_pad,row_pad), mode=padding_mode)[0]
    row = int((x.size(1)-rows+1)*row_pct)
    col = int((x.size(2)-cols+1)*col_pct)

    x = x[:, row:row+rows, col:col+cols]
    return x.contiguous() # without this, get NaN later - don't know why

def round_multiple(x, mult): return (int(x/mult+0.5)*mult)

def get_crop_target(target_px, target_aspect=1., mult=32):
    target_px = listify(target_px, 2)
    target_r = math.sqrt(target_px[0]*target_px[1]/target_aspect)
    target_c = target_r*target_aspect
    return round_multiple(target_r,mult),round_multiple(target_c,mult)

def get_resize_target(img, crop_target, do_crop=False):
    if crop_target is None: return None
    ch,r,c = img.shape
    target_r,target_c = crop_target
    ratio = (min if do_crop else max)(r/target_r, c/target_c)
    return ch,round(r/ratio),round(c/ratio)

def _apply_affine(img, size=None, padding_mode='reflect', do_crop=False, aspect=None, mult=32,
                  m=None, func=None, crop_func=None, **kwargs):
    if size is not None and not isinstance(size, (tuple,list)):
        size = listify(size,2) if aspect is None else get_crop_target(size, aspect, mult)
    if m is None and func is None and size is None: return img
    resize_target = get_resize_target(img, size, do_crop=do_crop)
    c = affine_grid(img, torch.eye(3), size=resize_target)
    if func is not None: c = func(c, img.size())
    if m is not None: c = affine_mult(c, img.new_tensor(m))
    res = grid_sample(img, c, padding_mode=padding_mode, **kwargs)
    if padding_mode=='zeros': padding_mode='constant'
    if crop_func is not None: res = crop_func(res, size=size, padding_mode=padding_mode)
    return res

def apply_affine(m=None, func=None, crop_func=None):
    return partial(_apply_affine, m=m, func=func, crop_func=crop_func)

nb_002.apply_affine = apply_affine

def affines_mat(matrices=None):
    if matrices is None or len(matrices) == 0: return None#Chaning here to return None instead of identity
    matrices = [FloatTensor(m) for m in matrices if m is not None]
    return reduce(torch.matmul, matrices, torch.eye(3))

nb_002.affines_mat = affines_mat

from nb_002 import _apply_tfm_funcs

def apply_tfms(tfms):
    grouped_tfms = dict_groupby(listify(tfms), lambda o: o.tfm_type)
    start_tfms,affine_tfms,coord_tfms,pixel_tfms,lighting_tfms,crop_tfms = [
        resolve_tfms(grouped_tfms.get(o)) for o in TfmType]
    lighting_func = apply_lighting(compose(lighting_tfms))
    affine_func = apply_affine(
        affines_mat(affine_tfms), func=compose(coord_tfms) if len(coord_tfms) != 0 else None, crop_func=compose(crop_tfms))
    return partial(_apply_tfm_funcs,
        compose(pixel_tfms),lighting_func,affine_func,compose(start_tfms))