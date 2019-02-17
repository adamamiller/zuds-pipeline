import numpy as np
from photutils import CircularAnnulus
from image_registration import chi2_shift_iterzoom
from scipy import ndimage
from copy import deepcopy
from astropy.wcs import WCS
from astropy.io import fits

__all__ = ['ZTFphot', 'yao_photometry_single']


def mylinear_fit(x, y, yerr, npar=2):
    '''
    Ref:
        1. Numerical Recipes, 3rd Edition, p745, 781 - 782
        2. http://web.ipac.caltech.edu/staff/fmasci/ztf/ztf_pipelines_deliverables.pdf, p37
    '''
    assert len(x) == len(y)
    assert len(y) == len(yerr)

    Sx = np.sum(x)
    Sy = np.sum(y)
    Sxy = np.sum(x * y)
    Sxx = np.sum(x ** 2)
    N = len(x)

    Sx_sigma = np.sum(x * yerr ** 2)
    Sxx_sigma = np.sum(x ** 2 * yerr ** 2)
    S_sigma = np.sum(yerr ** 2)

    if npar == 1:
        Fpsf = Sxy / Sxx
        e_Fpsf = np.sqrt(Sxx_sigma) / Sxx
        a = 0
    elif npar == 2:
        Fpsf = (N * Sxy - Sx * Sy) / (N * Sxx - Sx ** 2)
        a = (Sxx * Sy - Sx * Sxy) / (N * Sxx - Sx ** 2)
        e_Fpsf = np.sqrt(N ** 2 * Sxx_sigma - 2 * N * Sx * Sx_sigma + Sx ** 2 * S_sigma) / (N * Sxx - Sx ** 2)

    x_mean = np.mean(x)
    y_mean = np.mean(y)
    pearson_r = np.sum((x - x_mean) * (y - y_mean)) / np.sqrt(np.sum((x - x_mean) ** 2)) / np.sqrt(
        np.sum((y - y_mean) ** 2))
    return Fpsf, e_Fpsf, a, pearson_r


