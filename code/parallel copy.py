from micromind import Metric
from micromind.utils.parse import parse_arguments

import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as transforms
from torchvision.transforms import v2
from torch.utils.data import default_collate
from torchinfo import summary
from ptflops import get_model_complexity_info

import os
import random
import importlib
import numpy as np

batch_size = 128

def START_seed():
    seed = 9
    torch.manual_seed(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

def seed_worker(worker_id):
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)
    
def save_parameters(model, hparams):

    path = hparams.output_folder + "/" + hparams.experiment_name

    input = (3, 32, 32)
    macs_backbone, params_backbone = get_model_complexity_info(model.modules["feature_extractor"], input, as_strings=False,
                                           print_per_layer_stat=False, verbose=False)        
    summary_backbone = summary(model.modules["feature_extractor"], input_size=(batch_size, 3, 32, 32))    
    #print(summary_backbone)

    input = (model.input, 1, 1)
    macs_classifier, params_classifier = get_model_complexity_info(model.modules["original_classifier"], input, as_strings=False,
                                           print_per_layer_stat=False, verbose=False)        
    summary_classifier = summary(model.modules["original_classifier"], input_size=(10, model.input, 1, 1))    

    output = "BACKBONE\n" 
    output += "MACs {}, learnable parameters {}\n".format(macs_backbone, params_backbone)
    output += str(summary_backbone) + "\n"
    output += "\n"*2
    output += "CLASSIFIER\n" 
    output += "MACs {}, learnable parameters {}\n".format(macs_classifier, params_classifier)
    output += str(summary_classifier)    

    print(path)

    if not os.path.exists(path):
        os.makedirs(path)

    with open(path + '/architecture.txt', 'w') as file:
        file.write(output)

    print("ok")

    with open(path + '/meta.txt', 'w') as file:
        file.write(str(hparams))
    
# cutmix = v2.CutMix(num_classes=100, alpha=0.5)
# mixup = v2.MixUp(num_classes=100, alpha=0.5)
# cutmix_or_mixup = v2.RandomChoice([cutmix, mixup])

# def collate_fn(batch):
#     tmp = cutmix_or_mixup(*default_collate(batch))
#     res = [x for x in tmp] 
#     return res

