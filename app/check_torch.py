import torch
import torchvision
from torchvision.transforms import InterpolationMode

print("torch =", torch.__version__)
print("torchvision =", torchvision.__version__)
print("cuda available =", torch.cuda.is_available())
print("InterpolationMode =", InterpolationMode.BILINEAR)