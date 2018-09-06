
        #################################################
        ### THIS FILE WAS AUTOGENERATED! DO NOT EDIT! ###
        #################################################

from nb_004c import *

def uniform_int(low, high, size=None):
    return random.randint(low,high) if size is None else torch.randint(low,high,size)

@TfmPixel
def dihedral(x, k:partial(uniform_int,0,8)):
    flips=[]
    if k&1: flips.append(1)
    if k&2: flips.append(2)
    if flips: x = torch.flip(x,flips)
    if k&4: x = x.transpose(1,2)
    return x.contiguous()

def get_transforms(do_flip=False, flip_vert=False, max_rotate=0., max_zoom=1., max_lighting=0., max_warp=0.,
                   p_affine=0.75, p_lighting=0.5, xtra_tfms=None):
    res = [rand_crop()]
    if do_flip:    res.append(dihedral() if flip_vert else flip_lr(p=0.5))
    if max_warp:   res.append(symmetric_warp(magnitude=(-max_warp,max_warp), p=p_affine))
    if max_rotate: res.append(rotate(degrees=(-max_rotate,max_rotate), p=p_affine))
    if max_zoom>1: res.append(rand_zoom(scale=(1.,max_zoom), p=p_affine))
    if max_lighting:
        res.append(brightness(change=(0.5*(1-max_lighting), 0.5*(1+max_lighting)), p=p_lighting))
        res.append(contrast(scale=(1-max_lighting, 1/(1-max_lighting)), p=p_lighting))
    #       train                   , valid
    return (res + listify(xtra_tfms), [crop_pad()])

def transform_datasets(train_ds, valid_ds, tfms, size=None):
    return (DatasetTfm(train_ds, tfms[0], size=size),
            DatasetTfm(valid_ds, tfms[1], size=size))

class AdaptiveConcatPool2d(nn.Module):
    def __init__(self, sz=None):
        super().__init__()
        sz = sz or 1
        self.ap,self.mp = nn.AdaptiveAvgPool2d(sz), nn.AdaptiveMaxPool2d(sz)
    def forward(self, x): return torch.cat([self.mp(x), self.ap(x)], 1)

def create_skeleton(model, cut):
    layers = list(model.children())[:-cut] if cut else [model]
    layers += [AdaptiveConcatPool2d(), Flatten()]
    return nn.Sequential(*layers)

def num_features(m):
    c=list(m.children())
    if len(c)==0: return None
    for l in reversed(c):
        if hasattr(l, 'num_features'): return l.num_features
        res = num_features(l)
        if res is not None: return res

def bn_dp_lin(n_in, n_out, bn=True, dp=0., actn=None):
    layers = [nn.BatchNorm1d(n_in)] if bn else []
    if dp != 0: layers.append(nn.Dropout(dp))
    layers.append(nn.Linear(n_in, n_out))
    if actn is not None: layers.append(actn)
    return layers

def create_head(nf, nc, lin_ftrs=None, dps=None):
    lin_ftrs = [nf, 512, nc] if lin_ftrs is None else [nf] + lin_ftrs + [nc]
    if dps is None: dps = [0.25] * (len(lin_ftrs)-2) + [0.5]
    actns = [nn.ReLU(inplace=True)] * (len(lin_ftrs)-2) + [None]
    layers = []
    for ni,no,dp,actn in zip(lin_ftrs[:-1],lin_ftrs[1:],dps,actns):
        layers += bn_dp_lin(ni,no,True,dp,actn)
    return nn.Sequential(*layers)

class ConvLearner(Learner):
    def __init__(self, data, arch, cut, pretrained=True, lin_ftrs=None, dps=None, **kwargs):
        self.skeleton = create_skeleton(arch(pretrained), cut)
        nf = num_features(self.skeleton) * 2
        # XXX: better way to get num classes
        self.head = create_head(nf, len(data.train_ds.ds.classes), lin_ftrs, dps)
        model = nn.Sequential(self.skeleton, self.head)
        super().__init__(data, model, **kwargs)

    def freeze_to(self, n):
        for g in self.layer_groups[:n]:
            for p in g.parameters(): p.requires_grad = False
        for g in self.layer_groups[n:]:
            for p in g.parameters(): p.requires_grad = True

    def freeze(self): self.freeze_to(-1)
    def unfreeze(self): self.freeze_to(0)

bn_types = (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d)

def set_bn_eval(m):
    for l in m.children():
        set_bn_eval(l)
        if isinstance(l, bn_types) and not next(l.parameters()).requires_grad:
            l.eval()

@dataclass
class BnFreeze(Callback):
    learn:Learner
    def on_train_begin(self, **kwargs): set_bn_eval(self.learn.model)