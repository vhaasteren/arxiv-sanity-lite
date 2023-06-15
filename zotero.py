"""
Zotero library import functionality
"""

import sqlite3
import json
from aslite.db import get_papers_db, get_tags_db


def add_entry_to_tags(username, new_tag, paper_id):
    with get_tags_db(flag='c', autocommit=True) as tags_db:  # Open db in create mode to allow writes
        # Retrieve the existing tags for the user, or use an empty dict if the user doesn't exist
        tags_dict = tags_db[username] if username in tags_db else {}

        # Add the new paper to the specified tag
        if new_tag in tags_dict:
            tags_dict[new_tag].add(paper_id)
        else:
            tags_dict[new_tag] = {paper_id}

        # Update the user's entry in the db
        tags_db[username] = tags_dict

def create_uncompressed_db(uncompressed_db_fn='uncompressed_papers_db.sqlite'):
    # Open the compressed database
    with get_papers_db() as papers_db:
        # Create a new uncompressed SQLite database
        uncompressed_db = sqlite3.connect(uncompressed_db_fn)

        # Create a new table for the data
        uncompressed_db.execute('''
        CREATE TABLE papers (
            arxiv_id TEXT PRIMARY KEY,
            data TEXT
        )
        ''')

        # Copy the data from the compressed database to the uncompressed one
        for arxiv_id, paper_dict in papers_db.items():
            # We still need to serialize the data, but we don't compress it
            # This allows us to use the JSON functions in SQLite
            uncompressed_db.execute('''
            INSERT INTO papers (arxiv_id, data)
            VALUES (?, ?)
            ''', (arxiv_id, json.dumps(paper_dict)))

        # Commit the changes and close the connection
        uncompressed_db.commit()
        uncompressed_db.close()

def find_paper_by_doi(doi, uncompressed_db_fn='uncompressed_papers_db.sqlite'):
    # Connect to the uncompressed SQLite database
    uncompressed_db = sqlite3.connect(uncompressed_db_fn)

    # Query the database for a paper with a specific DOI
    paper_data = uncompressed_db.execute('''
    SELECT arxiv_id, data
    FROM papers
    WHERE json_extract(data, '$.arxiv_doi') = ?
    ''', (doi,))

    # Fetch the result and close the connection
    result = paper_data.fetchone()
    uncompressed_db.close()

    # If a paper was found, return its ArXiv ID and data
    if result:
        arxiv_id, paper_dict = result
        return arxiv_id, json.loads(paper_dict)

    # If no paper was found, return None
    return None

def chunked(lst, chunk_size):
    """Yield successive chunk_size chunks from lst."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def find_papers_by_dois(dois, chunk_size=900, uncompressed_db_fn='uncompressed_papers_db.sqlite'):
    uncompressed_db = sqlite3.connect(uncompressed_db_fn)
    arxiv_ids = []

    for doi_chunk in chunked(dois, chunk_size):
        placeholders = ', '.join(['?'] * len(doi_chunk))  # Create placeholder for each DOI in the chunk
        sql_query = f'''
        SELECT arxiv_id
        FROM papers
        WHERE json_extract(data, '$.arxiv_doi') IN ({placeholders})
        '''
        cursor = uncompressed_db.execute(sql_query, doi_chunk)
        arxiv_ids.extend([row[0] for row in cursor.fetchall()])

    uncompressed_db.close()

    return arxiv_ids

def add_zotero_entries_to_new_tag(username='vhaasteren', new_tag='zotero', zotero_json='./zotero-library.json', uncompressed_db_fn='uncompressed_papers_db.sqlite', doi_chunk_size=900):

    with open(zotero_json, 'r') as fp:
        zotlib = json.load(fp)

        doi_list = [zl_item['DOI'] for zl_item in zotlib['items'] if 'DOI' in zl_item]

        arxiv_ids = find_papers_by_dois(doi_list, chunk_size=doi_chunk_size, uncompressed_db_fn=uncompressed_db_fn)

        for ii, arxiv_id in enumerate(arxiv_ids):
            add_entry_to_tags(username, new_tag, arxiv_id)
            print(f"Adding: {ii}: {username}, {new_tag}, {arxiv_id}")

def add_zotero_entries_to_new_tag(username, zotlib, new_tag='zotero', uncompressed_db_fn='uncompressed_papers_db.sqlite', doi_chunk_size=900):

    doi_list = [zl_item['DOI'] for zl_item in zotlib['items'] if 'DOI' in zl_item]

    arxiv_ids = find_papers_by_dois(doi_list, chunk_size=doi_chunk_size, uncompressed_db_fn=uncompressed_db_fn)

    for ii, arxiv_id in enumerate(arxiv_ids):
        add_entry_to_tags(username, new_tag, arxiv_id)
        print(f"Adding: {ii}: {username}, {new_tag}, {arxiv_id}")
