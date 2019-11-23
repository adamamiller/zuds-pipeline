import db
import sys
import mpi

db.init_db()

__author__ = 'Danny Goldstein <danny@caltech.edu>'
__whatami__ = 'Make the weight maps for ZUDS.'

infile = sys.argv[0]  # file listing all the images to build weight maps for

# get the work
sci_fns = mpi.get_my_share_of_work(infile)

# load the objects into memory
for fn in sci_fns:
    # this line assumes that .mskimg.fits is in the same directory
    sci = db.ScienceImage.from_file(fn)
    sci.weight_image.save()
    sci.rms_image.save()

