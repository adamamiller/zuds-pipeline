import os
import sys
import pika
import psycopg2
import requests
import datetime
import logging
import json
import uuid

from pika.exceptions import ConnectionClosed
from liblg import nersc_authenticate


# some constants
cwd = os.path.dirname(__file__)
slurmd = os.path.join(cwd, '../', 'slurm')
mkcoadd_cori = os.path.join(slurmd, 'makecoadd_cori.sh')
mksub_cori = os.path.join(slurmd, 'makesub_cori.sh')
mkvar_cori = os.path.join(slurmd, 'makevariance_cori.sh')
mkcoaddsub_cori = os.path.join(slurmd, 'makecoaddsub_cori.sh')
newt_baseurl = 'https://newt.nersc.gov/newt'

#database_uri = os.getenv('DATABASE_URI')
database_uri = 'host=db port=5432 dbname=ztfcoadd user=ztfcoadd_admin'


def is_up(host):
    """Check to see if cori or edison is up via the NEWT REST API."""

    if host not in ['cori', 'edison']:
        raise ValueError('invalid host "%s". Must be either cori or edison.' % host)

    target = os.path.join(newt_baseurl, 'status', host)

    r = requests.get(target)

    if r.status_code != 200:
        return False

    j = r.json()
    return j['status'] == 'up'


