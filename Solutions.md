</details>

******

<details>
<summary>Exercise 1: Working with Subnets in AWS</summary>
 <br />

```sh
import boto3

ec2 = boto3.client('ec2')
subnets = ec2.describe_subnets()
for subnet in subnets["Subnets"]:
    if subnet["DefaultForAz"]:
        print(subnet["SubnetId"])

```

</details>

******

<details>
<summary>Exercise 2: Working with IAM in AWS </summary>
 <br />

```sh
import boto3

iam = boto3.client('iam')
iam_users = iam.list_users()

last_active_user = iam_users["Users"][0]

for iam_user in iam_users["Users"]:
    print(iam_user["UserName"])
    print(iam_user["PasswordLastUsed"])
    print("---------------------------")
    
    if last_active_user["PasswordLastUsed"] < iam_user["PasswordLastUsed"]:
        last_active_user = iam_user

print("Last active user:")
print(last_active_user["UserId"])
print(last_active_user["UserName"])
print(last_active_user["PasswordLastUsed"])

```

</details>

******

<details>
<summary>Exercise 3: Automate Running and Monitoring Application on EC2 instance</summary>
 <br />

```sh
# Pre requisites
Do the following manually to prepare your AWS region for the script execution 
- open the SSH port 22 in the default security group in your default VPC 
- create key-pair for your ec2 instance. Download the private key of the key-pair and set its access permission to 400 mode
- set the values for: image_id, key_name, instance_type and ssh_privat_key_path in your python script.    
```

```sh
# Code
from distutils import command
import boto3
import time
import paramiko
import requests
import schedule

ec2_resource = boto3.resource('ec2')
ec2_client = boto3.client('ec2')

# set all needed variable values

image_id = 'ami-031eb8d942193d84f'
key_name = 'boto3-server-key'
instance_type = 't2.small'

# the pem file must have restricted 400 permissions: chmod 400 absolute-path/boto3-server-key.pem
ssh_privat_key_path = '/Users/nanajanashia/Downloads/boto3-server-key.pem' 
ssh_user = 'ec2-user'
ssh_host = '' # will be set dynamically below

# Start EC2 instance in default VPC

# check if we have already created this instance using instance name
response = ec2_client.describe_instances(
    Filters=[
        {
            'Name': 'tag:Name',
            'Values': [
                'my-server',
            ]
        },
    ]
) 

instance_already_exists = len(response["Reservations"]) != 0 and len(response["Reservations"][0]["Instances"]) != 0
instance_id = ""

if not instance_already_exists: 
    print("Creating a new ec2 instance")
    ec2_creation_result = ec2_resource.create_instances(
        ImageId=image_id, 
        KeyName=key_name, 
        MinCount=1, 
        MaxCount=1, 
        InstanceType=instance_type,
        TagSpecifications=[
            {
                'ResourceType': 'instance',
                'Tags': [
                    {
                        'Key': 'Name',
                        'Value': 'my-server'
                    },
                ]
            },
        ],

    )
    instance = ec2_creation_result[0]
    instance_id = instance.id
else:
    instance = response["Reservations"][0]["Instances"][0]
    instance_id = instance["InstanceId"]
    print("Instance already exists")

# Wait until the EC2 server is fully initialized
ec2_instance_fully_initialised = False

while not ec2_instance_fully_initialised:
    print("Getting instance status")
    statuses = ec2_client.describe_instance_status(
        InstanceIds = [instance_id]
    )
    if len(statuses['InstanceStatuses']) != 0:
        ec2_status = statuses['InstanceStatuses'][0]

        ins_status = ec2_status['InstanceStatus']['Status']
        sys_status = ec2_status['SystemStatus']['Status']
        state = ec2_status['InstanceState']['Name']
        ec2_instance_fully_initialised = ins_status == 'ok' and sys_status == 'ok' and state == 'running'
    if not ec2_instance_fully_initialised:
        print("waiting for 30 seconds")
        time.sleep(30)

print("Instance fully initialised")

# get the instance's public ip address
response = ec2_client.describe_instances(
    Filters=[
        {
            'Name': 'tag:Name',
            'Values': [
                'my-server',
            ]
        },
    ]
) 
instance = response["Reservations"][0]["Instances"][0]
ssh_host = instance["PublicIpAddress"]

# Install Docker on the EC2 server & start nginx container

commands_to_execute = [
    'sudo yum update -y && sudo yum install -y docker',
    'sudo systemctl start docker',
    'sudo usermod -aG docker ec2-user',
    'docker run -d -p 8080:80 --name nginx nginx'
]

# connect to EC2 server
print("Connecting to the server")
print(f"public ip: {ssh_host}")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(hostname=ssh_host, username=ssh_user, key_filename=ssh_privat_key_path)

# install docker & start nginx 
for command in commands_to_execute:
    stdin, stdout, stderr = ssh.exec_command(command)
    print(stdout.readlines())

ssh.close()

# Open port 8080 on nginx server, if not already open
sg_list = ec2_client.describe_security_groups(
    GroupNames=['default']
)

port_open = False
for permission in sg_list['SecurityGroups'][0]['IpPermissions']:
    print(permission)
    # some permissions don't have FromPort set
    if 'FromPort' in permission and permission['FromPort'] == 8080:
        port_open = True

if not port_open:
    sg_response = ec2_client.authorize_security_group_ingress(
        FromPort=8080,
        ToPort=8080,
        GroupName='default',
        CidrIp='0.0.0.0/0',
        IpProtocol='tcp'
    )

# Scheduled function to check nginx application status and reload if not OK 5x in a row
app_not_accessible_count = 0

def restart_container():
    print('Restarting the application...')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=ssh_host, username=ssh_user, key_filename=ssh_privat_key_path)
    stdin, stdout, stderr = ssh.exec_command('docker start nginx')
    print(stdout.readlines())
    ssh.close()
    # reset the count
    global app_not_accessible_count
    app_not_accessible_count = 0
    
    print(app_not_accessible_count)


def monitor_application():
    global app_not_accessible_count
    try:
        response = requests.get(f"http://{ssh_host}:8080")
        if response.status_code == 200:
            print('Application is running successfully!')
        else:
            print('Application Down. Fix it!')
            app_not_accessible_count += 1
            if app_not_accessible_count == 5:
                restart_container()
    except Exception as ex:
        print(f'Connection error happened: {ex}')
        print('Application not accessible at all')
        app_not_accessible_count += 1
        if app_not_accessible_count == 5:
            restart_container()
        return "test"
    
schedule.every(10).seconds.do(monitor_application)  

while True:
    schedule.run_pending()


```

