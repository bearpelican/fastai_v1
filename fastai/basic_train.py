from .imports.core import *
from .imports.torch import *
from .data import DataBunch
from .callback import OptimWrapper, CallbackHandler, Recorder

def loss_batch(model:nn.Module, xb:tensor, yb:tensor, loss_fn:Callable, opt:OptimWrapper=None, 
               cb_handler:CallbackHandler=None, metrics:Collection[Callable]=None):
    if cb_handler is None: cb_handler = CallbackHandler([])
    out = model(xb)
    out = cb_handler.on_loss_begin(out)
    loss = loss_fn(out, yb)
    mets = [f(out,yb).item() for f in metrics] if metrics is not None else []
    
    if opt is not None:
        loss = cb_handler.on_backward_begin(loss)
        loss.backward()
        cb_handler.on_backward_end()
        opt.step()
        cb_handler.on_step_end()
        opt.zero_grad()
        
    return (loss.item(),) + tuple(mets) + (len(xb),)

def fit(epochs:int, model:nn.Module, loss_fn:Callable, opt:OptimWrapper, data:DataBunch, 
        callbacks:Collection[Callable]=None, metrics:Collection[Callable]=None):
    cb_handler = CallbackHandler(callbacks)
    cb_handler.on_train_begin()
    
    for _ in tnrange(epochs):
        model.train()
        cb_handler.on_epoch_begin()
        
        for xb,yb in data.train_dl:
            xb, yb = cb_handler.on_batch_begin(xb, yb)
            loss,_ = loss_batch(model, xb, yb, loss_fn, opt, cb_handler)
            if cb_handler.on_batch_end(loss): break
        
        if hasattr(data,'valid_dl') and data.valid_dl is not None:
            model.eval()
            with torch.no_grad():
                *val_metrics,nums = zip(*[loss_batch(model, xb, yb, loss_fn, cb_handler=cb_handler, metrics=metrics)
                                for xb,yb in data.valid_dl])
            val_metrics = [np.sum(np.multiply(val,nums)) / np.sum(nums) for val in val_metrics]
            
        else: val_metrics=None
        if cb_handler.on_epoch_end(val_metrics): break
        
    cb_handler.on_train_end()

@dataclass
class Learner():
    data: DataBunch
    model: nn.Module
    opt_fn: Callable = optim.SGD
    loss_fn: Callable = F.cross_entropy
    metrics: Collection[Callable] = None
    true_wd: bool = False
    def __post_init__(self): 
        self.model = self.model.to(self.data.device)
        self.callbacks = []

    def fit(self, epochs, lr, wd=0., callbacks=None):
        if not hasattr(self, 'opt'): self.create_opt(lr, wd)
        if callbacks is None: callbacks = []
        callbacks = self.callbacks + callbacks
        fit(epochs, self.model, self.loss_fn, self.opt, self.data, callbacks=callbacks, metrics=self.metrics)
    
    def create_opt(self, lr, wd=0.):
        self.opt = OptimWrapper(self.opt_fn(self.model.parameters(), lr), wd=wd, true_wd=self.true_wd)
        self.recorder = Recorder(self.opt, self.data.train_dl)
        self.callbacks = [self.recorder] + self.callbacks