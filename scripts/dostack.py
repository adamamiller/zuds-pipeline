import db
import sys
import mpi
import os
import time
import pandas as pd

fmap = {1: 'zg',
        2: 'zr',
        3: 'zi'}

db.init_db()
db.DBSession().get_bind().echo = True

__author__ = 'Danny Goldstein <danny@caltech.edu>'
__whatami__ = 'Make the references for ZUDS.'

infile = sys.argv[1]  # file listing all the images to make subtractions of
# get the work
jobs = mpi.get_my_share_of_work(infile, reader=pd.read_csv)


for _, job in jobs.iterrows():

    tstart = time.time()
    sstart = time.time()
    images = db.DBSession().query(db.ZTFFile).filter(
        db.ZTFFile.id.in_(eval(job['target']))
    ).all()
    db.ensure_images_have_the_same_properties(images, db.GROUP_PROPERTIES)

    field = f'{images[0].field:06d}'
    ccdid = f'c{images[0].ccdid:02d}'
    qid = f'q{images[0].qid}'
    fid = f'{fmap[images[0].fid]}'

    for image in images:
        path = f'/global/cscratch1/sd/dgold/zuds/{field}/{ccdid}/{qid}/' \
               f'{fid}/{image.basename}'
        image.map_to_local_file(path)
        image.mask_image.map_to_local_file(path.replace('sciimg', 'mskimg'))

    basename = f'{field}_{ccdid}_{qid}_{fid}_{job["left"]}_' \
               f'{job["right"]}.coadd.fits'


    prev = db.ScienceCoadd.get_by_basename(basename)
    outname = os.path.join(os.path.dirname(images[0].local_path), basename)
    sstop = time.time()


    print(
        f'load: {sstop-sstart:.2f} sec to load input images for {outname}',
        flush=True
    )

    stackstart = time.time()
    try:
        stack = db.ScienceCoadd.from_images(
            images, outfile_name=outname,
            data_product=False,
            tmpdir='tmp'
        )
    except Exception as e:
        print(e, [i.basename for i in images], flush=True)
        db.DBSession().rollback()
        continue
    stackstop = time.time()
    print(
        f'stack: {stackstop-stackstart:.2f} sec to make {stack.basename}',
        flush=True
    )

    archstart = time.time()
    db.DBSession().add(stack)
    db.DBSession().commit()
    archstop = time.time()

    print(
        f'archive: {archstop-archstart:.2f} sec to archive {stack.basename}',
        flush=True
    )

    cleanstart = time.time()
    targets = []
    for sci in images + [stack]:
        if hasattr(sci, '_rmsimg'):
            targets.append(sci.rms_image.local_path)
        if hasattr(sci, '_weightimg'):
            targets.append(sci.weight_image.local_path)

        sci.unmap()

    for target in targets:
        os.remove(target)

    cleanstop = time.time()

    tstop = time.time()
    print(f'clean: took {cleanstop - cleanstart} sec to clean '
          f'up after {sub.basename}"',
          flush=True)
    print(f'took {tstop - tstart} sec to make "{sub.basename}"', flush=True)










