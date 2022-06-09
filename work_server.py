from NanoPoWWrapper import input_hash, check_pow_output_ready, get_pow_output, clear_pow_queue
from NanoFPGAOverlay import NanoFPGAOverlay

from nanolib.work import validate_work, get_work_value, blake2b
from flask import request, Flask, json
from flask_apscheduler import APScheduler

import struct, time, redis, logging, os, requests, random

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger()

r = redis.Redis(decode_responses=True)
url = os.environ.get('RPC_URL', 'https://rainstorm.city/api')
update_time = int(os.environ.get('UPDATE_TIME', '30'))
crawl_time = int(os.environ.get('CRAWL_TIME', '300'))
app = Flask(__name__)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

fpga_overlay = NanoFPGAOverlay("/home/xilinx/pynq/overlays/nano/conano_pynqz2_87MHz_1V3A.bit")
driver = fpga_overlay.nano_driver
fpga_status = 0


def swap32(i):
    return struct.unpack("<I", struct.pack(">I", i))[0]

def check_work_valid(data, hex_work, diff):
    outcome = 'failed'
    try:
        result = validate_work(data, hex_work, diff)
        outcome = 'success'
        r.incr('pow_success')
    except:
       outcome = 'failed'
       r.incr('pow_failed')
    return outcome

def work_generate(hash, difficulty):
    start_time = time.time()
    # clear any remaining pow in queue
    clear_pow_queue(driver)

    # set to generate pow at send threshold
    if difficulty == 'fffffff800000000':
        driver.set_pow_to_send()
        driver.set_send_threshold(35) # 35
    else:
        driver.set_pow_to_receive()
        driver.set_receive_threshold(41)

    n = 8
    previous_hash = [int(hash[i:i+n], 16) for i in range(0, len(hash), n)]
    reverse_hash = []
    for x in previous_hash:
        reverse_hash.append(swap32(x))

    input_hash(driver, reverse_hash)
    check_pow_output_ready(driver)

    # get work and pop from queue
    output_previous_hash, work_value, nonce_value = get_pow_output(driver) 
    driver.pop_output()

    nonce_value.reverse()
    work_value.reverse()

    final_work = ''.join('{:08X}'.format(x) for x in nonce_value)
    final_work = final_work.lower()
    outcome = check_work_valid(hash, final_work, difficulty)
    diff_data = ''.join('{:08X}'.format(x) for x in work_value)
    diff_data = diff_data.lower()

    work_time = time.time() - start_time
    return diff_data, outcome, final_work, work_time

def get_successor(hash):
    action_json = {'action' : 'block_info', 'json_block': 'true', 'hash': hash}
    x = requests.post(url, json = action_json)
    result = x.json()
#    logging.info(result)
    return result['successor']

def get_block_account(hash):
    action_json = {'action' : 'block_info', 'json_block': 'true', 'hash': hash}
    x = requests.post(url, json = action_json)
    result = x.json()
#    logging.info(result)
    if 'block_account' in result:
        return result['block_account']
    else:
        return 'error'

def get_account_frontier(account):
    action_json = {'action' : 'account_info', 'account': account}
    x = requests.post(url, json = action_json)
    result = x.json()
#    logging.info(result)
    return result['confirmation_height_frontier']

@scheduler.task('interval', id='do_job_2', seconds=crawl_time, misfire_grace_time=900)
def scheduled_crawl():
    global fpga_status
    with scheduler.app.app_context():
        address_list = []
        for user in r.scan_iter(match='nano_*'):
            address_list.append(user)

        for x in range(0, 10):
            random_result = random.choice(address_list)
            logging.info('crawler: checking {} ?needs updating'.format(random_result))
            current_block = r.get(random_result)
            frontier = get_account_frontier(random_result)
            if frontier != current_block:
                logging.info('crawler: frontier needs updating')
                r.expire(random_result, 600)
                r.rpush('pending_orig_hash', frontier)

            else:
                logging.info('crawler: already updated')

@scheduler.task('interval', id='do_job_1', seconds=update_time, misfire_grace_time=900)
def scheduled_task():
    global fpga_status
    with scheduler.app.app_context():
        if fpga_status == 0:
            while r.llen('pending_orig_hash') > 0:
                previous_hash = r.lpop('pending_orig_hash')
                account = get_block_account(previous_hash)
                if account == 'error':
                    continue

                frontier = get_account_frontier(account)
                r.set(account, frontier)

                if r.exists(frontier):
                    logging.info('precache: already precached')
                    continue

                fpga_status = 1
                diff_data, outcome, final_work, work_time = work_generate(frontier, 'fffffff800000000')
                fpga_status = 0
                logging.info('{}, {}, {}, {}, {}'.format(frontier, final_work, outcome, diff_data, work_time))
                if outcome == 'failed':
                    logging.info('precache: precaching failed, recycle')
                    r.rpush('pending_orig_hash', frontier)
                else:
                    logging.info('precache: precaching success')
                    r.set(frontier, '{},{}'.format(final_work, diff_data))
                    r.expire(previous_hash, 600)
                    return
        else:
            logging.info('precache: fpga busy')

@app.route('/', methods=['POST'])
def log():
    global fpga_status
    if request.method == 'POST':
        r.incr('count_requests')
        data = request.get_json()
        logging.info('work requested: {}'.format(data['hash']))
        r.rpush('pending_orig_hash', data['hash'])

        work_time = 0
        # Check if we have pre-cached version
        if r.exists(data['hash']):
            r.incr('count_precache')
            logging.info('Pre-cached')
            precache_data = r.get(data['hash'])
            precache_split = precache_data.split(',')
            final_work = precache_split[0]
            diff_data = precache_split[1]
            outcome = 'precache'

        else:
            r.incr('count_live')
            logging.info('live: Generating Work using FPGA')
            fpga_status = 1
            diff_data, outcome, final_work, work_time = work_generate(data['hash'], data['difficulty'])
            r.set(data['hash'], '{},{}'.format(final_work, diff_data))
            fpga_status = 0

        logging.info('{}, {}, {}, {}, {}'.format(data['hash'], final_work, outcome, diff_data, work_time))

        return {"difficulty" : diff_data, "outcome" : outcome, "work" : final_work, "hash" : data['hash'], "work_time" : work_time}
    else:
        return 'error: not post'

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