</details>

******

<details>
<summary>Exercise 4: Working with ECR in AWS</summary>
 <br />

```sh
import boto3
from operator import itemgetter

ecr_client = boto3.client('ecr')

# Get all ECR repos and print names
repos = ecr_client.describe_repositories()['repositories']
for repo in repos:
    print(repo['repositoryName'])

print("-----------------------")

# For one specific repo, get all the images and print them out sorted by date

# replace with your own repo-name
repo_name = "java-app"
images = ecr_client.describe_images(
    repositoryName=repo_name
)

image_tags = []

for image in images['imageDetails']:
    image_tags.append({
        'tag': image['imageTags'],
        'pushed_at': image['imagePushedAt']
    })

images_sorted = sorted(image_tags, key=itemgetter("pushed_at"), reverse=True)
for image in images_sorted:
    print(image)

```

</details>

******

<details>
<summary>Exercise 5: Python in Jenkins Pipeline </summary>
 <br />

**Do the following tasks manually** 
```sh
# Install Python inside Jenkins server
apt-get install python3
apt-get install pip
pip install boto3
pip install paramiko
pip install requests

# Create credentials in Jenkins 
"jenkins_aws_access_key_id" - Secret Text
"jenkins_aws_secret_access_key" - Secret Text
"ssh-creds" - SSH Username with private key
"ecr-repo-pwd" - Secret Text

# NOTE: you will have to approve usage of "split" function in script. You will see the link to approval inside the build console logs

```

**Code**
```sh
# In jenkins folder, you will find the Jenkinsfile that executes 3 python scripts for different stages:
- get-images.py
- deploy.py
- validate.py

# Before executing the Jenkins pipeline, set the following environment variable values inside Jenkinsfile
- ECR_REPO_NAME
- EC2_SERVER
- ECR_REGISTRY
- CONTAINER_PORT
- HOST_PORT
- AWS_DEFAULT_REGION
```

</details>

******