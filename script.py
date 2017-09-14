import requests, json, os, sys, pdb, traceback, time
from bs4 import BeautifulSoup

db_file = 'db.txt'

def prog(txt):
    print(txt, end='...')
    sys.stdout.flush()

def check_db(urls):
    if type(urls) != dict:
        raise Exception()
    deleted = {}
    for line in open(db_file):
        url = line.strip()
        if url in urls:
            deleted[url] = urls[url]
            del urls[url]
    return deleted

def add_to_db(urls):
    with open(db_file, 'a') as f:
        for url in urls:
            f.write(url + '\n')

def send(txt):
    if config['debug']:
        print('-----------')
        print(txt)
        print('-----------')
        return
    token = config['telegram_token']
    chat_id = config['telegram_chat_id']
    url = 'https://api.telegram.org/bot' + token + '/sendMessage'
    requests.post(url, params={
        'chat_id': chat_id,
        'text': txt,
    })

def admin_action(txt):
    send('ADMIN ACTION REQUIRED: %s' % txt)
    pdb.set_trace()

br = ' '
replacements = [
    ('&amp;' , '&'),
    ('&amp;' , '&'),
    ('&apos;', '\''),
    ('&#x27;', '\''),
    ('&#150;', '–'),
    ('&#x2F;', '/'),
    ('&#39;' , '\''),
    ('&#039;', '\''),
    ('&#47;' , '/'),
    ('&lt;'  , '<'),
    ('&gt;'  , '>'),
    ('&nbsp;', ' '),
    ('&quot;', '"'),
    ('<br>'  , br),
    ('<br/>' , br),
    ('<br />', br),
    ('\n'    , br),
]
    
def prettify(txt):
    for replace_what, replace_with in replacements:
        txt = txt.replace(replace_what, replace_with)
    return ' '.join(txt.split())

def send_job(job):
    send('%s: %s ::: %s ::: %s' % (
        prettify(job['source']),
        prettify(job['title']),
        prettify(job['body']),
        prettify(job['url']),
    ))
    
def parse_upwork_json(url):
    # DO NOT RETURN RECENT JOBS WITHOUT LOGIN
    txt = requests.get(url, headers={
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    }).text
    pos1 = txt.index('var phpVars = ')
    pos2 = txt.index('{', pos1)
    pos3 = txt.index(';\n', pos1)
    s = txt[pos2:pos3]
    jsn = json.loads(s)
    jobs = {url: {
        'source': 'upwork',
        'title': 'FIRST RUN',
        'body': '',
        'url': '',
        'time': '',
    }}
    for job in jsn['jobs']:
        job_url = 'https://www.upwork.com/jobs/%s/' % job['ciphertext']
        jobs[job_url] = {
            'source': 'upwork',
            'title': job['title'],
            'body': job['description'],
            'url': job_url,
            'time': job['publishedOn'],
        }
    existing = check_db(jobs)
    if len(existing) == 1 and url in existing:
        admin_action('len(existing) == 1, url = %s' % url)
    for job in sorted(jobs.values(), key=lambda x: x['time']):
        send_job(job)
    add_to_db(jobs)
    pdb.set_trace()

def parse_upwork_rss(url, title):
    source = 'upwork_rss:%s' % title
    prog('Requesting %s' % (source,))
    txt = requests.get(url).text
    prog('Parsing')
    bs = BeautifulSoup(txt, 'xml')
    jobs = {url: {
        'source': source,
        'title': 'FIRST RUN',
        'body': '',
        'url': url,
        'pos': -1,
    }}
    items = bs.find_all('item')
    for pos, item in enumerate(items):
        body = item.description.text
        idx1 = body.index('<b>Posted On</b>:')
        body = body[:idx1]
        jobs[item.guid.text] = {
            'source': source,
            'title': item.title.text,
            'body': body,
            'url': item.link.text,
            'pos': len(items) - pos,
        }
    prog('Checking db')
    existing = check_db(jobs)
    print('%s / %s new' % (len(jobs), len(jobs) + len(existing)), end='...')
    if len(existing) == 1 and url in existing:
        admin_action('len(existing) == 1, source = %s, url = %s' % (source, url))
    prog('Sending messages')
    for job in sorted(jobs.values(), key=lambda x: x['pos']):
        send_job(job)
    prog('Adding to db')
    add_to_db(jobs)
    print('done')
    

if not os.path.exists('config.json'):
    print('Please, create config.json file with "telegram_token" and "telegram_chat_id" fields.')
    sys.exit()
if not os.path.exists(db_file):
    print('Creating %s file.' % db_file)
    open(db_file, 'w')
config = json.load(open('config.json'))

try:
    while True:
        for title, url in config['upwork_rss']:
            parse_upwork_rss(url, title)
        print('Sleep for %d minutes' % config['sleep_minutes'])
        time.sleep(config['sleep_minutes'] * 60)
except Exception as e:
    exc = traceback.format_exc()
    print(exc)
    send(exc)
    pdb.post_mortem()
