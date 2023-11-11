from micromind import MicroMind, Metric
from micromind.networks import PhiNet
from micromind.utils.parse import parse_arguments

import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as transforms

from torchinfo import summary
from ptflops import get_model_complexity_info

import os

batch_size = 128

if torch.cuda.is_available():
    device = torch.device("cuda:0")
    print("Running on the GPU")
elif torch.backends.mps.is_available: 
    device = torch.device("mps")
    print("Running on the MPS")
else:
    device = torch.device("cpu")
    print("Running on the CPU")

# 192 a1, 384 a2, 576 a3

exp = 0
alpha_id = 4

alphas_str = ['0','0.2', '1', '15', '2', '3']
alphas = [0, 0.2, 1, 1.5, 2, 3]
inputs = [0, 38, 192, 288, 384, 576]

class ImageClassification(MicroMind):

    # test 1 with n as input vector size and m classes custom d
    # n has to be calculated from the output of the neural network of the feature extractor

    def __init__(self, *args, inner_layer_width = 10, testing=False, path="", **kwargs):
        super().__init__(*args, **kwargs)

        self.input = inputs[alpha_id]
        self.output = 100
        self.d = inner_layer_width

        self.modules["feature_extractor"] = PhiNet(
            (3, 32, 32), include_top=False, num_classes=100, alpha=alphas[alpha_id]
        )        

        if(not testing):
            # Taking away the classifier from pretrained model
            pretrained_dict = torch.load("./pretrained/a" + alphas_str[alpha_id] + "/exp/baseline.ckpt", map_location=device)["feature_extractor"]        
            model_dict = {}
            for k, v in pretrained_dict.items():
                if "classifier" not in k:
                    model_dict[k] = v

            #loading the new model
            self.modules["feature_extractor"].load_state_dict(model_dict)         

            self.modules["baseline_classifier"] = nn.Sequential(
                    nn.AdaptiveAvgPool2d((1, 1)),
                    nn.Flatten(),
                    nn.Linear(in_features=self.input, out_features=self.output)
                )
            
            for x, param in self.modules["feature_extractor"].named_parameters():    
                param.requires_grad = False

        if(testing):
            if(path==""):
                raise Exception
            full_path = path + 'exp/save/'
            print(full_path)        

            res = os.listdir(full_path)
            print(res)            

            test = torch.load(full_path + res[0], map_location=device)
            print(torch.load(full_path + res[0], map_location=device)["baseline_classifier"].named_parameters())

            #loading the new model
            self.modules["feature_extractor"].load_state_dict(torch.load(full_path + res[0], map_location=device)["feature_extractor"])
            self.modules["baseline_classifier"].load_state_dict(torch.load(full_path + res[0], map_location=device)["baseline_classifier"])                        
            

    def forward(self, batch):
        x = self.modules["feature_extractor"](batch[0])        
        x = self.modules["baseline_classifier"](x)
        return x

    def compute_loss(self, pred, batch):
        return nn.CrossEntropyLoss()(pred, batch[1])
    
def save_parameters(model, path):

    input = (3, 32, 32)
    macs_backbone, params_backbone = get_model_complexity_info(model.modules["feature_extractor"], input, as_strings=False,
                                           print_per_layer_stat=False, verbose=False)        
    summary_backbone = summary(model.modules["feature_extractor"], input_size=(batch_size, 3, 32, 32))    
    print(summary_backbone)

    input = (model.input, 1, 1)
    macs_classifier, params_classifier = get_model_complexity_info(model.modules["baseline_classifier"], input, as_strings=False,
                                           print_per_layer_stat=False, verbose=False)        
    summary_classifier = summary(model.modules["baseline_classifier"], input_size=(10, model.input, 1, 1))    

    output = "BACKBONE\n" 
    output += "MACs {}, learnable parameters {}\n".format(macs_backbone, params_backbone)
    output += str(summary_backbone) + "\n"
    output += "\n"*2
    output += "CLASSIFIER\n" 
    output += "MACs {}, learnable parameters {}\n".format(macs_classifier, params_classifier)
    output += str(summary_classifier)    

    if not os.path.exists(path):
        os.makedirs(path)

    with open(path + 'architecture.txt', 'w') as file:
        file.write(output)
    
if __name__ == "__main__":    

    hparams = parse_arguments()  
    hparams.lr = 0.001
    print(hparams)  

    d = 0
    
    print("Running experiment with d = {}".format(d))        

    hparams.output_folder = 'results/adaptive_exp/a' + alphas_str[alpha_id] + '/'+str(exp)+'/' + str(d) + '/'
    print(hparams.output_folder)

    m = ImageClassification(hparams, inner_layer_width = d)    

    def compute_accuracy(pred, batch):
        tmp = (pred.argmax(1) == batch[1]).float()
        return tmp

    transform = transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))]
    )

    trainset = torchvision.datasets.CIFAR100(
        root="data/cifar-100", train=True, download=True, transform=transform
    )
    trainloader = torch.utils.data.DataLoader(
        trainset, batch_size=batch_size, shuffle=True, num_workers=8
    )

    testset = torchvision.datasets.CIFAR100(
        root="data/cifar-100", train=False, download=True, transform=transform
    )
    testloader = torch.utils.data.DataLoader(
        testset, batch_size=batch_size, shuffle=False, num_workers=1
    )

    save_parameters(m, hparams.output_folder)    

    acc = Metric(name="accuracy", fn=compute_accuracy)

    epochs = 200

    m.train(
        epochs=epochs,
        datasets={"train": trainloader, "val": testloader, "test": testloader},
        metrics=[acc],
        debug=hparams.debug,
    )

    m = ImageClassification(hparams, inner_layer_width = d, testing=True, path=hparams.output_folder)

    m.train(
        epochs=1,
        datasets={"train": trainloader, "val": testloader, "test": testloader},
        metrics=[acc],
        debug=hparams.debug,
    )

    result = m.test(
        datasets={"test": testloader},
    )

    result += " Epochs: " + str(epochs)

    with open(hparams.output_folder + 'test_set_result.txt', 'w') as file:
        file.write(result)