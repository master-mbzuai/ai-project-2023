from micromind import MicroMind
from micromind.networks import PhiNet

import torch
import torch.nn as nn

model_path = "./pretrained/finetuned/baseline.ckpt"

if torch.cuda.is_available():
    device = torch.device("cuda:0")
    print("Running on the GPU")
elif torch.backends.mps.is_available: 
    device = torch.device("mps")
    print("Running on the MPS")
else:
    device = torch.device("cpu")
    print("Running on the CPU")

class ImageClassification(MicroMind):

    # test 1 with n as input vector size and m classes custom d
    # n has to be calculated from the output of the neural network of the feature extractor

    def __init__(self, *args, inner_layer_width = 10, **kwargs):
        super().__init__(*args, **kwargs)

        self.alpha = 1/inner_layer_width

        print(self.alpha)

        self.input = 344
        self.output = 10

        self.lasso = nn.Parameter(torch.rand(self.input), requires_grad=True).to(device)
        self.lasso.requires_grad_ = True

        # alpha: 0.9
        # beta: 0.5
        # num_classes: 1000
        # num_layers: 7
        # t_zero: 4.0

        self.modules["feature_extractor"] = PhiNet(
            input_shape=(3, 240, 240),
            alpha=0.9,
            num_layers=7,
            beta=0.5,
            t_zero=4.0,
            include_top=False,
            num_classes=100,
            compatibility=False,
            divisor=8,
            downsampling_layers=[4,5,7]
        )

        # Taking away the classifier from pretrained model
        pretrained_dict = torch.load(model_path, map_location=device)  

        #loading the new model
        self.modules["feature_extractor"].load_state_dict(pretrained_dict["feature_extractor"])        
        for _, param in self.modules["feature_extractor"].named_parameters():                
            param.requires_grad = False

        self.modules["flattener"] = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten()
        )

        self.modules["classifier"] = nn.Sequential(   
                nn.Linear(in_features=self.input, out_features=self.output)      
        )

    def forward(self, batch):     

        feature_vector = self.modules["feature_extractor"](batch[0])                      
        x = self.modules["flattener"](feature_vector)
        x = torch.mul(x, self.lasso) # we need to add this as a computation complexity
        x = self.modules["classifier"](x)
        return x
       
    def compute_loss(self, pred, batch):        
        lasso_loss = self.lasso.abs().sum() * self.alpha
        cross_loss = nn.CrossEntropyLoss()(pred, batch[1])
        return lasso_loss + cross_loss
    
    def configure_optimizers(self):
        """Configures and defines the optimizer for the task. Defaults to adam
        with lr=0.001; It can be overwritten by either passing arguments from the
        command line, or by overwriting this entire method.

        Returns
        ---------
            Optimizer and learning rate scheduler
            (not implemented yet). : Tuple[torch.optim.Adam, None]

        """

        assert self.hparams.opt in [
            "adam",
            "sgd",
        ], f"Optimizer {self.hparams.opt} not supported."
        if self.hparams.opt == "adam":
            opt = torch.optim.Adam(self.modules.parameters(), self.hparams.lr)
            sched = torch.optim.lr_scheduler.StepLR(opt, step_size=20, gamma=0.1)
            #sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', factor=0.1, patience=5, threshold=0.0001, threshold_mode='rel', cooldown=0, min_lr=0, eps=1e-08, verbose=False)
        elif self.hparams.opt == "sgd":
            opt = torch.optim.SGD(self.modules.parameters(), self.hparams.lr)
        return opt, sched