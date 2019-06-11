import os
import sys
import time
import requests
import logging

from sqlalchemy import and_
from libztf.db import DBSession, Image

suffix_dict = {'sub': 'scimrefdiffimg.fits.fz',
               'sci': 'sciimg.fits',
               'mask': 'mskimg.fits',
               'psf': 'diffimgpsf.fits'}

ipac_username = os.getenv('IPAC_USERNAME')
ipac_password = os.getenv('IPAC_PASSWORD')
ipac_root = 'https://irsa.ipac.caltech.edu/'

# split an iterable over some processes recursively
_split = lambda iterable, n: [iterable[:len(iterable)//n]] + \
             _split(iterable[len(iterable)//n:], n - 1) if n != 0 else []

CHUNK_SIZE = 1024


def ipac_authenticate():
    target = os.path.join(ipac_root, 'account', 'signon', 'login.do')

    while True:
        try:
            r = requests.post(target, data={'josso_username': ipac_username, 'josso_password': ipac_password,
                                            'josso_cmd': 'login'})
        except Exception as e:
            print(f'Got exception {e} trying to connect to IPAC, retrying...')
            time.sleep(1)
        else:
            break

    if r.status_code != 200:
        raise ValueError('Unable to Authenticate')

    if r.cookies.get('JOSSO_SESSIONID') is None:
        raise ValueError('Unable to login to IPAC - bad credentials')

    return r.cookies


class IPACQueryManager(object):

    def __init__(self, logger):
        self.logger = logger
        self.cookie = ipac_authenticate()
        self.start_time = time.time()

    def __call__(self, nchunks, mychunk, imagetypes=('sub',)):

        counter = 0
        for itype in imagetypes:

            hpss = getattr(Image, f'hpss_{itype}_path')
            disk = getattr(Image, f'disk_{itype}_path')

            images = DBSession().query(Image) \
                                .filter(and_(hpss == None, disk == None)) \
                                .order_by(Image.field, Image.ccdid, Image.qid, Image.filtercode, Image.obsjd) \
                                .all()

            my_images = _split(images, nchunks)[mychunk - 1]
            suffix = suffix_dict[itype]

            for image in my_images:
                ipac_path = image.ipac_path(suffix)
                disk_path = image.disk_path(suffix)

                while True:
                    now = time.time()
                    dt = now - self.start_time
                    if dt > 86400.:
                        self.start_time = time.time()
                        self.cookie = ipac_authenticate()
                    try:
                        r = requests.get(ipac_path, cookies=self.cookie)
                    except Exception as e:
                        self.logger.info(f'Received exception {e}, retrying...')
                        time.sleep(1.)
                    else:
                        break

                with open(disk_path, 'wb') as f:
                    f.write(r.content)
                    counter += 1

                disk = disk_path

                if counter == CHUNK_SIZE:
                    DBSession().commit()
                    counter = 0

if __name__ == '__main__':

    logger = logging.getLogger('poll')
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    logger.addHandler(ch)

    hostname = os.getenv('HOSTNAME')

    formatter = logging.Formatter(f'[%(asctime)s - {hostname} - %(levelname)s] - %(message)s')
    ch.setFormatter(formatter)

    nchunks = 4
    mychunk = int(hostname[-2:])
    manager = IPACQueryManager(logger)
    manager(nchunks, mychunk)
