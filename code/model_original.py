from micromind import MicroMind, Metric
from micromind.networks import PhiNet
from micromind.utils.parse import parse_arguments

import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as transforms

exp = 0
alpha_id = 0

alphas_str = ['0.2', '1', '15', '2', '3']
alphas = [0.2, 1, 1.5, 2, 3]
# input sizes for the different alpha values
inputs = [38, 192, 288, 384, 576]

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

        self.input = inputs[alpha_id]
        self.output = 100
        self.d = inner_layer_width

        self.modules["feature_extractor"] = PhiNet(
            (3, 32, 32), include_top=True, num_classes=100, alpha=alphas[alpha_id]
        )        

        # Taking away the classifier from pretrained model
        pretrained_dict = torch.load("./pretrained/1000_epochs_baseline.ckpt", map_location=device)["feature_extractor"]                

        #loading the new model
        self.modules["feature_extractor"].load_state_dict(pretrained_dict)        

    def forward(self, batch):
        x = self.modules["feature_extractor"](batch[0])        
        return x

    def compute_loss(self, pred, batch):
        return nn.CrossEntropyLoss()(pred, batch[1])