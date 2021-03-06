# Licensed under a 3-clause BSD style license - see LICENSE.rst
# -*- coding: utf-8 -*-
"""
===========================
desitarget.mock.bgs_durham
===========================

Builds target/truth files from already existing mock data
"""

from __future__ import (absolute_import, division)
#
import numpy as np
import os, re
import desitarget.mock.io
import desitarget.io
from   desitarget import bgs_mask
import os
from   astropy.table import Table, Column
import fitsio
import desiutil.io
import desispec.brick

############################################################
def bgs_selection(data, mag_faintest=20.0, mag_priority_split=19.5, mag_bright=15.0):
    """
    Apply the selection function to determine the target class of each entry in
    the input catalog.

    Parameters:
    -----------
        data: dict
            Data required for selection
        mag_faintest:    float
            Hard faint limit for inclusion in survey.
        mag_priority_split:  float
            Magintude fainter than which galaxies have lower priority
        mag_bright:      float
            Hard bright limit for inclusion in survey.
    """
    # Parameters
    SELECTION_MAG_NAME = 'SDSSr_true'

    # Will populate this array with the bitmask values of each target class
    target_class = np.zeros(len(data[SELECTION_MAG_NAME]),dtype=np.int64) - 1
    #priority     = np.zeros(len(data[SELECTION_MAG_NAME]),dtype=np.int64) - 1

    fainter_than_bright_limit  = data[SELECTION_MAG_NAME]  >= mag_bright
    brighter_than_split_mag    = data[SELECTION_MAG_NAME]   < mag_priority_split
    fainter_than_split_mag     = data[SELECTION_MAG_NAME]  >= mag_priority_split
    brighter_than_faint_limit  = data[SELECTION_MAG_NAME]   < mag_faintest

    # Bright sample
    select_bright_sample               = (fainter_than_bright_limit) & (brighter_than_split_mag)
    target_class[select_bright_sample] = bgs_mask.mask('BGS_BRIGHT')
    #priority[select_bright_sample]     = bgs_mask['BGS_BRIGHT'].priorities['UNOBS']

    # Nearby ('100pc') sample -- everything in the input table that isn't a WD
    # Expect to refine this in future
    select_faint_sample               = (fainter_than_split_mag) & (brighter_than_faint_limit)
    target_class[select_faint_sample] = bgs_mask.mask('BGS_FAINT')
    #priority[select_faint_sample]     = bgs_mask['BGS_FAINT'].priorities['UNOBS']

    return target_class#, priority