class TaskHandler(object):

    def __init__(self, logger):
        self._reconnect()
        self.logger = logger

    def __del__(self):
        self.connection.close()
        self.msgconnection.close()

    def close(self):
        self.__del__()

    def resolve_dependencies(self, contents, data):
        query = 'SELECT MAX(NERSC_ID) FROM JOB WHERE CORR_ID=%s'
        deps = []
        for dep in data['dependencies']:
            self.cursor.execute(query, (dep,))
            deps.append(str(self.cursor.fetchone()[0]))
        deps = ':'.join(deps)
        contents = contents.replace('DLIST', deps)
        return contents

    def submit_coadd(self, images, catalogs, obase, data, host='cori', scriptname=None):

        # login to nersc
        cookies = nersc_authenticate()

        # create the payload
        with open(mkcoadd_cori, 'r') as f:
            contents = f.read()
        contents = contents.replace('$1', ' '.join(images))
        contents = contents.replace('$2', ' '.join(catalogs))
        contents = contents.replace('$3', obase)
        contents = self.resolve_dependencies(contents, data)

        if scriptname is None:
            scriptname = f'{uuid.uuid4().hex}.sh'

            # first upload the job script to scratch
        path = f'global/cscratch1/sd/dgold/ztfcoadd/job_scripts/{scriptname}'
        target = os.path.join(newt_baseurl, 'file', host, path)
        contents = contents.replace('$4', f'/{os.path.dirname(path)}')
        contents = contents.replace('$5', f'coadd_{scriptname.replace(".sh","")}')
        requests.put(target, data=contents, cookies=cookies)

        target = os.path.join(newt_baseurl, 'queue', host)
        payload = {'jobfile': f'/{path}'}
        self.logger.info(payload)

        r = requests.post(target, data=payload, cookies=cookies)

        if r.status_code != 200:
            raise ValueError(r.content)

        return r.json()['jobid']

    def submit_coaddsub(self, images, catalogs, obase, template,
                        data, host='cori', scriptname=None):

        # login to nersc
        cookies = nersc_authenticate()

        # create the payload
        with open(mkcoaddsub_cori, 'r') as f:
            contents = f.read()

        contents = contents.replace('$1', ' '.join(images))
        contents = contents.replace('$2', ' '.join(catalogs))
        contents = contents.replace('$3', obase)
        contents = contents.replace('$6', template)
        contents = self.resolve_dependencies(contents, data)

        if scriptname is None:
            scriptname = f'{uuid.uuid4().hex}.sh'

            # first upload the job script to scratch
        path = f'global/cscratch1/sd/dgold/ztfcoadd/job_scripts/{scriptname}'
        target = os.path.join(newt_baseurl, 'file', host, path)
        contents = contents.replace('$4', f'/{os.path.dirname(path)}')
        contents = contents.replace('$5', f'coaddsub_{scriptname.replace(".sh","")}')
        requests.put(target, data=contents, cookies=cookies)

        target = os.path.join(newt_baseurl, 'queue', host)
        payload = {'jobfile': f'/{path}'}
        self.logger.info(payload)

        r = requests.post(target, data=payload, cookies=cookies)

        # check the return code
        if r.status_code != 200:
            raise ValueError(r.content)

        return r.json()['jobid']

    def submit_variance(self, images, masks, host='cori', scriptname=None):

        # login to nersc
        cookies = nersc_authenticate()

        # create the payload
        with open(mkvar_cori, 'r') as f:
            contents = f.read()

        contents = contents.replace('$1', '\n'.join(images))
        contents = contents.replace('$2', '\n'.join(masks))

        if scriptname is None:
            scriptname = f'{uuid.uuid4().hex}.sh'

            # first upload the job script to scratch
        path = f'global/cscratch1/sd/dgold/ztfcoadd/job_scripts/{scriptname}'
        target = os.path.join(newt_baseurl, 'file', host, path)

        contents = contents.replace('$3', f'/{os.path.dirname(path)}')
        contents = contents.replace('$4', f'variance_{scriptname.replace(".sh","")}')

        requests.put(target, data=contents, cookies=cookies)

        target = os.path.join(newt_baseurl, 'queue', host)
        payload = {'jobfile': f'/{path}'}
        self.logger.info(payload)

        r = requests.post(target, data=payload, cookies=cookies)

        if r.status_code != 200:
            raise ValueError(r.content)

        return r.json()['jobid']

    def submit_sub(self, images, templates, host='cori', scriptname=None):

        # login to nersc
        cookies = nersc_authenticate()

        # create the payload
        with open(mksub_cori, 'r') as f:
            contents = f.read()

        contents = contents.replace('$1', ' '.join(images))
        contents = contents.replace('$2', ' '.join(templates))

        target = os.path.join(newt_baseurl, 'queue', host)
        payload = {'jobscript': contents}

        self.logger.info(payload)

        r = requests.post(target, data=payload, cookies=cookies)

        if r.status_code != 200:
            raise ValueError(r.content)

        return r.json()['jobid']

    def _reconnect(self):

        try:
            self.close()
        except AttributeError:
            pass
        except ConnectionClosed:
            pass

        # keep a connection open to the database

        while True:
            try:
                self.connection = psycopg2.connect(database_uri)
            except psycopg2.DatabaseError:
                pass
            else:
                break

        while True:
            try:
                self.cursor = self.connection.cursor()
            except ConnectionClosed:
                pass
            else:
                break


        cparams = pika.ConnectionParameters('msgqueue')
        self.msgconnection = pika.BlockingConnection(cparams)
        self.pub_channel = self.msgconnection.channel()

    def __call__(self, ch, method, properties, body):

        # messages are just lists of new images. this method
        # implements the logic to figure out what to do with
        # them

        self._reconnect()
        data = json.loads(body)

        if is_up('cori'):
            host = 'cori'
        elif is_up('edison'):
            host = 'edison'
        else:
            # send the message to the dead letter exchange where it will wait for 10 minutes
            # before attempting to be resubmitted

            query = 'UPDATE JOB SET STATUS=%s, NERSC_ID=NULL WHERE CORR_ID = %s;'
            self.cursor.execute(query, ('DEAD_LETTER', properties.correlation_id))

            return ch.basic_reject(method.delivery_tag, requeue=False)

        scriptname = f'{properties.correlation_id}.sh'

        if data['jobtype'] == 'variance':

            new_images = data['images']
            new_masks = [p.replace('sciimg', 'mskimg') for p in new_images]
            submit_func = self.submit_variance
            args = (new_images, new_masks, host, scriptname)

        elif data['jobtype'] == 'template':

            images = data['images']
            catalogs = [p.replace('fits', 'cat') for p in images]
            submit_func = self.submit_coadd
            coadd_name = data['outfile_name']
            args = (images, catalogs, coadd_name[:-5], data, host, scriptname)

        elif data['jobtype'] == 'coaddsub':

            images = data['images']
            template = data['template']
            cats = [p.replace('.fits', '.cat') for p in images]
            obase = data['outfile_name'][:-5]
            submit_func = self.submit_coaddsub
            args = (images, cats, obase, template, data, host, scriptname)

        else:
            raise ValueError('invalid task type')

        # try submitting
        try:
            jobid = submit_func(*args)
        except ValueError as e:
            logging.info(e.message)
            query = 'UPDATE JOB SET STATUS=%s, NERSC_ID=NULL WHERE CORR_ID = %s;'
            self.cursor.execute(query, ('DEAD_LETTER', properties.correlation_id))
            ch.basic_reject(method.delivery_tag, requeue=False)  # try again in 10

        else:
            self.logger.info(f'Submitted {data["jobtype"]} job {properties.correlation_id} to {host} with '
                             f'queue ID {jobid}.')
            query = 'UPDATE JOB SET NERSC_ID = %s, STATUS=%s, SUBMIT_TIME=%s, SYSTEM=%s WHERE CORR_ID = %s;'
            self.cursor.execute(query, (jobid, 'PENDING', datetime.datetime.now(),
                                        host, properties.correlation_id))
            ch.basic_ack(method.delivery_tag)
            self.pub_channel.basic_publish(exchange='',
                                           routing_key='monitor',
                                           properties=properties,
                                           body=body)

        self.connection.commit()


if __name__ == '__main__':

    # set up a connection to the message queue
    while True:
        try:
            cparams = pika.ConnectionParameters('msgqueue')
            connection = pika.BlockingConnection(cparams)
        except ConnectionClosed:
            pass
        else:
            break

    channel = connection.channel()

    logger = logging.getLogger('run')
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    logger.addHandler(ch)

    # consume stuff from the queue
    handler = TaskHandler(logger)
    channel.basic_qos(prefetch_count=1)

    # try to connect
    while True:
        try:
            channel.basic_consume(handler, queue='jobs')
        except pika.exceptions.ChannelClosed:
            pass
        else:
            break

    channel.start_consuming()
