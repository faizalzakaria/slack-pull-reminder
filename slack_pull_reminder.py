import os
import sys
from datetime import datetime

import requests
from github3 import login

POST_URL = 'https://slack.com/api/chat.postMessage'

ignore = os.environ.get('IGNORE_WORDS')
IGNORE_WORDS = [i.lower().strip() for i in ignore.split(',')] if ignore else []

filter_labels = os.environ.get('FILTER_LABELS')
FILTER_LABELS = [i.lower().strip() for i in filter_labels.split(',')] if filter_labels else []

repositories = os.environ.get('REPOSITORIES')
REPOSITORIES = [r.lower().strip() for r in repositories.split(',')] if repositories else []

usernames = os.environ.get('USERNAMES')
USERNAMES = [u.lower().strip() for u in usernames.split(',')] if usernames else []

SLACK_CHANNEL = os.environ.get('SLACK_CHANNEL', '#general')

try:
    SLACK_API_TOKEN = os.environ['SLACK_API_TOKEN']
    GITHUB_API_TOKEN = os.environ['GITHUB_API_TOKEN']
    ORGANIZATION = os.environ['ORGANIZATION']
except KeyError as error:
    sys.stderr.write('Please set the environment variable {0}'.format(error))
    sys.exit(1)

INITIAL_MESSAGE = """\
Hi! There's a few open pull requests you should take a \
look at:

"""


def fetch_repository_pulls(repository):
    pulls = []
    for pull in repository.pull_requests():
        if pull.state == 'open' and (not USERNAMES or pull.user.login.lower() in USERNAMES):
            pulls.append(pull)
    return pulls


def is_valid_title(title):
    lowercase_title = title.lower()
    for ignored_word in IGNORE_WORDS:
        if ignored_word in lowercase_title:
            return False

    return True

def is_valid_labels(labels):
    if not FILTER_LABELS:
        return True

    for label in labels:
        lowercase_label = label['name'].lower()
        for filtered_label in FILTER_LABELS:
            if filtered_label in lowercase_label:
                return True

    return False

def is_open(state):
    if state in 'open':
        return True

    return False

def is_approved(labels):
    for label in labels:
        lowercase_label = label['name'].lower()
        if lowercase_label in 'approved':
            return True

    return False

def duration(created_at):
    current_date = datetime.now().replace(tzinfo=None)
    return (current_date - created_at.replace(tzinfo=None)).days

def format_pull_requests(pull_requests, owner, repository):
    lines = []

    for pull in pull_requests:
        if is_valid_title(pull.title) and is_valid_labels(pull.labels) and is_open(pull.state):
            creator = pull.user.login
            line = "*[{0}/{1}]* <{2}|{3} by {4}> - *since {5} day(s)*".format(
                owner, repository, pull.html_url, pull.title, creator, duration(pull.created_at))

            if is_approved(pull.labels):
                line = "{0} - *approved*".format(line)

            print(pull.statuses_url)
            lines.append(line)

    return lines


def fetch_organization_pulls(organization_name):
    """
    Returns a formatted string list of open pull request messages.
    """
    client = login(token=GITHUB_API_TOKEN)
    organization = client.organization(organization_name)
    lines = []

    for repository in organization.repositories():
        if REPOSITORIES and repository.name.lower() not in REPOSITORIES:
            continue
        unchecked_pulls = fetch_repository_pulls(repository)
        lines += format_pull_requests(unchecked_pulls, organization_name,
                                      repository.name)

    return lines


def send_to_slack(text):
    payload = {
        'token': SLACK_API_TOKEN,
        'channel': SLACK_CHANNEL,
        'username': 'Pull Request Reminder',
        'icon_emoji': ':bell:',
        'text': text
    }

    response = requests.post(POST_URL, data=payload)
    answer = response.json()
    if not answer['ok']:
        raise Exception(answer['error'])


def cli():
    lines = fetch_organization_pulls(ORGANIZATION)
    if lines:
        text = INITIAL_MESSAGE + '\n'.join(lines)
        print(text)
        send_to_slack(text)

if __name__ == '__main__':
    cli()
