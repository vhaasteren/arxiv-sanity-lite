"""
Iterates over the current database and makes best effort to download the papers,
convert them to thumbnail images and save them to disk, for display in the UI.
Atm only runs the most recent 5K papers. Intended to be run as a cron job daily
or something like that.
"""

import os
import time
import random
import requests
import glob
from subprocess import Popen
from aslite.db import get_papers_db, get_metas_db
from google.cloud import storage

# create the tmp directory if it does not exist, where we will do temporary work
TMP_DIR = 'tmp_catchup'
if not os.path.exists(TMP_DIR):
    os.makedirs(TMP_DIR)
# create the thumb directory, where we will store the paper thumbnails
THUMB_DIR = os.path.join('static', 'thumb')
if not os.path.exists(THUMB_DIR):
    os.makedirs(THUMB_DIR)

# Initialize Google API
cloud_bucket_name = 'arxiv-dataset'
cloud_timeout = 40

# open the database, determine which papers we'll try to get thumbs for
pdb = get_papers_db()
n = len(pdb)
mdb = get_metas_db()
metas = list(mdb.items())
metas.sort(key=lambda kv: kv[1]['_time'], reverse=True) # most recent papers first
keys = [k for k,v in metas[5000:]] # oldest papers first

for i, key in enumerate(keys):
    time.sleep(0.01) # for safety

    # the path where we would store the thumbnail for this key
    thumb_path = os.path.join(THUMB_DIR, key + '.jpg')
    if os.path.exists(thumb_path):
        continue

    # fetch the paper
    p = pdb[key]
    print("%d/%d: paper to process: %s" % (i, n, key))

    # get the link to the pdf on arxiv
    url = p['link'].replace('abs', 'pdf')
    temp_file = os.path.join(TMP_DIR, 'paper.pdf')

    # parse that to get the cloud storage pdf
    pdf_basename = url.split('/')[-1]
    foldername = pdf_basename.split('.')[0]
    cloud_storage_pdf = f'arxiv/arxiv/pdf/{foldername}/{pdf_basename}.pdf'
    gs_cloud_storage_pdf = f'gs://arxiv-dataset/arxiv/arxiv/pdf/{foldername}/{pdf_basename}.pdf'

    # attempt to download the pdf
    try:
        print(f"attempting to download pdf from: gs://{cloud_bucket_name}/{cloud_storage_pdf}")

        # Download using gsutil in a subprocess
        pp = Popen(['gsutil', 'cp', gs_cloud_storage_pdf, temp_file])
        t0 = time.time()
        while time.time() - t0 < cloud_timeout: # give it 40 seconds deadline
            ret = pp.poll()
            if not (ret is None):
                # process terminated
                break
            time.sleep(0.1)
        ret = pp.poll()
        if ret is None:
            print(f"convert command did not terminate in {cloud_timeout} seconds, terminating.")
            pp.terminate() # give up
            continue

        print("OK")
    except Exception as e:
        print("error downloading the pdf from cloud storage")
        print(e)

        try:
            print("attempting to download pdf from: ", url)
            x = requests.get(url, timeout=10, allow_redirects=True)
            with open(temp_file, 'wb') as f:
                f.write(x.content)
            print("OK")
        except Exception as e:
            print("error downloading the pdf at url", url)
            print(e)
            continue
        time.sleep(5 + random.uniform(0, 5)) # take a breather

    # mv away the previous temporary files if they exist
    if os.path.isfile(os.path.join(TMP_DIR, 'thumb-0.png')):
        for i in range(8):
            f1 = os.path.join(TMP_DIR, 'thumb-%d.png' % (i,))
            f2 = os.path.join(TMP_DIR, 'thumbbuf-%d.png' % (i,))
            if os.path.isfile(f1):
                cmd = 'mv %s %s' % (f1, f2)
                os.system(cmd)

    # convert pdf to png images per page. spawn async because convert can unfortunately enter an infinite loop, have to handle this.
    # this command will generate 8 independent images thumb-0.png ... thumb-7.png of the thumbnails
    print("converting the pdf to png images")
    pp = Popen(['convert', '%s[0-7]' % (temp_file, ), '-thumbnail', 'x156', os.path.join(TMP_DIR, 'thumb.png')])
    t0 = time.time()
    while time.time() - t0 < 20: # give it 20 seconds deadline
        ret = pp.poll()
        if not (ret is None):
            # process terminated
            break
        time.sleep(0.1)
    ret = pp.poll()
    if ret is None:
        print("convert command did not terminate in 20 seconds, terminating.")
        pp.terminate() # give up
        continue

    if not os.path.isfile(os.path.join(TMP_DIR, 'thumb-0.png')):
        # failed to render pdf, replace with missing image
        #missing_thumb_path = os.path.join('static', 'missing.jpg')
        #os.system('cp %s %s' % (missing_thumb_path, thumb_path))
        #print("could not render pdf, creating a missing image placeholder")
        print("could not render pdf, skipping")
        continue
    else:
        # otherwise concatenate the 8 images into one
        cmd = "montage -mode concatenate -quality 80 -tile x1 %s %s" \
              % (os.path.join(TMP_DIR, 'thumb-*.png'), thumb_path)
        print(cmd)
        os.system(cmd)

    # remove the temporary paper.pdf file
    tmp_pdf = temp_file
    if os.path.isfile(tmp_pdf):
        os.remove(tmp_pdf)
