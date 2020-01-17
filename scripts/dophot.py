import db
import sys
import mpi
import os
import time
import archive
from datetime import datetime, timedelta

fmap = {1: 'zg',
        2: 'zr',
        3: 'zi'}

db.init_db()
#db.DBSession().autoflush = False
#db.DBSession().get_bind().echo = True

__author__ = 'Danny Goldstein <danny@caltech.edu>'
__whatami__ = 'Make the subtractions for ZUDS.'

infile = sys.argv[1]  # file listing all the subs to do photometry on


# get the work
imgs = mpi.get_my_share_of_work(infile)

for fn in imgs:

    start = time.time()
    sub = db.SingleEpochSubtraction.get_by_basename(os.path.basename(fn))
    sub.map_to_local_file(fn, quiet=True)
    sub.mask_image.map_to_local_file(fn.replace('.fits', '.mask.fits'), quiet=True)
    sub._rmsimg = db.FITSImage()
    sub.rms_image.map_to_local_file(fn.replace('.fits', '.rms.fits'), quiet=True)

    sources = sub.unphotometered_sources
    if len(sources) == 0:
        stop = time.time()
        print(f'phot: took {stop-start:.2f} sec to do phot on {sub.basename}')
        continue

    try:
        phot = sub.force_photometry(sources,
                                    assume_background_subtracted=True
                                    )
    except Exception as e:
        print(e)
        continue

    db.DBSession().add_all(phot)
    db.DBSession().commit()
    stop = time.time()
    print(f'phot: took {stop-start:.2f} sec to do phot on {sub.basename}', flush=True)


