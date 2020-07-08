import sys


def train(exe: str, *argv: str) -> None:
    print("Your training script here", exe, argv)


if __name__ == "__main__":
    train(*sys.argv)
