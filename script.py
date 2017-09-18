import requests, json, os, sys, pdb, traceback, time, urllib.parse
from bs4 import BeautifulSoup

db_file = 'db.txt'
websites_db_dir = 'websites'

def prog(txt):
    print(txt, end='...')
    sys.stdout.flush()

def check_db(urls):
    prog('Checking db')
    if type(urls) != dict:
        raise Exception()
    deleted = {}
    for line in open(db_file):
        url = line.strip()
        if url in urls:
            deleted[url] = urls[url]
            del urls[url]
    prog('%s / %s new' % (len(urls), len(urls) + len(deleted)))
    return deleted

def add_to_db(urls):
    with open(db_file, 'a') as f:
        for url in urls:
            f.write(url + '\n')

def send(txt):
    global last_message
    last_message = cur_time
    if config['debug']:
        print('-----------')
        print(txt)
        print('-----------')
        return
    prog('send len = %d' % len(txt))
    token = config['telegram_token']
    chat_id = config['telegram_chat_id']
    url = 'https://api.telegram.org/bot' + token + '/sendMessage'
    resp = requests.post(url, params={
        'chat_id': chat_id,
        'text': txt[:4000] + ('\n..........' if len(txt) > 4000 else ''),
    })
    if resp.status_code != 200:
        admin_action('TELEGRAM ERROR %s' % resp.text)

def admin_action(txt):
    send('ADMIN ACTION REQUIRED: %s' % txt)
    pdb.set_trace()

def req_text(req, url):
    if req.status_code != 200:
        send('STATUS CODE %d for url=%s' % (req.status_code, url))
        return None
    txt = req.content.decode('utf-8')
    return txt

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
    ('&bull;', '•'),
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
    txt = req_text(requests.get(url), source)
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
    existing = check_db(jobs)
    if len(existing) == 1 and url in existing:
        admin_action('len(existing) == 1, source = %s, url = %s' % (source, url))
        prog('Sending messages')
    for job in sorted(jobs.values(), key=lambda x: x['pos']):
        send_job(job)
    prog('Adding to db')
    add_to_db(jobs)
    print('done')

def extract(text, start_marker, end_marker):
    res = []
    idx = 0
    while True:
        idx_start = text.find(start_marker, idx)
        if idx_start == -1:
            return res
        idx_start += len(start_marker)
        idx_end = text.find(end_marker, idx_start)
        if idx_end == -1:
            return res
        idx = idx_end + len(end_marker)
        res.append(text[idx_start:idx_end])

def get_fl_ru_token(html):
    return extract(html, "var _TOKEN_KEY = '", "'")[0]

def check_fl_ru(keywords):
    for keyword in keywords:
        prog('Checking fl_ru "%s" keyword' % keyword)
        prog('Getting fl_ru token')
        s = requests.Session()
        url = 'https://www.fl.ru/projects/'
        text = req_text(s.get(url), 'GET: %s' % url)
        if text is None:
            return
        token = get_fl_ru_token(text)
        prog('token=%s' % token)
        data = (
                'action=postfilter&kind=5&pf_category=&pf_subcategory=&'
                'comboe_columns%5B1%5D=0&comboe_columns%5B0%5D=0&comboe_column_id=0&'
                'comboe_db_id=0&comboe=%D0%92%D1%81%D0%B5+%D1%81%D0%BF%D0%B5%D1%86%D0%B8%D0%B0%D0%BB%D0%B8%D0%B7%D0%B0%D1%86%D0%B8%D0%B8&'
                'location_columns%5B1%5D=0&location_columns%5B0%5D=0&location_column_id=0&location_db_id=0&'
                'location=%D0%92%D1%81%D0%B5+%D1%81%D1%82%D1%80%D0%B0%D0%BD%D1%8B&pf_cost_from=&currency_text_columns%5B1%5D=0&'
                'currency_text_columns%5B0%5D=2&currency_text_column_id=0&currency_text_db_id=2&pf_currency=2&'
                'currency_text=%D0%A0%D1%83%D0%B1&'
            ) + 'pf_keywords=%s&u_token_key=%s' % (urllib.parse.quote(keyword), urllib.parse.quote(token))
        prog('Making POST request')
        text = req_text(s.post(
            url,
            data=data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        ), 'POST: fl.ru %s' % keyword)
        # token = get_fl_ru_token(text)
        # prog('token=%s' % token)
        # pdb.set_trace()
        projects = extract(text, 'id="project-item', '"')
        source = 'fl.ru: %s' % keyword
        jobs = {source: {
            'url': source,
            'pos': -100,
        }}
        for pos, project in enumerate(projects):
            url = 'https://www.fl.ru/projects/%s' % project
            jobs[url] = {
                'url': url,
                'pos': -pos,
            }
        existing = check_db(jobs)
        if len(existing) == 1 and url in existing:
            admin_action('len(existing) == 1, source = %s, url = %s' % (source, url))
        if len(jobs) > 0:
            prog('Sending messages')
            for job in sorted(jobs.values(), key=lambda x: x['pos']):
                send('fl.ru: %s' % job['url'])
        prog('Adding to db')
        add_to_db(jobs)
        print('done')
        

