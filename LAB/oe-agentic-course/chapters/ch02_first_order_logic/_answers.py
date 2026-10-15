"""Reference answers for the Chapter 2 exercise checks.

The check cells compare your results with these. Do not open this file before you have
attempted the exercises: the solutions notebooks show the reasoning, this shows only the
results.
"""

CH2_1_2 = (16, 7)                       # (interpretations, satisfying ones)
CH2_2_2 = 2                             # smallest countermodel size
CH2_R1 = {
    "Every lion is a carnivore.": "forall x (Lion(x) -> Carnivore(x))",
    "Some plant is edible.": "exists x (Plant(x) & Edible(x))",
    "No carnivore is a plant.": "forall x (Carnivore(x) -> ~Plant(x))",
    "Every animal eats something.": "forall x (Animal(x) -> exists y Eats(x, y))",
    "There is an animal that everything eats.": "exists x (Animal(x) & forall y Eats(y, x))",
}
CH2_R2 = [True, True, False]
CH2_R3 = ["valid", "satisfiable", "unsatisfiable"]
