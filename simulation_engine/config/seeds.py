import random
import numpy as np
from faker import Faker

SEED = 42

random.seed(SEED)
np.random.seed(SEED)
Faker.seed(SEED)

fake = Faker(["ar_EG", "en_US"])
