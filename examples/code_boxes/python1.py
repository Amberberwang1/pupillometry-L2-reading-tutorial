# 1. Install pupilread (once). Type this line, without the "#", in a terminal or in
#    the console of a Python editor such as Spyder. The output should end with
#    "Successfully installed pupilread-1.0.0".
# pip install https://github.com/Amberberwang1/pupillometry-L2-reading-tutorial/archive/refs/tags/v1.0.0.zip

# 2. Load the package
import pupilread as pr

# 3. Write a small simulated study to test on
pr.make_example("example")    # 3 readers, 4 texts each, in a folder named example

# 4. Run all stages on every reader (Sections 3.1 to 3.6)
settings = {"data": {
    "design": "example/design.csv",       # text and version of each trial
    "exclude": "example/exclusions.csv",  # trials to leave out
}}
result = pr.run_pipeline("example", settings)
# The last line printed ends with "3 readers, 10 kept and 9 analysed trials; files in
# example/pupilread_output". The files for the models in R are in its folder for_R.
