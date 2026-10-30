# Check the installation on a simulated study
import pupilread as pr
pr.make_example("example")          # 3 readers, 4 texts each, in folder example
settings = {"data": {
    "design": "example/design.csv",       # text and version of each trial
    "exclude": "example/exclusions.csv",  # trials to leave out
}}
result = pr.run_pipeline("example", settings)   # all stages, every reader
