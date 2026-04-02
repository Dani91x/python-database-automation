import urllib.request, json
try:
    url = "https://api.github.com/repos/Dani91x/python-database-automation/actions/runs/23786706394/jobs"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode('utf-8'))
    for job in data['jobs']:
        for step in job['steps']:
            if step['conclusion'] == 'failure':
                print(f"FAILED_STEP: {step['name']}")
                print(f"JOB_LOG_URL: {job['html_url']}")
except Exception as e:
    print(f"Error: {e}")
