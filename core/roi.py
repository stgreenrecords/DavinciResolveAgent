from dataclasses import dataclass


@dataclass
class Roi:
    x: int
    y: int
    width: int
    height: int
