import json, sys, codecs
try:
    with codecs.open('run.json', 'r', encoding='utf-16le') as f:
        d = json.load(f)
    print('Name:', d.get('name'))
    print('Status:', d.get('status'))
    print('Conclusion:', d.get('conclusion'))
    print('Title:', d.get('display_title'))
    print('check_suite_url:', d.get('check_suite_url'))
    print('jobs_url:', d.get('jobs_url'))
except Exception as e:
    print('Error:', e)
