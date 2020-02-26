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
imgs = sorted(imgs, key=lambda s: s.split('ztf_')[1].split('_')[0], reverse=True)

for fn in imgs:

    start = time.time()
    sub = db.SingleEpochSubtraction.get_by_basename(os.path.basename(fn))
    sub.map_to_local_file(fn, quiet=True)
    sub.mask_image.map_to_local_file(fn.replace('.fits', '.mask.fits'), quiet=True)
    sub._rmsimg = db.FITSImage()
    sub.rms_image.map_to_local_file(fn.replace('.fits', '.rms.fits'), quiet=True)

    sstart = time.time()
    sources = sub.unphotometered_sources
    sstop = time.time()
    db.print_time(sstart, sstop, sub, 'unphotometered sources')

    if len(sources) == 0:
        stop = time.time()
        print(f'phot: took {stop-start:.2f} sec to do phot on {sub.basename}')
        continue

    try:
        pstart = time.time()
        phot = sub.force_photometry(sources,
                                    assume_background_subtracted=True,
                                    use_cutout=False,
                                    direct_load={'sci': fn,
                                                 'mask': fn.replace('.fits', '.mask.fits'),
                                                 'rms': fn.replace('.fits', '.rms.fits')}
                                    )
        pstop = time.time()
        db.print_time(pstart, pstop, sub, 'actual force photometry')
    except Exception as e:
        print(e)
        continue

    #db.DBSession().add_all(phot)

    gtups = [str((p.source.id, p.image.id, 'now()', 'now()', p.flux, p.fluxerr, 'photometry'))
             for p in phot]

    pid = [row[0] for row in db.DBSession().execute(
        'INSERT INTO objectswithflux (source_id, image_id, created_at, modified, '
        'flux, fluxerr, type) '
        f'VALUES {",".join(gtups)} RETURNING ID'
    )]

    ftups = [str((i, p.flags, p.ra, p.dec)) for i, p in zip(pid, phot)]
    db.DBSession().execute(f'INSERT INTO forcedphotometry (id, flags, ra, dec) '
                           f'VALUES {",".join(ftups)}')

    db.DBSession().commit()
    stop = time.time()
    print(f'phot: took {stop-start:.2f} sec to do phot on {sub.basename}', flush=True)