############################################################
def build_mock_target(root_mock_dir='', output_dir='',
                      mock_ext='hdf5',
                      targets_name='bgs_durahm_mxxl_targets.fits',
                      truth_name='bgs_durahm_mxxl_truth.fits',
                      selection_name='bgs_durahm_mxxl_selection.fits',
                      mag_faintest=20.0, mag_priority_split=19.5, mag_bright=15.0, 
                      remake_cached_targets=False,
                      write_cached_targets=True,
                      rand_seed=42):

    """Builds a Target and Truth files from a series of mock files.

    Parameters:
    ----------
        rand_seed: int
            seed for random number generator.
    """
    desitarget.io.check_fitsio_version()
    np.random.seed(seed=rand_seed)

    targets_filename = os.path.join(output_dir, targets_name)
    truth_filename   = os.path.join(output_dir, truth_name)

    target_exists    = os.path.exists(targets_filename)
    truth_exists     = os.path.exists(truth_filename)

    # Do we need to store copies of the targets and truth on disk?
    write_new_files = (remake_cached_targets) or not (target_exists and truth_exists)

    if not write_new_files:
        # Report the size of the existing input files
        targets_filesize = os.path.getsize(targets_filename) / (1024.0**3)
        truth_filesize   = os.path.getsize(targets_filename) / (1024.0**3)

        # Just read from the files we already have. Need to convert to astropy
        # table for consistency of return types.
        print("Reading existing files:")
        print("    Targets: {} ({:4.3f} Gb)".format(targets_filename,targets_filesize))
        targets   = Table(desitarget.io.whitespace_fits_read(targets_filename,ext='TARGETS'))
        print("    Truth:   {} ({:4.3f} Gb)".format(truth_filename,truth_filesize))
        truth     = Table(desitarget.io.whitespace_fits_read(truth_filename,ext='TRUTH'))
        file_list = Table(desitarget.io.whitespace_fits_read(truth_filename,ext='SOURCES'))
    else:
        # Read the mocks on disk. This returns a dict.
        # FIXME should just use table here too?
        data, file_list = desitarget.mock.io.read_mock_bgs_mxxl_brighttime(root_mock_dir=root_mock_dir,mock_ext=mock_ext)
        data_keys       = list(data.keys())
        n               = len(data[data_keys[0]])
        
        # Allocate target classes and priorities
        target_class = bgs_selection(data,
                                     mag_faintest       = mag_faintest,
                                     mag_priority_split = mag_priority_split,
                                     mag_bright         = mag_bright)
        # Identify all targets
        in_target_list = target_class >= 0
        ii             = np.where(in_target_list)[0]
        n_selected     = len(ii)

        print("Properties read from mock: {}".format(data.keys()))
        print("n_items in full catalog: {}".format(n))

        print('Selection criteria:')
        for criterion in ['mag_faintest','mag_priority_split','mag_bright']:
            print(" -- {:30s} {}".format(criterion,locals().get(criterion)))

        print("n_items after selection: {}".format(n_selected))
            
        # targetid  = np.random.randint(2**62, size=n_selected)

        # Targetids are row numbers in original input
        #targetid  = np.arange(0,n)[ii]

        # Targetids are brick/object combos from original input
        #BRICKID_FACTOR           = 1e10 # Max 10^10 objects per brick
        #combined_brick_object_id = data['brickid'][ii]*BRICKID_FACTOR + data['objid'][ii]
        #targetid                 = np.asarray(combined_brick_object_id,dtype=np.int64)

        # This routine assigns targetIDs that encode the mapping of each row in the
        # target outputfile to a filenumber and row in the set of mock input files.
        # This targetID will be further modified when all target lists are merged.
        targetid = desitarget.mock.io.encode_rownum_filenum(data['rownum'][ii],data['filenum'][ii])

        # Assign random subpriorities for now
        subprior  = np.random.uniform(0., 1., size=n_selected)

        # Assign DESI-standard bricknames
        # CAREFUL: These are not the bricknames used by the input catalog!
        brickname = desispec.brick.brickname(data['RA'][ii], data['DEC'][ii])

        # assign target flags and true types
        desi_target_pop   = np.zeros(n_selected, dtype='i8')
        bgs_target_pop    = np.zeros(n_selected, dtype='i8') 
        mws_target_pop    = np.zeros(n_selected, dtype='i8') 
        bgs_target_pop[:] = target_class[ii]

        # APC This is a string? 
        # FIXME (APC) This looks totally wrong, especially if the target class
        # encodes a combination of bits such that mask.names() returns a list.
        # The 'true type' should be something totally separate (an LRG is an
        # LRG, regardless of whether it's in the North or South, etc.).
        true_type_pop     = np.asarray(desitarget.targets.target_bitmask_to_string(target_class[ii],bgs_mask),dtype='S10')

        # Write the Targets to disk
        targets = Table()
        targets['TARGETID']    = targetid
        targets['BRICKNAME']   = brickname
        targets['RA']          = data['RA'][ii]
        targets['DEC']         = data['DEC'][ii]
        targets['DESI_TARGET'] = desi_target_pop
        targets['BGS_TARGET']  = bgs_target_pop
        targets['MWS_TARGET']  = mws_target_pop
        targets['SUBPRIORITY'] = subprior

        # Write the Truth to disk
        truth = Table()
        truth['TARGETID']  = targetid
        truth['BRICKNAME'] = brickname
        truth['RA']        = data['RA'][ii]
        truth['DEC']       = data['DEC'][ii]
        truth['TRUEZ']     = data['Z'][ii]

        # True type is just targeted type for now.
        truth['TRUETYPE']  = true_type_pop

        # File list
        file_list = np.array(file_list,dtype=[('FILE','|S500'),('NROWS','i8')])
        assert(np.all([len(x[0]) < 500 for x in file_list]))

        # Write Targets
        if write_cached_targets:
            print('Writing target list and truth for this mock...')
            with fitsio.FITS(targets_filename,'rw',clobber=True) as fits:
                fits.write(desiutil.io.encode_table(targets).as_array(),extname='TARGETS',clobber=True)

            # Write truth, slightly convoluted because we write two tables
            with fitsio.FITS(truth_filename,'rw',clobber=True) as fits:
                fits.write(desiutil.io.encode_table(truth).as_array(), extname='TRUTH')
                fits.write(file_list, extname='SOURCES')                
 
            print("Wrote new files:")
            print("    Targets: {}".format(targets_filename))
            print("    Truth:   {}".format(truth_filename))

    return targets, truth, Table(file_list)
