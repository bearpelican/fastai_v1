
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################

from nb_004c import *

def pil2tensor(image, as_mask=False):
    arr = torch.ByteTensor(torch.ByteStorage.from_buffer(image.tobytes()))
    arr = arr.view(image.size[1], image.size[0], -1)
    arr = arr.permute(2,0,1).float()
    return arr if as_mask else arr.div_(255)

def open_image(fn, as_mask=False):
    x = PIL.Image.open(fn)
    if not as_mask: x = x.convert('RGB')
    return pil2tensor(x, as_mask=as_mask)

def image2np(image):
    res = image.cpu().permute(1,2,0).numpy()
    return res[...,0] if res.shape[2]==1 else res

def show_image(img, ax=None, figsize=(3,3), hide_axis=True, cmap='binary'):
    if ax is None: fig,ax = plt.subplots(figsize=figsize)
    ax.imshow(image2np(img), cmap=cmap)
    if hide_axis: ax.axis('off')

def _apply_tfm_func(pixel_func,lighting_func,affine_func,start_func, x, **kwargs):
    if not np.any([pixel_func,lighting_func,affine_func,start_func]): return x
    x = x.clone()
    if start_func is not None:  x = start_func(x)
    if affine_func is not None: x = affine_func(x, **kwargs)
    if lighting_func is not None: x = lighting_func(x)
    if pixel_func is not None: x = pixel_func(x)
    return x

def _apply_tfm_funcs(pixel_func,lighting_func,affine_func,start_func,
                     x, y=None, segmentation=False, **kwargs):
    x = _apply_tfm_func(pixel_func,lighting_func,affine_func,start_func, x, **kwargs)
    if y is None: return x

    if segmentation: lighting_func=None
    y = _apply_tfm_func(pixel_func, lighting_func,affine_func,start_func, y,
                         mode='nearest' if segmentation else 'bilinear', **kwargs)
    return x,y

import nb_003a
nb_003a._apply_tfm_funcs = _apply_tfm_funcs

@dataclass
class MatchedFilesDataset(Dataset):
    x_fns:List[Path]; y_fns:List[Path]
    def __post_init__(self): assert len(self.x_fns)==len(self.y_fns)
    def __repr__(self): return f'{type(self).__name__} of len {len(self.x_fns)}'
    def __len__(self): return len(self.x_fns)
    def __getitem__(self, i): return open_image(self.x_fns[i]), open_image(self.y_fns[i])

default_mean,default_std = map(tensor, ([0.5]*3, [0.5]*3))

class TfmDataset(Dataset):
    def __init__(self, ds:Dataset, tfms:Collection[Callable]=None,
                 do_tfm_y=False, smooth_y=True, **kwargs):
        self.ds,self.tfms,self.do_tfm_y,self.smooth_y,self.kwargs = ds,tfms,do_tfm_y,smooth_y,kwargs

    def __len__(self): return len(self.ds)

    def __getitem__(self,idx):
        x,y = self.ds[idx]
        if self.tfms is not None:
            tfm = apply_tfms(self.tfms)
            if self.do_tfm_y: x,y = tfm(x,y, self.smooth_y, **self.kwargs)
            else:             x   = tfm(x, **self.kwargs)
        return x,y

class Transforms():
    def __init__(self, tfms:Collection[Callable]=None, **kwargs):
        self.tfms,self.kwargs = tfms,kwargs

    def __call__(self, x):
        return x if self.tfms is None else apply_tfms(self.tfms)(x, **self.kwargs)

@dataclass
class TfmDataset(Dataset):
    ds:Dataset; x_tfms:Transforms=None; y_tfms:Transforms=None

    def __len__(self): return len(self.ds)

    def __getitem__(self,idx):
        x,y = self.ds[idx]
        return self.x_tfms(x),self.y_tfms(y)

class Darknet(nn.Module):
    def make_group_layer(self, ch_in, num_blocks, stride=1):
        return [conv_layer(ch_in, ch_in*2,stride=stride)
               ] + [(ResLayer(ch_in*2)) for i in range(num_blocks)]

    def __init__(self, num_blocks, num_classes, nf=32, custom_head=None):
        super().__init__()
        layers = [conv_layer(3, nf, ks=3, stride=1)]
        for i,nb in enumerate(num_blocks):
            layers += self.make_group_layer(nf, nb, stride=2-(i==1))
            nf *= 2
        layers += [nn.AdaptiveAvgPool2d(1), Flatten(), nn.Linear(nf, num_classes)
                  ] if custom_head is None else custom_head
        self.layers = nn.Sequential(*layers)

    def forward(self, x): return self.layers(x)