import psycopg2 
import argparse
import astropy
from astropy.io import fits
from astropy.table import vstack, Table

import sys, os, re, glob, distutils
from distutils.util import strtobool
import numpy as np

from desitarget.db import my_psql
import desitarget.bin.tractor_load as dbload 

def read_schema_table(fn,cand=False):
    skiprows=3
    a=np.loadtxt(fn,\
                 dtype=str,skiprows=skiprows,delimiter=" ",comments=")",\
                 usecols=(0,1))
    a=np.char.strip(a)
    return np.char.replace(a,',','')
        
def read_decam_tables(table_dir='/project/projectdirs/desi/users/burleigh'):
    print("reading tables from %s" % table_dir)
    print("reading %s" % os.path.join(table_dir,'decam_table_cand'))
    cand=read_schema_table(os.path.join(table_dir,'decam_table_cand'),cand=True)
    flux=read_schema_table(os.path.join(table_dir,'decam_table_flux'))
    aper=read_schema_table(os.path.join(table_dir,'decam_table_aper'))
    wise=read_schema_table(os.path.join(table_dir,'decam_table_wise'))
    return np.concatenate((cand,flux,aper,wise),axis=0)

def name2type(var, psql_type): 
    if psql_type == 'real': return float(var)
    elif psql_type == 'double': return float(var)
    elif psql_type == 'integer': return int(var)
    elif psql_type == 'bigint': return int(var)
    elif psql_type == 'boolean': return bool(var)
    elif psql_type == 'text': return str(var)
    else:
        print("psql_type=%s,NOT supported, crash" % psql_type)
        sys.exit()


def diff_rows(trac_at,db_dict):
    '''trac_at -- tractor astropy table
    db_dict -- dict with psql text file columns as keys'''
    # DB keys
    db_keys= ['brickname','objid'] + [b+'flux' for b in ['g','r','z']]
    dtypes= ['s']+['i'] + ['f']*3
    # Tractor keys
    trac_keys= ['brickname','objid'] + ['decam_flux']*3
    trac_i= [None]*2 + [1,2,4]
    # Difference
    for db_key,typ,trac_key,i in zip(db_keys,dtypes,trac_keys,trac_i):
        print('db key,val=',db_key, usetype(db_dict[db_key]), \
              'trac key,i,val=', trac_key,i,trac_at[trac_key][i])

parser = argparse.ArgumentParser(description="test")
parser.add_argument("--list_of_cats",action="store",help='list of tractor cats',default='dr3_cats_qso.txt',required=True)
parser.add_argument("--table_dir",action="store",default='/project/projectdirs/desi/users/burleigh',help='relative path to directory containing the decam_tables_* files',required=True)
parser.add_argument("--seed",type=int,action="store",default=1,required=False)
parser.add_argument("--outdir",action="store",default='/project/projectdirs/desi/users/burleigh',required=False)
args = parser.parse_args()

# choose 10 cats randomly
fits_files= dbload.read_lines(args.list_of_cats)
rand = np.random.RandomState(args.seed)
if len(fits_files) > 10:
    ndraws=10
    keep= rand.uniform(1, len(fits_files), ndraws).astype(int)-1
    fits_files= fits_files[keep]
else: fits_files= [fits_files[0]]
# for each, choose a random objid and get corresponding row from DB
for fn in fits_files:
    t=Table(fits.getdata(fn, 1))
    # Get db keys from table files IN CORRECT ORDER
    db_keys= read_decam_tables(table_dir=args.table_dir) 
    db_keys,db_types= db_keys[:,0],db_keys[:,1]
    # Random rows
    ndraws=1
    keep= rand.uniform(1, len(t), ndraws).astype(int)-1
    for row in keep:
        # grab this row from DB
        brickname= '%s' % t[row]['brickname']
        objid= '%d' % t[row]['objid']
        cmd="select * from decam_table_cand as c JOIN decam_table_flux as f ON f.cand_id=c.id JOIN decam_table_aper as a ON a.cand_id=c.id JOIN decam_table_wise as w ON w.cand_id=c.id WHERE c.brickname like '%s' and c.objid=%s" % (brickname,objid) 
        print("selecting row %d from db with cmd:\n%s\n" % (row,cmd)) #and saving output as %s" % \
        #cmd="select "
        #for db_key in db_keys: cmd+= "%s " % db_key
        #cmd+= "from decam_table_cand as c JOIN decam_table_flux as f ON f.cand_id=c.id JOIN decam_table_aper as a ON a.cand_id=c.id JOIN decam_table_wise as w ON w.cand_id=c.id WHERE c.brickname like '%s' and c.objid=%s" % (brickname,objid) 
        #name='db_row_%d.csv' % row
        #        (row,cmd,os.path.join(args.outdir,name))
        #my_psql.select(cmd,name,outdir=args.outdir)
        # Connect and fetchone() the results
        con= psycopg2.connect(host='scidb2.nersc.gov', user='desi_admin', database='desi')
        cursor = con.cursor()
        cursor.execute(cmd) 
        vals = cursor.fetchone()
        con.close()
        #for a,b,v in zip(db_keys,db_types,vals): print a,b,v
        # put in dict and compare
        db_vals= {}
        for db_key,db_type,val in zip(db_keys,db_types,vals): 
            db_vals[db_key]= name2type(val, db_type)
            #print "db_type=%s,db_key=%s,db_vals[db_key]=%s,val=%s" % (db_type,db_key,str(db_vals[db_key]),str(val))
        ####### Final check
        print("FINAL comparison")
        # Decam table
        for db_key,trac_key,trac_i in zip(*dbload.decam_table_keys()):
            print("trac_key=%s, trac_cat=%s, db=%s" % (trac_key,str(t[row][trac_key][trac_i]),str(db_vals[db_key])))
        # Aperature table
        #for db_key,trac_key,trac_i,ap_i in zip(*dbload.aper_table_keys()):
        #    aper[db_key]= tractor[trac_key][:,trac_i,ap_i].data
        ## Wise table
        #for db_key,trac_key,trac_i in zip(*dbload.wise_default_keys()):
        #    wise[db_key]= tractor[trac_key][:,trac_i].data
        #if 'wise_lc_flux' in tractor.colnames:
        #    for db_key,trac_key,trac_i,epoch_i in zip(*dbload.wise_lc_keys()):
        #        wise[db_key]= tractor[trac_key][:,trac_i,epoch_i].data
        ## Candidate table
        #for db_key,trac_key in zip(*dbload.cand_default_keys(t.colnames)):
        #    cand[db_key]= tractor[trac_key].data 
        #for db_key,trac_key,trac_i in zip(*dbload.cand_array_keys()):
        #    cand[db_key]= tractor[trac_key][:,trac_i].data
        #######
        
# Compare Tractor Catalogue data to db
#print 'reading in %s' % os.path.join(args.outdir,name)
#db=  my_psql.read_psql_csv(os.path.join(args.outdir,name))
#print 'comparing to Tractor catalogue'
#print 'trac=',trac[row]
#print 'db=',db
#diff_rows(t[row],db)
    
print('done')
