from wsgiref.util import request_uri
import requests
import time
import os

ssh_host = os.environ['EC2_SERVER']
host_port = os.environ['HOST_PORT']

# Validate the application started successfully
try:
    # give the app some time to start up
    time.sleep(15)
    
    response = requests.get(f"http://{ssh_host}:{host_port}")
    if response.status_code == 200:
        print('Application is running successfully!')
    else:
        print('Application deployment was not successful')
except Exception as ex:
    print(f'Connection error happened: {ex}')
    print('Application not accessible at all')