import torch.nn as nn
from torch.utils.data import DataLoader

from openood.utils import Config

from .base_trainer import BaseTrainer
from .mixup_trainer import MixupTrainer
from .sae_trainer import SAETrainer


def get_trainer(
    net: nn.Module,
    train_loader: DataLoader,
    config: Config,
):
    trainers = {
        'base': BaseTrainer,
        'mixup': MixupTrainer,
        'sae': SAETrainer,
    }
    return trainers[config.trainer.name](net, train_loader, config)