if __name__ == "__main__":  

    START_seed()  

    hparams = parse_arguments()    
    hparams.experiment_name = hparams.experiment_name + '/' + str(hparams.d) + '/'    
    print(hparams.experiment_name)

    print("Running experiment with {}".format(hparams.d))

    module = importlib.import_module("models." + hparams.model_name)
    ImageClassification = getattr(module, "ImageClassification") 

    g = torch.Generator()
    g.manual_seed(0)

    m = ImageClassification(hparams)

    def compute_accuracy(pred, batch):
        tmp = (pred.argmax(1) == batch[1]).float()
        return tmp
        
    transform = transforms.Compose(
        [
         transforms.ToTensor(), 
         transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)), 
         transforms.Resize((160, 160), antialias=True), 
         transforms.RandomHorizontalFlip(0.5),
         transforms.RandomRotation(10)
        ] 
    )
    trainset = torchvision.datasets.CIFAR100(
        root="data/cifar-100", train=True, download=True, transform=transform
    )
    testset = torchvision.datasets.CIFAR100(
        root="data/cifar-100", train=False, download=True, transform=transform
    )        
    
    val_size = int(0.1 * len(trainset))
    train_size = len(trainset) - val_size
    train, val = torch.utils.data.random_split(trainset, [train_size, val_size])    

    train_loader = torch.utils.data.DataLoader(
        train, batch_size=batch_size, 
        shuffle=True, 
        num_workers=8, 
        worker_init_fn=seed_worker,
        generator=g
        #collate_fn=collate_fn,
    )
    val_loader = torch.utils.data.DataLoader(
        val, batch_size=batch_size, 
        shuffle=False, 
        num_workers=8, 
        worker_init_fn=seed_worker,
        generator=g
    )    
    test_loader = torch.utils.data.DataLoader(
        testset, batch_size=batch_size, 
        shuffle=False, 
        num_workers=1,
        worker_init_fn=seed_worker,
        generator=g
    )

    print("Trainset size: ", len(train)//batch_size)
    print("Valset size: ", len(val)//batch_size)
    print("Testset size: ", len(testset)//batch_size)

    save_parameters(m, hparams)    

    acc = Metric(name="accuracy", fn=compute_accuracy)    

    epochs = hparams.epochs

    m.train(
        epochs=epochs,
        datasets={"train": train_loader, "val": val_loader},
        metrics=[acc],
        debug=hparams.debug,
    )

    result = m.test(
        datasets={"test": test_loader},
    )    

    result += " Epochs: " + str(epochs)

    with open(hparams.output_folder + 'test_set_result.txt', 'w') as file:
        file.write(result)



import torch, time, sys, os, copy

os.environ['CUDA_LAUNCH_BLOCKING'] = '1'
sys.path.append('../')

import torch
import torch.multiprocessing as mp
from torch.utils.data import DataLoader, TensorDataset
from termcolor import cprint

# Spawn a separate process for each copy of the model
# mp.set_start_method('spawn')  # must be not fork, but spawn

queue = mp.Queue()


# Define your model
class MyModel(torch.nn.Module):

    def __init__(self):
        super().__init__()
        self.fc1 = torch.nn.Linear(10, 10)
        self.relu = torch.nn.ReLU()
        self.fc2 = torch.nn.Linear(10, 2)

    def forward(self, x):
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2(x)
        return x


# Define a function to train a single copy of the model
def train_model(rank, queue, DEVICE):
    # Set the random seed for reproducibility
    torch.manual_seed(rank)

    X, y, bias = queue.get()
    cprint(f'Rank: {rank}, X data_ptr: {X.data_ptr()}', color='yellow')

    # Load your dataset
    dataset = TensorDataset(
        X,
        y,
    )

    # Set the device to the current process's device
    with torch.no_grad():
        model = MyModel().to(DEVICE)
        model.fc1.bias = torch.nn.Parameter(bias)

        if rank == 0:
            # changing weight in one model in a separate process doesn't affect the weights in the model in another process, because the weight tensors are not shared
            model.fc1.weight[0][0] = -33.0

            # but changing bias (which is a shared tensor) should affect biases in the other processes
            model.fc1.bias *= 4

            cprint(f'RANK: {rank} | {list(model.parameters())[0][0,0]}', color='magenta')

        if rank == 8:
            cprint(f'RANK: {rank} | {list(model.parameters())[0][0,0]}', color='red')
            cprint(f'RANK: {rank} | BIAS: {model.fc1.bias}', color='red')

    ptr = model.fc1.weight[0][0].storage().data_ptr()
    cprint(f'Rank: {rank}, model data_ptr: {ptr}', color='blue')

    # Create a DataLoader for your dataset
    dataloader = DataLoader(dataset, batch_size=32, shuffle=False)

    # Define the loss function and optimizer
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)

    # Train the model
    for epoch in range(100):
        for i, (inputs, labels) in enumerate(dataloader):

            if rank == 0:
                cprint(f'RANK: {rank} | {list(model.parameters())[0][0,0]}', color='magenta')
                cprint(f'RANK: {rank} | BIAS: {model.fc1.bias}', color='magenta')
            if rank == 8:
                cprint(f'RANK: {rank} | {list(model.parameters())[0][0,0]}', color='red')
                cprint(f'RANK: {rank} | BIAS: {model.fc1.bias}', color='red')

            optimizer.zero_grad()

            outputs = model(inputs)
            loss = criterion(outputs, labels)
            loss.backward()

            # optimizer.step()

            if (i + 1) % 10 == 0:
                print(
                    f"Process {rank} Epoch [{epoch + 1}/{100}], Step [{i + 1}/{len(dataloader)}], Loss: {loss.item():.4f}"
                )
    cprint(f'{rank} finished!', color='yellow')


NUM_MODEL_COPIES = 10
DEVICE = 'cuda:0'

processes = []
for rank in range(NUM_MODEL_COPIES):
    process = mp.Process(target=train_model, args=(rank, queue, DEVICE))
    process.start()
    processes.append(process)

time.sleep(2)

X = torch.rand(size=(10000, 10)).to(DEVICE)
y = torch.randint(2, size=(10000,)).to(DEVICE)
shared_bias = torch.ones(size=(10,), device=DEVICE)
for rank in range(NUM_MODEL_COPIES):
    queue.put((X, y, shared_bias))

# Wait for all processes to finish
for process in processes:
    process.join()