import db
import numpy as np
from astropy.coordinates import SkyCoord
from astropy import units as u
from secrets import get_secret
import penquins



def estimate_seeing(image):
    """Estimate the seeing on an image by comparing its catalog to GAIA stars."""

    # connect to kowalski to query gaia
    username = get_secret('kowalski_username')
    password = get_secret('kowalski_password')
    kowalski = penquins.Kowalski(username=username, password=password)
    catalog = image.catalog

    if catalog is None:
        catalog = db.PipelineFITSCatalog.from_image(image)

    # get a list of gaia stars
    coordlist = []
    for row in catalog.data:
        ra = row['sky_centroid_icrs.ra']
        dec = row['sky_centroid_icrs.dec']
        coordlist.append((ra, dec))

    q = {"query_type": "cone_search",
         "object_coordinates": {
             "radec": coordlist,
             "cone_search_radius": "1",
             "cone_search_unit": "arcsec"
         },
         "catalogs": {
             "Gaia_DR2": {
                 "filter": {
                     "parallax": {"$gt": 0.},
                     "phot_g_mean_mag": {"$gt": 16.}  # only return stars
                 },
                 "projection": {
                     "_id": 1,
                     "ra": 1,
                     "dec": 1
                 }
             }
         },
         "kwargs": {}
    }
    result = kowalski.query(q)
    if result['status'] != 'done':
        raise ValueError(f'Kowalski Error: {result}')

    stars = result['result_data']['Gaia_DR2']
    matchra = []
    matchdec = []
    for d in stars.values():
        if len(d) > 0:
            matchra.append(d[0]['ra'])
            matchdec.append(d[0]['dec'])

    matchcoord = SkyCoord(matchra, matchdec, unit='deg')
    catcoord = catalog['sky_centroid_icrs']

    idx, d2d, _ = catcoord.match_to_catalog_sky(matchcoord)
    ind = d2d < 1 * u.arcsec
    catok = catalog[ind]

    seeings = []
    for row in catok:
        fwhm = 2 * np.sqrt(np.log(2) * (row['semimajor_axis_sigma']**2 + row['semiminor_axis_sigma']**2))
        seeings.append(fwhm.value)

    medsee = np.nanmedian(seeings) * np.median(image.pixel_scale)
    return medsee
