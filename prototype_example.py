import numpy as np

import prototype_module


print(prototype_module.func1.__doc__)

print("\n\nTrivial call examples:\n")

print(prototype_module.func1([1, 2, 3]))
print(prototype_module.func1(np.matrix([1, 2, 3])))

print("\nNobody can handle this")
prototype_module.func1(np.matrix([1, 2, 3]), parameter="uhoh!")
