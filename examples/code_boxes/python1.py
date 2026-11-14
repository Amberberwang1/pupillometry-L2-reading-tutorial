# Step 1: install pupilread. In a Spyder or Jupyter console, run the line below without the first "#" (in a terminal, also leave out the %):
# %pip install https://github.com/Amberberwang1/pupillometry-L2-reading-tutorial/archive/refs/tags/v1.1.1.zip

# Step 2: to follow our stages outlined in the paper (Python 2 to 5) and reproduce our results, download
# pupilread_paper_data.zip (388 MB) from Assets on the v1.1.1 release
# page and unzip it:
# https://github.com/Amberberwang1/pupillometry-L2-reading-tutorial/releases/tag/v1.1.1

# Step 3: load pupilread and go to the data folder.
import pupilread as pr
# Optional: check that pupilread works on simulated data (3 readers)
pr.make_example("example")

# Replace the path with that of your unzipped pupilread_paper_data folder
# (or of your own data, laid out in the same way):
import os
os.chdir("/path/to/pupilread_paper_data")
