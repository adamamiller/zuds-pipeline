from astropy.io import fits
from astropy.coordinates import SkyCoord
from astropy.wcs import WCS
from astropy import units as u
import pandas as pd
import galsim
from galsim import des
from libztf import mkivar, make_rms, medg



import numpy as np
import subprocess
import os

abspath = os.path.abspath

matchquery = "SELECT id, ra, dec, {flt}, {std} " \
    "from dr1.ps1 where q3c_poly_query(ra, dec, "\
    "'{{{ra_ll}, {dec_ll}, {ra_lr}, {dec_lr}, {ra_ur}, {dec_ur}, {ra_ul}, {dec_ul}}}') "\
    " and {flt} > 0.0"

def parse_sexcat(cat, bin=False):
    """Read a sextractor catalog file (path: `cat`) and return a numpy
    record array containing the values."""

    if bin:
        data = fits.open(cat)[2].data
    else:
        data = np.genfromtxt(cat, dtype=None)
    return data


def zpsee(image, cat, cursor, zp_fid, inhdr=None):
    """Compute the median zeropoint of an image or images (path/paths:
    `im_or_ims`) using the Pan-STARRS photometric database (cursor:
    `cursor`)."""

    hd = fits.Header()

    with fits.open(image) as f:
        band = f[0].header['FILTER'][-1].lower() + '_median'
        nax1 = f[0].header['NAXIS1']
        nax2 = f[0].header['NAXIS2']
        std = f[0].header['FILTER'][-1].lower() + '_stdev'

    hd['NAXIS1'] = nax1
    hd['NAXIS2'] = nax2

    if inhdr is not None:
        with open(inhdr, 'r') as f:
            for line in list(f.read().split('\n')):
                card = fits.Card.fromstring(line.strip())
                hd.append(card)

    hd['CTYPE1'] = 'RA---TPV'
    hd['CTYPE2'] = 'DEC--TPV'



    try:
        wcs = WCS(hd)
    except Exception as e:
        print(f'failing header: {hd}')
        print(f'failing image: {image}')
        raise e

    corners = wcs.calc_footprint()

    ra_ll, dec_ll = corners[0]
    ra_lr, dec_lr = corners[1]
    ra_ul, dec_ul = corners[2]
    ra_ur, dec_ur = corners[3]

    cat = parse_sexcat(cat, bin=True)
    cat = cat[cat['FLAGS'] == 0]
    cat = cat[cat['FLUX_PSF'] / cat['FLUXERR_PSF'] > 20]

    query_dict = {'flt':band, 'ra_ll':ra_ll, 'dec_ll':dec_ll,
                  'ra_lr':ra_lr, 'dec_lr':dec_lr, 'ra_ul':ra_ul,
                  'dec_ul':dec_ul, 'ra_ur':ra_ur, 'dec_ur':dec_ur,
                  'std': std}

    for key in query_dict:
        query_dict[key] = str(query_dict[key])
    cursor.execute(matchquery.format(**query_dict))

    result = np.array(cursor.fetchall(), dtype=[('id','<i8'),
                                                ('ra','<f8'),
                                                ('dec','<f8'),
                                                ('mag','<f8'),
                                                ('magerr', '<f8')])

    pd.DataFrame(result).to_csv(image.replace('.fits', '.phot.cat',), index=False)

    zps = []
    seeings = []

    cat_coords = SkyCoord(ra=cat['X_WORLD'] * u.degree, dec=cat['Y_WORLD'] * u.degree)
    db_coords = SkyCoord(ra=result['ra'] * u.degree, dec=result['dec'] * u.degree)
    try:
        idx, d2d, _ = cat_coords.match_to_catalog_sky(db_coords)
    except ValueError as e:
        print(f'failing frame was {image}')
        print(f'cat coords were {cat_coords}')
        print(f' db coords were {db_coords}')
        print(f'query dict was {query_dict}')
        print(f'wcs was {wcs}')
        print(f'header was {hd}')
        print(f'corners was {corners}')
        raise e

    for cat_row, i, d in zip(cat, idx, d2d):
        if d <= 1 * u.arcsec:
            ps1_mag = result[i]['mag']
            sex_mag = cat_row['MAG_PSF']
            zp = zp_fid + ps1_mag - sex_mag
            seeing = cat_row['FWHM_IMAGE'] * 1.013
            zps.append(zp)
            seeings.append(seeing)


    return np.median(zps), np.median(seeings)


def solve_zeropoint(image, cat, psf, zp_fid=27.5):

    import psycopg2

    con = psycopg2.connect(dbname='desi', host='***REMOVED***',
                           port=5432, user='***REMOVED***', password='***REMOVED***')

    # takes an image and sextractor  catalog and computes seeing /
    # zeropoints for all of them

    with con:
        cursor = con.cursor()
        inhdr = image.replace('.fits', '.head')
        zp, seeing = zpsee(image, cat, cursor, zp_fid, inhdr=inhdr)

    with fits.open(image, mode='update', memmap=False) as f:
        f[0].header['MAGZP'] = zp
        f[0].header['SEEING'] = seeing


