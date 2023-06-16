"""
This script is intended to wake up every 30 min or so (eg via cron),
it checks for any new arxiv papers via the arxiv API and stashes
them into a sqlite database.
"""

import sys
import time
import random
import logging
import argparse

from aslite.arxiv import get_response, parse_response
from aslite.db import get_papers_db, get_metas_db

import re
import json
import feedparser
from datetime import datetime
from dateutil import tz


def author_string_to_dict(authors_str):
    """Convert a string of authors to a list of dictionaries"""

    # Remove any parentheses and the contained information
    authors_str = re.sub(r'\([^)]*\)', '', authors_str)
    # Split the authors on commas and "and"
    authors_list = [author.strip() for author in re.split(',| and ', authors_str)]
    # Convert to desired format
    authors_dict_list = [{'name': author} for author in authors_list if author]

    return authors_dict_list

def backlog_item_to_api(item):
    """Convert an arxiv backlog item to an API item"""

    api_item = dict()

    api_item['title'] = item.pop('title')       # Title
    api_item['summary'] = item.pop('abstract')  # Abstract
    api_item['authors'] = author_string_to_dict(item.pop('authors'))
    api_item['_idv'] = item['id']               # arXiv id, like 2208.07377v2
    api_item['id'] = item['id']
    api_item['_id'] = item.pop('id')            # arXiv id, like 2208.07377

    vsns = item.pop('versions')
    api_item['_version'] = vsns[0]['version']   # Like: v2
    api_item['_time_str'] = vsns[0]['created']  # Like: Sep 01 2022
    dtobj = datetime.strptime(vsns[0]['created'], '%a, %d %b %Y %H:%M:%S %Z')
    api_item['_time'] = dtobj.replace(tzinfo=tz.tzutc()).timestamp()

    # Find the default category
    cat_scheme = 'http://arxiv.org/schemas/atom'
    cat = item.pop('dategories', '')
    categories = cat.strip().split(' ')
    api_item['arxiv_primary_category'] = {'term': categories[0], 'scheme': cat_scheme}

    # Fill in all that remains
    api_item.update(**item)

    # Finally, add to the (perhaps existing) tags
    api_item_tags = api_item.setdefault('tags', {})
    add_categories = [{'term': category, 'scheme': cat_scheme, 'label': None} for category in categories]
    api_item_tags.extend(add_categories)

    return api_item


if __name__ == '__main__':

    logging.basicConfig(level=logging.INFO, format='%(name)s %(levelname)s %(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

    parser = argparse.ArgumentParser(description='Arxiv Backlog Utility')
    parser.add_argument('-f', '--file', type=str, default="", help='JSON file with arxiv backlog')
    args = parser.parse_args()

    print(args)

    # Adding blanked-all 'astro-ph' here as well
    categories = ['astro-ph', 'astro-ph.CO', 'astro-ph.HE', 'astro-ph.IM', 'gr-qc']

    pdb = get_papers_db(flag='c')
    mdb = get_metas_db(flag='c')

    # Read the large backlog json file
    arxiv_backlog_raw, arxiv_backlog = [], []
    with open(args.file, 'r') as fp:
        for line in fp:
            arxiv_backlog_raw.append(json.loads(line))

    # Convert (approximately) to the formap of the API
    for backlog_item in arxiv_backlog_raw:
        try:
            arxiv_backlog.append(backlog_item_to_api(backlog_item))
        except KeyError:
            pass


    # process the batch of retrieved papers
    nhad, nnew, nreplace = 0, 0, 0
    for p in arxiv_backlog:
        pid = p['_id']
        if pid in pdb:
            if p['_time'] > pdb[pid]['_time']:
                # replace, this one is newer
                store(p)
                nreplace += 1
            else:
                # we already had this paper, nothing to do
                nhad += 1
        else:
            # new, simple store into database
            store(p)
            nnew += 1
    prevn = len(pdb)
    total_updated += nreplace + nnew

    # some diagnostic information on how things are coming along
    logging.info(arxiv_backlog[0]['_time_str'])
    logging.info("k=%d, out of %d: had %d, replaced %d, new %d. now have: %d" %
         (k, len(papers), nhad, nreplace, nnew, prevn))

    # exit with OK status if anything at all changed, but if nothing happened then raise 1
    sys.exit(0 if total_updated > 0 else 1)