class ZTFphot(object):

    def __init__(self, name, ra, dec, imgpath, psfpath, bad_threshold=-500,
                 r_psf=3, r_bkg_in=10, r_bkg_out=15):
        self.name = name
        self.ra = ra
        self.dec = dec
        self.imgpath = imgpath
        self.psfpath = psfpath
        self.r_psf = r_psf
        self.r_bkg_in = r_bkg_in
        self.r_bkg_out = r_bkg_out
        self.bad_threshold = bad_threshold
        self.length = 2 * r_psf + 1

        try:
            hd = fits.open(imgpath)[1].header
            dt = fits.open(imgpath)[1].data
        except IndexError:
            hd = fits.open(imgpath)[0].header
            dt = fits.open(imgpath)[0].data

        n_dty = dt.shape[0]
        n_dtx = dt.shape[1]
        w = WCS(hd)
        world = np.array([[ra, dec]], np.float_)
        pixcrd = w.wcs_world2pix(world, 1)
        # need to subtract 1 !
        # since physical coordinate in python starts from 0, not 1
        pixX = pixcrd[0, 0] - 1
        pixY = pixcrd[0, 1] - 1

        self.pixX = pixX
        self.pixY = pixY
        self.n_dty = n_dty
        self.n_dtx = n_dtx

        # plt.imshow(dt, origin = 'power left', vmin = -10, vmax = 100)
        # plt.plot(pixX, pixY, 'r.')

        if np.isnan(pixX) == 1 or np.isnan(pixY) == 1:
            self.status = False
            print('Set status to False -- Target outside of image!')

        else:
            pixXint = int(np.rint(pixX))
            pixYint = int(np.rint(pixY))
            self.pixXint = pixXint
            self.pixYint = pixYint

            # require no bad pixels in the central 3*3 small cutout
            small_cutout = dt[pixYint - 1: pixYint + 2, pixXint - 1: pixXint + 2]

            if pixXint < 0 or pixYint < 0 or pixYint > n_dty or pixXint > n_dtx:
                self.status = False
                print('Set status to False -- Target outside of image!')
            elif pixXint < r_psf or pixYint < r_psf or pixYint >= (n_dty - r_psf) or pixXint >= (n_dtx - r_psf):
                print('Set status to False -- Target on the edge of the image!')
                self.status = False
            elif np.sum(small_cutout < bad_threshold) != 0:
                self.status = False
                print('Set status to False -- Bad pixel in the central 3x3 cutout!')
            else:
                self.status = True

        self.gain = hd['GAIN']


        # load psf cutout
        psf_fn = fits.open(psfpath)[0].data[12 - r_psf:12 + r_psf + 1, 12 - r_psf:12 + r_psf + 1]
        self.psf_fn = psf_fn

    def load_source_cutout(self):
        '''
        imgpath = pobj.imgpath
        pixX = pobj.pixX
        pixY = pobj.pixY
        pixXint = pobj.pixXint
        pixYint = pobj.pixYint
        bad_threshold = pobj.bad_threshold
        n_dty = pobj.n_dty
        n_dtx = pobj.n_dtx
        r_psf = pobj.r_psf
        length = pobj.length
        '''
        imgpath = self.imgpath
        pixX = self.pixX
        pixY = self.pixY
        pixXint = self.pixXint
        pixYint = self.pixYint
        bad_threshold = self.bad_threshold
        n_dty = self.n_dty
        r_psf = self.r_psf
        length = self.length
        # n_dtx = self.n_dtx

        dt = fits.open(imgpath)[1].data
        if (pixYint + r_psf + 2) > n_dty:
            new_patch = np.zeros((10, dt.shape[1]))
            dt = np.vstack([dt, new_patch])

        scr_fn_1 = dt[pixYint - r_psf - 1: pixYint + r_psf + 2,
                   pixXint - r_psf - 1: pixXint + r_psf + 2]
        xoff_tobe = pixX - pixXint
        yoff_tobe = pixY - pixYint
        scr_fn_ = ndimage.shift(scr_fn_1, [-yoff_tobe, -xoff_tobe], order=3,
                                mode='reflect', cval=0.0, prefilter=True)
        scr_fn = scr_fn_[1:-1, 1:-1]

        bad_mask = scr_fn <= bad_threshold
        nbad = np.sum(bad_mask)
        scr_fn[bad_mask] = np.nan
        self.bad_mask = bad_mask
        self.nbad = nbad
        self.scr_fn = scr_fn

        if nbad != 0:
            print('%d bad pixels in %d*%d source frame' % (nbad, length, length))

    def find_optimal_coo(self):
        psf_fn = self.psf_fn
        scr_fn = self.scr_fn
        pixX = self.pixX
        pixY = self.pixY
        imgpath = self.imgpath

        hd = fits.open(imgpath)[1].header
        w = WCS(hd)
        xoff, yoff, exoff, eyoff = chi2_shift_iterzoom(psf_fn, scr_fn)
        pixX_cor = pixX + xoff
        pixY_cor = pixY + yoff
        pixel = np.array([[pixX_cor + 1, pixY_cor + 1]], np.float_)
        newcrd = w.wcs_pix2world(pixel, 1)
        ra_cor = newcrd[0][0]
        dec_cor = newcrd[0][1]
        self.ra_cor = ra_cor
        self.dec_cor = dec_cor

    def load_bkg_cutout(self):
        '''
        imgpath = pobj.imgpath
        pixX = pobj.pixX
        pixY = pobj.pixY
        bad_threshold = pobj.bad_threshold
        r_bkg_in = pobj.r_bkg_in
        r_bkg_out = pobj.r_bkg_out
        '''
        imgpath = self.imgpath
        pixX = self.pixX
        pixY = self.pixY
        bad_threshold = self.bad_threshold
        r_bkg_in = self.r_bkg_in
        r_bkg_out = self.r_bkg_out

        dt = fits.open(imgpath)[1].data
        positions = [(pixX, pixY)]
        annulus_aperture = CircularAnnulus(positions,
                                           r_in=r_bkg_in, r_out=r_bkg_out)
        annulus_masks = annulus_aperture.to_mask(method='center')
        annulus_data = annulus_masks[0].multiply(dt)

        bkg_fn = deepcopy(annulus_data)
        bad_bkg_mask = annulus_data <= bad_threshold
        bkg_fn[bad_bkg_mask] = np.nan
        nbad_bkg = np.sum(bad_bkg_mask)

        self.bad_bkg_mask = bad_bkg_mask
        self.nbad_bkg = nbad_bkg

        setnan = annulus_masks[0].data == 0
        bkg_fn[setnan] = np.nan
        bkgstd = np.nanstd(bkg_fn)

        self.bkgstd = bkgstd
        self.bkg_fn = bkg_fn

    def get_scr_cor_fn(self, manual_mask, col_mask_start, col_mask_end,
                       row_mask_start, row_mask_end):
        '''
        psf_fn = pobj.psf_fn
        bad_mask = pobj.bad_mask
        scr_fn = pobj.scr_fn
        psf_fn = pobj.psf_fn
        gain = pobj.gain
        bkgstd = pobj.bkgstd
        '''
        bad_mask = self.bad_mask
        scr_fn = self.scr_fn
        gain = self.gain
        bkgstd = self.bkgstd
        r_psf = self.r_psf

        if manual_mask == True:
            manual_mask = np.zeros((2 * r_psf + 1, 2 * r_psf + 1), dtype=bool)
            manual_mask[col_mask_start:col_mask_end, row_mask_start:row_mask_end] = True
            bad_mask[manual_mask] = True

        ind = (scr_fn / gain + bkgstd ** 2 < 0)
        if np.sum(ind) != 0:
            print('%d pixel removed to get positive photometric error' % np.sum(ind))
            bad_mask[ind] = 1

        scr_cor_fn = deepcopy(scr_fn)
        scr_cor_fn[bad_mask] = np.nan

        self.scr_cor_fn = scr_cor_fn
        self.bad_mask = bad_mask
        self.nbad = np.sum(bad_mask)

    def fit_psf(self):
        '''
        psf_fn = pobj.psf_fn
        scr_cor_fn = pobj.scr_cor_fn
        bad_mask = pobj.bad_mask
        bkgstd = pobj.bkgstd
        gain  = pobj.gain
        length = pobj.length
        '''
        psf_fn = self.psf_fn
        scr_cor_fn = self.scr_cor_fn
        bad_mask = self.bad_mask
        bkgstd = self.bkgstd
        gain = self.gain
        length = self.length

        _psf_ravel = psf_fn[~bad_mask]
        _scr_cor_ravel = scr_cor_fn[~bad_mask]
        _yerrsq = _scr_cor_ravel / gain + bkgstd ** 2

        _yerr = np.sqrt(_yerrsq)

        # one-parameter fit
        Fpsf, eFpsf, apsf, pearson_r = mylinear_fit(_psf_ravel, _scr_cor_ravel, _yerr, npar=1)
        # calculate chi
        resi = _psf_ravel * Fpsf - _scr_cor_ravel
        res_over_error = resi / _yerr
        # plt.plot(resi, 'r')
        # plt.plot(_yerr, 'k')
        chi2 = np.sum(res_over_error ** 2)
        chi2_red = chi2 / (length ** 2 - 1)

        self._psf_ravel = _psf_ravel
        self._scr_cor_ravel = _scr_cor_ravel
        self.Fpsf = Fpsf
        self.eFpsf = eFpsf
        self.apsf = apsf
        self.r_value = round(pearson_r, 3)
        self.Fap = np.sum(_scr_cor_ravel) / np.sum(_psf_ravel)
        self.chi2_red = chi2_red
        self.yerrs = _yerr


def yao_photometry_single(sub, psf, ra, dec):
    pobj = ZTFphot(None, ra, dec, sub, psf)
    pobj.load_source_cutout()
    pobj.load_bkg_cutout()
    pobj.get_scr_cor_fn(False, 0, 0, 0, 0)
    pobj.fit_psf()
    return pobj
