import os
import pika
import time
import requests
import psycopg2

newt_baseurl = 'https://newt.nersc.gov/newt'
nersc_username = os.getenv('NERSC_USERNAME')
nersc_password = os.getenv('NERSC_PASSWORD')
database_uri = os.getenv('DATABASE_URI')


def authenticate():

    target = os.path.join(newt_baseurl, 'login')
    payload = {'username':nersc_username,
               'password':nersc_password}

    r = requests.post(target, data=payload)

    if r.status_code != 200:
        raise ValueError('Unable to Authenticate')

    return r.cookies


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

    cparams = pika.ConnectionParameters('msgqueue')
    pcon = pika.BlockingConnection(cparams)
    channel = pcon.channel()
    channel.queue_declare(queue='monitor')

    connection = psycopg2.connect(database_uri)
    cursor = connection.cursor()

    ncookies = authenticate()

    query = "SELECT CORR_ID, NERSC_ID, SYSTEM, STATUS FROM JOB WHERE STATUS=%s OR STATUS=%s;"
    uquery = 'UPDATE JOB SET STATUS=%s'

    job_cache = {}

    while True:

        new_messages = fetch_new_messages(channel)

        for message in new_messages:
            job_cache[message[1].properties.correlation_id] = message

        cursor.execute(query, 'PENDING', 'RUNNING')
        active_jobs = cursor.fetchall()

        for corr_id, nersc_id, machine, status in active_jobs:

            target = os.path.join(newt_baseurl, 'queue', f'{machine}', f'{nersc_id}', 'sacct')
            r = requests.get(target, cookies=ncookies)

            data = r.json()
            current_status = data['status'].upper()
            args = []
            resubmit = False

            if current_status == status:
                continue

            else:
                args.append(status)

            if status == 'COMPLETED':
                uquery += ', TIMEUSE=%s'
                args.append(data['timeuse'])
                del job_cache[corr_id]

            elif status == 'FAILED' or status == 'TIMEOUT':
                # resubmit
                resubmit = True
                args[0] = 'UNSUBMITTED'
                body = job_cache[corr_id][2]
                del job_cache[corr_id]

            uquery += ' WHERE CORR_ID = %s;'
            args.append(corr_id)

            # need to do this before sending the message
            cursor.execute(uquery, *args)
            connection.commit()

            if resubmit:
                channel.basic_publish(exchange='',
                                      routing_key='jobs',
                                      body=body,
                                      properties=pika.BasicProperties(
                                          correlation_id=corr_id
                                      ))

        time.sleep(10.)  # only check every ten seconds
