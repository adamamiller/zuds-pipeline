import os
import pika
import time
import json
import requests
import psycopg2
import datetime
from pika.exceptions import ConnectionClosed
from liblg import nersc_authenticate
import pandas as pd

newt_baseurl = 'https://newt.nersc.gov/newt'
#database_uri = os.getenv('DATABASE_URI')
database_uri = 'host=db port=5432 dbname=ztfcoadd user=ztfcoadd_admin'

_status_dict ={
    'R': 'RUNNING',
    'PD': 'PENDING',
    'F': 'FAILED',
    'TO': 'TIMEOUT',
    'CD': 'COMPLETED',
    'CA': 'CANCELLED'
}


NTRIES = 10

def fetch_new_messages(ch):

    result = []

    while True:
        msg = ch.basic_get('monitor')
        if msg == (None, None, None):
            break
        result.append(msg)
        ch.basic_ack(msg[0].delivery_tag)

    return result


if __name__ == '__main__':

    while True:
        try:
            connection = psycopg2.connect(database_uri)
        except psycopg2.DatabaseError:
            pass
        else:
            break

    cursor = connection.cursor()
    ncookies = nersc_authenticate()
    job_cache = {}

    while True:

        query = "SELECT CORR_ID, NERSC_ID, SYSTEM, STATUS FROM JOB WHERE STATUS=%s OR STATUS=%s " \
                "ORDER BY SUBMIT_TIME DESC LIMIT 1000"  # the 'order by' is important - ensures correct resub order

        while True:
            try:
                cparams = pika.ConnectionParameters('msgqueue')
                pcon = pika.BlockingConnection(cparams)
            except ConnectionClosed:
                pass
            else:
                break

        channel = pcon.channel()
        channel.queue_declare(queue='monitor')

        new_messages = fetch_new_messages(channel)

        for message in new_messages:
            job_cache[message[1].correlation_id] = message

        cursor.execute(query, ('PENDING', 'RUNNING'))
        active_jobs = cursor.fetchall()[::-1]  # want the latest jobs, in ascending order (hence the [::-1])

        for corr_id, nersc_id, machine, status in active_jobs:

            # database inserts dashes for some reason
            corr_id = corr_id.replace('-', '')

            uquery = 'UPDATE JOB SET STATUS=%s'
            target = os.path.join(newt_baseurl, 'queue', f'{machine}', f'{nersc_id}', 'sacct')

            data = {}
            for _ in range(NTRIES):
                r = requests.get(target, cookies=ncookies)
                try:
                    data = r.json()
                except json.JSONDecodeError:
                    continue  # try it again ... sometimes NEWT returns a bad response on repeated queries
                else:
                    if data['status'].upper() == 'ERROR':
                        continue  # again, try it again....
                    else:
                        break

            if data == {}:
                raise requests.HTTPError(f'Could not get a good response from sacct after {NTRIES} tries')

            current_status = _status_dict[data['status'].upper()]
            args = []
            resubmit = False

            if current_status == status:
                continue

            else:
                args.append(current_status)

            if current_status == 'COMPLETED':
                uquery += ', TIMEUSE=%s'
                args.append(data['timeuse'])
                bodyd = json.loads(job_cache[corr_id][2])

                if bodyd['jobtype'] == 'template':
                    # if the template is done mark it as such

                    query = 'INSERT INTO TEMPLATE (PATH, FILTER, QUADRANT, FIELD, CCDNUM, ' \
                            'MINDATE, MAXDATE, PIPELINE_SCHEMA_ID, PROCDATE, NIMG) VALUES (' \
                            '%s, %s, %s, %s, %s, %s, %s ,%s, %s, %s) RETURNING ID'

                    for job in bodyd['jobs']:
                        path = job['outfile_name']
                        band = job['filter']
                        quadrant = job['quadrant']
                        field = job['field']
                        ccdnum = job['ccdnum']
                        mindate = pd.to_datetime(job['mindate']).to_pydatetime()
                        maxdate = pd.to_datetime(job['maxdate']).to_pydatetime()
                        pipeline_schema_id = job['pipeline_schema_id']
                        procdate = datetime.datetime.utcnow()

                        cursor.execute(query, (path, band, quadrant, field, ccdnum, mindate,
                                       maxdate, pipeline_schema_id, procdate, len(job['imids'])))
                        tmplid = cursor.fetchone()[0]

                        # now update the association table
                        query = 'INSERT INTO TEMPLATEIMAGEASSOC (TEMPLATE_ID, IMAGE_ID) VALUES (%s, %s)'
                        for imid in job['imids']:
                            cursor.execute(query, (tmplid, imid))

                    connection.commit()

                elif bodyd['jobtype'] == 'coaddsub':

                    for job in bodyd['jobs']:

                        query = 'INSERT INTO COADD (PATH, FILTER, QUADRANT, FIELD, CCDNUM, ' \
                                'MINDATE, MAXDATE, PIPELINE_SCHEMA_ID, PROCDATE, NIMG) VALUES (' \
                                '%s, %s, %s, %s, %s, %s, %s ,%s, %s, %s) RETURNING ID'

                        path = job['outfile_name']
                        band = job['filter']
                        quadrant = job['quadrant']
                        field = job['field']
                        ccdnum = job['ccdnum']
                        mindate = pd.to_datetime(job['mindate']).to_pydatetime()
                        maxdate = pd.to_datetime(job['maxdate']).to_pydatetime()
                        pipeline_schema_id = job['pipeline_schema_id']
                        procdate = datetime.datetime.utcnow()

                        cursor.execute(query, (path, band, quadrant, field, ccdnum, mindate,
                                       maxdate, pipeline_schema_id, procdate, len(job['imids'])))
                        coaddid = cursor.fetchone()[0]

                        # now update the association table
                        query = 'INSERT INTO COADDIMAGEASSOC (COADD_ID, IMAGE_ID) VALUES (%s, %s)'
                        for imid in job['imids']:
                            cursor.execute(query, (coaddid, imid))

                        # now do the subtraction


                    connection.commit()

                del job_cache[corr_id]

            elif current_status in ['FAILED', 'TIMEOUT', 'CANCELLED']:
                # resubmit
                resubmit = True
                args[0] = 'UNSUBMITTED'
                body = job_cache[corr_id][2]
                del job_cache[corr_id]

            uquery += ' WHERE CORR_ID = %s'
            args.append(corr_id)

            # need to do this before sending the message
            cursor.execute(uquery, tuple(args))
            connection.commit()

            if resubmit:
                channel.basic_publish(exchange='',
                                      routing_key='jobs',
                                      body=body,
                                      properties=pika.BasicProperties(
                                          correlation_id=corr_id
                                      ))

        pcon.close()
        time.sleep(10.)  # only check every ten seconds