def get_strings(html, select=None):
    bs = BeautifulSoup(html, 'lxml')
    if select is not None:
        bs = bs.select(select)[0]
    for s in bs(['script', 'style']):
        s.extract()
    txt = bs.getText(separator=' ')
    res = []
    for line in txt.split('\n'):
        pret = prettify(line)
        if pret != '':
            res.append(pret)
    return res

url_replace = [
    ('/', '_'),
    ('.', '_'),
    ('?', '_'),
    ('=', '_'),
    ('&', '_'),
]

def get_website_file(url):
    if url.startswith('http://'):
        url = url[len('http://'):]
    if url.startswith('https://'):
        url = url[len('https://'):]
    if url.startswith('www.'):
        url = url[len('www.'):]
    if url.endswith('/'):
        url = url[:-1]
    for repl_what, repl_with in url_replace:
        url = url.replace(repl_what, repl_with)
    return os.path.join(websites_db_dir, url)

def check_website(task):
    if type(task) == str:
        task = {'url': task}
    if 'select' not in task:
        task['select'] = None
    url = task['url']
    prog('Requesting %s' % url)
    text = req_text(requests.get(url), url)
    txt = get_strings(text, select=task['select'])
    fname = get_website_file(url)
    if os.path.exists(fname):
        prev_lines = set()
        for line in open(fname):
            line = line.strip()
            prev_lines.add(line)
    else:
        prog('First version of %s' % fname)
        prev_lines = []
    new_txt = []
    for line in txt:
        if line not in prev_lines:
            new_txt.append(line)
    if len(new_txt) == 0:
        print('No changes. done.')
        return
    prog('%d new lines' % len(new_txt))
    send('%s ::: %s' % (url, ' / '.join(new_txt)))
    prog('Writing new strings')
    with open(fname, 'w') as f:
        f.write('\n'.join(txt))
    # pdb.set_trace()
    print('done')

if not os.path.exists('config.json'):
    print('Please, create config.json file with "telegram_token" and "telegram_chat_id" fields.')
    sys.exit()
if not os.path.exists(db_file):
    print('Creating %s file.' % db_file)
    open(db_file, 'w')
if not os.path.exists(websites_db_dir):
    print('Creating %s dir.' % websites_db_dir)
    os.makedirs(websites_db_dir)
config = json.load(open('config.json'))

last_message = 0
last_upwork_req = 0
last_websites_req = 0
last_fl_ru_req = 0
try:
    while True:
        cur_time = time.time() / 60
        if cur_time - last_upwork_req >= config['upwork_sleep']:
            for title, url in config['upwork_rss']:
                if 1:
                    parse_upwork_rss(url, title)
            last_upwork_req = cur_time
        if cur_time - last_websites_req >= config['websites_sleep']:
            for url in config['websites']:
                if 1:
                    check_website(url)
            last_websites_req = cur_time
        if cur_time - last_fl_ru_req >= config["fl_ru_sleep"]:
            if 1:
                check_fl_ru(config['fl_ru_keywords'])
            last_fl_ru_req = cur_time
        if cur_time - last_message >= config['ping_period']:
            send('OK')
        print(end=',')
        sys.stdout.flush()
        time.sleep(60)
except Exception as e:
    if type(e).__name__ == 'BdbQuit':
        sys.exit()
    exc = traceback.format_exc()
    print(exc)
    send(exc)
    pdb.post_mortem()
