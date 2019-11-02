import db
import os
import shutil
from pathlib import Path


fid_map = {
    1: 'zg',
    2: 'zr',
    3: 'zi'
}


def archive(product):
    """Publish a data product to the NERSC archive. Must be run from a nersc machine."""

    if not isinstance(product, db.PipelineFITSProduct):
        raise ValueError(f'Cannot archive object "{product}", must be an instance of'
                         f'PipelineFITSProduct.')

    field = product.field
    qid = product.qid
    ccdid = product.ccdid
    fid = product.fid
    band = fid_map[fid]

    path = Path(db.NERSC_PREFIX) / f'{field:06d}/' \
                                   f'c{ccdid:02d}/' \
                                   f'q{qid}/' \
                                   f'{band}/' \
                                   f'{product.basename}'

    product.nersc_path = path.absolute()
    product.url = str(path.absolute()).replace(db.NERSC_PREFIX, db.URL_PREFIX)

    if os.getenv('NERSC_HOST') == 'cori':
        path.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy(product.local_path, path)
    else:
        # TODO: implement this -- will send a local file to
        # an HTTP server that can put the file in its proper
        # place at NERSC
        product.put()

    db.DBSession().rollback()
    db.DBSession().add(product)
    db.DBSession().commit()


