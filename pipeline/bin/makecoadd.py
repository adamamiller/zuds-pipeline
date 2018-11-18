import os
import numpy as np
import liblg
import uuid
from astropy.io import fits


if __name__ == '__main__':

    import argparse

    # set up the argument parser and parse the arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-basename', dest='output_basename', required=True,
                        help='Basename of output coadd.', nargs=1)
    parser.add_argument('--input-catalogs', dest='cats', required=True,
                        help='List of catalogs to use for astrometric alignment.', nargs='+')
    parser.add_argument('--input-frames', dest='frames', nargs='+', required=True,
                        help='List of frames to coadd.')
    args = parser.parse_args()

    # distribute the work to each processor

    if args.frames[0].startswith('@'):
        frames = np.genfromtxt(args.frames[0][1:], dtype=None, encoding='ascii')
        frames = np.atleast_1d(frames)
    else:
        frames = args.frames

    if args.cats[0].startswith('@'):
        cats = np.genfromtxt(args.cats[0][1:], dtype=None, encoding='ascii')
        cats = np.atleast_1d(cats)
    else:
        cats = args.cats

    # now set up a few pointers to auxiliary files read by sextractor
    wd = os.path.dirname(__file__)
    confdir = os.path.join(wd, '..', 'config', 'makecoadd')
    sexconf = os.path.join(confdir, 'scamp.sex')
    scampparam = os.path.join(confdir, 'scamp.param')
    filtname = os.path.join(confdir, 'default.conv')
    nnwname = os.path.join(confdir, 'default.nnw')
    scampconf = os.path.join(confdir, 'scamp.conf')
    swarpconf = os.path.join(confdir, 'default.swarp')

    clargs = '-PARAMETERS_NAME %s -FILTER_NAME %s -STARNNW_NAME %s' % (scampparam, filtname, nnwname)

    mycats = ' '.join(cats)

    # First scamp everything
    # make a random dir for the output catalogs
    scamp_outpath = f'/tmp/{uuid.uuid4().hex}'
    os.makedirs(scamp_outpath)

    syscall = 'scamp -c %s %s' % (scampconf, mycats)
    syscall += f' -REFOUT_CATPATH {scamp_outpath}'
    liblg.execute(syscall, capture=False)

    allims = ' '.join(frames)
    out = args.output_basename[0] + '.fits'
    oweight = args.output_basename[0] + '.weight.fits'

    # put all swarp temp files into a random dir
    swarp_rundir = f'/tmp/{uuid.uuid4().hex}'
    os.makedirs(swarp_rundir)

    syscall = 'swarp -c %s %s -IMAGEOUT_NAME %s -WEIGHTOUT_NAME %s' % (swarpconf, allims, out, oweight)
    syscall += f' -VMEM_DIR {swarp_rundir} -RESAMPLE_DIR {swarp_rundir}'
    liblg.execute(syscall, capture=False)

    # Now postprocess it a little bit
    with fits.open(frames[0]) as f:
        h0 = f[0].header
        band = h0['FILTER']

    with fits.open(out, mode='update') as f:
        header = f[0].header

        if 'r' in band.lower():
            header['FILTER'] = 'r'
        elif 'g' in band.lower():
            header['FILTER'] = 'g'
        elif 'i' in band.lower():
            header['FILTER'] = 'i'
        else:
            raise ValueError('Invalid filter "%s."' % band)

        # TODO make this more general
        header['PIXSCALE'] = 1.0

        # Add the sky back in as a constant
        f[0].data += 150.

    # Make a new catalog
    outcat = args.output_basename[0] + '.cat'
    noise = args.output_basename[0] + '.noise.fits'
    syscall = 'sex -c %s -CATALOG_NAME %s -CHECKIMAGE_NAME %s -MAG_ZEROPOINT 27.5 %s'
    syscall = syscall % (sexconf, outcat, noise, out)
    syscall = ' '.join([syscall, clargs])
    liblg.execute(syscall, capture=False)

    # And zeropoint the coadd, putting results in the header
    liblg.solve_zeropoint(out, outcat)

    # Now retrieve the zeropoint
    with fits.open(out) as f:
        zp = f[0].header['MAGZP']

    # redo sextractor
    syscall = 'sex -c %s -CATALOG_NAME %s -CHECKIMAGE_NAME %s -MAG_ZEROPOINT %f %s'
    syscall = syscall % (sexconf, outcat, noise, zp, out)
    syscall = ' '.join([syscall, clargs])
    liblg.execute(syscall, capture=False)
    liblg.make_rms(out, oweight)
    liblg.medg(out)
