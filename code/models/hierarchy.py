from micromind import MicroMind, Metric
from micromind.networks import PhiNet
from micromind.utils.parse import parse_arguments

import torch
import torch.nn as nn

from huggingface_hub import hf_hub_download

REPO_ID = "micromind/ImageNet"
FILENAME = "v7/state_dict.pth.tar"

model_path = hf_hub_download(repo_id=REPO_ID, filename=FILENAME, local_dir="./pretrained")

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

        self.input = 344
        self.output = 10                

        self.modifier_bias = nn.Parameter(torch.randn(self.output, self.input)).to(device)        

        # alpha: 0.9
        # beta: 0.5
        # num_classes: 1000
        # num_layers: 7
        # t_zero: 4.0

        self.modules["feature_extractor"] = PhiNet(
            input_shape=(3, 160, 160),
            alpha=0.9,
            num_layers=7,
            beta=0.5,
            t_zero=4.0,
            include_top=False,
            num_classes=1000,
            compatibility=False,
            divisor=8,
            downsampling_layers=[4,5,7]
        )

        # Taking away the classifier from pretrained model
        pretrained_dict = torch.load(model_path, map_location=device)
        model_dict = {}
        for k, v in pretrained_dict.items():
            if "classifier" not in k:
                model_dict[k] = v

        #loading the new model
        self.modules["feature_extractor"].load_state_dict(model_dict)        
        # for _, param in self.modules["feature_extractor"].named_parameters():    
        #     param.requires_grad = False 

        self.modules["flattener"] = nn.Sequential(
                nn.AdaptiveAvgPool2d((1, 1)),
                nn.Flatten(),                   
        )

        self.modules["classifier"] = nn.Sequential(
            nn.Linear(in_features=self.input, out_features=self.output)    
        )

    def forward(self, batch):     

        feature_vector = self.modules["feature_extractor"](batch[0])    
        feature_vector = self.modules["flattener"](feature_vector)            
        x = self.modules["classifier"](feature_vector)

        #print(len(batch[0]))

        broadcasted_bias = self.modifier_bias.unsqueeze(0).expand(len(batch[0]),-1,-1)

        out_expanded = x.unsqueeze(2)

        result = out_expanded * broadcasted_bias

        result_summed = result.sum(dim=1)

        # maybe we don't even need to add them?
        modified_feature_vector = feature_vector + result_summed

        x_2 = self.modules["classifier"](modified_feature_vector)        
        
        output_tensor = torch.zeros(len(batch[0]), 100, device=device)

        indexes = torch.argmax(x, dim=1)

        # Calculate the ranges using vectorized operations
        start = indexes * 10
        end = (indexes + 1) * 10

        # Use 'torch.arange' and 'torch.stack' for creating the sequence tensors
        to_add = torch.stack([torch.arange(start[i], end[i], device=device) for i in range(len(indexes))])        

        output_tensor.scatter_(1, to_add, x_2)        
        
        return output_tensor
    
    """
    >>> b = torch.zeros((4,10), dtype=a.dtype)
    >>> b
    tensor([[0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]])
    >>> indexes = torch.tensor([[1,2],[2,3],[3,4],[4,5]]
    ... )
    >>> indexes
    tensor([[1, 2],
            [2, 3],
            [3, 4],
            [4, 5]])
    >>> values = torch.tensor([[1,1],[2,2],[3,3],[4,4]])
    >>> b.scatter_(1, indexes, values)
    tensor([[0, 1, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 2, 2, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 3, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 4, 4, 0, 0, 0, 0]])
    """

    def compute_loss(self, pred, batch):
        return nn.CrossEntropyLoss()(pred, batch[1])
    
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