def write_starcat(cat):

    hdul = fits.open(cat)
    data = hdul[2].data

    # keep stellar sources only

    # this is a star/galaxy cut from DES DR1
    # https://des.ncsa.illinois.edu/easyweb/db-examples
    # "Select stars from M2 Globular Cluster"

    ind = data['SPREAD_MODEL'] + 3 * data['SPREADERR_MODEL'] < 0.005
    ind = ind & (data['SPREAD_MODEL'] > -1)
    data = data[ind]

    snr = data['FLUX_PSF'] / data['FLUXERR_PSF']
    ind = snr >= 5
    data = data[ind]

    hdul[2].data = data
    outname = cat.replace('.cat', '.star.cat')
    hdul.writeto(outname, overwrite=True)
    hdul.close()


def calc_maglimit(cat):
    # calculate the magnitude of a 5 sigma point source
    # assumes the catalog is calibrated and has a PSF model

    with fits.open(cat) as hdul:
        data = hdul[2].data

    # keep stellar sources only

    sortinds = np.argsort(data['FLUX_PSF'] / data['FLUXERR_PSF'])
    maglimit = data['MAG_PSF'][sortinds[0]]

    return maglimit

def calibrate(frame, reuse_psf=False):
    # astrometrically and photometrically calibrate a ZTF frame using
    # PSF fitting and gaia

    mypath = os.path.dirname(os.path.abspath(__file__))
    sexconf = os.path.join(mypath, '../astromatic/calibration/scamp.sex')
    sexparam = os.path.join(mypath, '../astromatic/calibration/scamp.param')
    scampconf = os.path.join(mypath, '../astromatic/calibration/scamp.conf')
    sexphotconf = os.path.join(mypath, '../astromatic/calibration/psfphot.sex')
    photparams = os.path.join(mypath, '../astromatic/calibration/psfphot.param')
    sexnnw = os.path.join(mypath, '../astromatic/calibration/default.nnw')
    sexfilter = os.path.join(mypath, '../astromatic/calibration/default.conv')
    psfconf = os.path.join(mypath, '../astromatic/calibration/psfex.conf')
    nnwfilt = f'-FILTER_NAME {sexfilter} -STARNNW_NAME {sexnnw}'


    # first run source extractor
    cat = frame.replace('.fits', '.cat')
    chk = frame.replace('.fits', '.noise.fits')
    cmd = f'sex -c {sexconf} -PARAMETERS_NAME {sexparam} -CATALOG_NAME {cat} {nnwfilt} -CHECKIMAGE_NAME {chk} {frame}'
    subprocess.check_call(cmd.split())

    # now run scamp to solve the astrometry
    cmd = f'scamp -c {scampconf} {cat}'
    subprocess.check_call(cmd.split())

    # now get a model of the psf
    cmd = f'psfex -c {psfconf} {cat}'
    psf = frame.replace('.fits', '.psf')

    # if the psf already exists then use it if requested
    if not (reuse_psf and os.path.exists(psf)):
        subprocess.check_call(cmd.split())

    # now do photometry by fitting the psf model to the image

    cmd = f'sex -c {sexphotconf} -CATALOG_NAME {cat} -PSF_NAME {psf} -PARAMETERS_NAME {photparams} {nnwfilt} {frame}'
    subprocess.check_call(cmd.split())

    # write a catalog of the stellar sources only
    write_starcat(cat)
    starcat = cat.replace('.cat', '.star.cat')

    # now solve for the zeropoint using the stellar sources
    solve_zeropoint(frame, starcat, psf, zp_fid=27.5)

    with fits.open(frame) as hdul:
        zp = hdul[0].header['MAGZP']

    # now solve for the calibrated catalog
    psf = frame.replace('.fits', '.psf')
    cmd = f'sex -c {sexphotconf} -CATALOG_NAME {cat} -PSF_NAME {psf} -PARAMETERS_NAME {photparams} {nnwfilt} ' \
          f'-MAG_ZEROPOINT {zp} {frame}'
    subprocess.check_call(cmd.split())

    # now write the calibrated star catalog
    write_starcat(cat)

    # now make the inverse variance map using fortran
    wgtname = frame.replace('fits', 'weight.fits')
    chkname = frame.replace('.fits', '.noise.fits')

    if frame.endswith('sciimg.fits'):
        mask = frame.replace('sciimg.fits', 'mskimg.fits')
        mkivar(frame, mask, chkname, wgtname)

    # and make the bad pixel masks and rms images
    make_rms(frame, wgtname)

    # and save it as a fits model
    gsmod = des.DES_PSFEx(psf)
    with fits.open(psf) as f:
        xcen = f[1].header['POLZERO1']
        ycen = f[1].header['POLZERO2']
        psfsamp = f[1].header['PSF_SAMP']

    cpos = galsim.PositionD(xcen, ycen)
    psfmod = gsmod.getPSF(cpos)
    psfimg = psfmod.drawImage(scale=1., nx=25, ny=25, method='real_space')

    # clear wcs and rotate array to be in same orientation as coadded images (north=up and east=left)
    psfimg.wcs = None
    psfimg = galsim.Image(np.fliplr(psfimg.array))

    psfimpath = f'{psf}.fits'
    # save it to the D
    psfimg.write(psfimpath)

    medg(frame)

    # and calculate the limiting magnitude
    lmt_mg = calc_maglimit(starcat)

    with fits.open(frame, mode='update', memmap=False) as f:
        f[0].header['LMT_MG'] = lmt_mg
        if 'SATURATE' not in f[0].header:
            f[0].header['SATURATE'] = 5e4
