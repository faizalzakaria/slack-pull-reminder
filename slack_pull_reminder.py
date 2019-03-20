import os
import sys
from collections import defaultdict
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

Hi! Please review these PR: \


"""

APPROVED_INITIAL_MESSAGE = """\

Please merge & deploy APPROVED PR when its ready: \


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

def is_approved(pull):
    for review in pull.reviews():
        if review.state == 'APPROVED':
            return True

    return False

def duration(created_at):
    current_date = datetime.now().replace(tzinfo=None)
    return (current_date - created_at.replace(tzinfo=None)).days

def get_review_statuses(pull):
    dict = defaultdict(set)

    for review in pull.reviews():
        if review.state == 'APPROVED':
            state = ':white_check_mark:'
        elif review.state == 'CHANGES_REQUESTED':
            state = ':o:'
        else:
            continue

        dict[state].add('@{0}'.format(review.user.login))

    if dict:
        line = 'Reviews: ' + ' '.join(['{0} by {1}'.format(key, ', '.join(value)) for (key, value) in dict.items()])
    else:
        line = 'No reviews :warning:'

    return line

def format_pull_requests(pull_requests, owner, repository):
    approved_lines = []
    for_review_lines = []

    for pull in pull_requests:
        if is_valid_title(pull.title) and is_valid_labels(pull.labels) and is_open(pull.state):
            creator = pull.user.login
            review_statuses = get_review_statuses(pull)
            days = duration(pull.created_at)

            line = "*[{0}/{1}]* <{2}|{3} by {4}> - *since {5} day(s)* - {6}".format(
                owner, repository, pull.html_url, pull.title, creator, days, review_statuses)

            if is_approved(pull):
                approved_lines.append(line)
            else:
                for_review_lines.append(line)

    return [for_review_lines, approved_lines]


def fetch_organization_pulls(organization_name):
    """
    Returns a formatted string list of open pull request messages.
    """
    client = login(token=GITHUB_API_TOKEN)
    organization = client.organization(organization_name)
    approved_lines = []
    for_review_lines = []

    organization

    for repository in organization.repositories():
        if REPOSITORIES and repository.name.lower() not in REPOSITORIES:
            continue
        unchecked_pulls = fetch_repository_pulls(repository)
        _for_review_lines, _approved_lines = format_pull_requests(unchecked_pulls, organization_name,
                                                              repository.name)

        for_review_lines += _for_review_lines
        approved_lines += _approved_lines

    return [for_review_lines, approved_lines]


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
    for_review_lines, approved_lines = fetch_organization_pulls(ORGANIZATION)
    if for_review_lines:
        text = INITIAL_MESSAGE + '\n'.join(for_review_lines)
        print(text)
        send_to_slack(text)

    if approved_lines:
        text = APPROVED_INITIAL_MESSAGE + '\n'.join(approved_lines)
        print(text)
        send_to_slack(text)


if __name__ == '__main__':
    cli()
