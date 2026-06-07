import sys
from .sampler import main

if len(sys.argv) != 2:
    print("Usage: python -m data_sampler <config.yaml>")
    sys.exit(1)

main(sys.argv[1])
