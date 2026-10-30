# Check the installation on a simulated study
import pupilread as pr
pr.make_example("example")          # 3 readers, 4 texts each, in folder example
config = {"data": {"design": "example/design.csv",          # item and version
                   "exclude": "example/exclusions.csv"}}    # skimmed trials
result = pr.run_pipeline("example", config)   # all stages, every reader
